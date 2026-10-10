#!/usr/bin/env python3
"""Offline verifier for a native dependency notice tree and its MANIFEST.json (schema v1 or v2).

Standard library only; no network; never writes. Delivery validation only, not
an application runtime dependency, not a legal review and not a release approval.

Content integrity (any failure -> exit 1):
  - with --manifest-sha256, MANIFEST.json has exactly that SHA-256
  - every member path is a safe relative POSIX path (no absolute path, drive,
    backslash, empty/'.'/'..' segment, or dot-directory)
  - no symlink anywhere in the tree, and every member resolves inside the root
  - every member exists as a regular file with the recorded bytes and SHA-256
  - every file in the tree is a member (MANIFEST.json itself excepted)
  - every member is referenced by exactly one component or the packet list,
    and every referenced path is a member of that component
  - every required component is present with identity and provenance entries,
    and its recorded release status agrees with its gaps
  - v2: the staged inventory has the declared count, unique safe names, valid
    sizes/hashes, and every entry is assigned to a listed component
  - with --repo-root, every reused repository path has the recorded bytes/SHA-256
Release provenance is reported separately and never affects integrity. It is
INCOMPLETE while any gap has a blocking class (blocker or obligation; v1 string
gaps count as blocking), or while a component that ships staged files has no
notice text and no recorded reason why none is needed.

Exit codes: 0 integrity PASS; 1 integrity FAIL; 2 usage or unreadable/malformed
manifest; 3 integrity PASS but release provenance INCOMPLETE under
--require-release-complete.

Usage: python3 -I verify_native_notices.py ROOT [--repo-root DIR]
       [--manifest-sha256 HEX] [--require-release-complete]
"""
import argparse, hashlib, json, os, re, stat, sys

MANIFEST = 'MANIFEST.json'
HEX64 = re.compile(r'^[0-9a-f]{64}$')
COMPONENT_KEYS = ('name', 'version', 'required', 'identity', 'notice_members',
                  'provenance_members', 'reused_repo_paths', 'release_provenance')
BLOCKING = {'blocker', 'obligation'}          # always blocking, whatever the manifest says
OPEN_CLASSES = {'blocker', 'obligation', 'advisory'}
CLOSED_CLASSES = {'resolved', 'duplicate'}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def path_problem(p):
    if not isinstance(p, str) or not p:
        return 'empty or non-string path'
    if p.startswith('/') or '\\' in p or re.match(r'^[A-Za-z]:', p) or '\x00' in p:
        return 'absolute, drive or backslash path'
    parts = p.split('/')
    if any(s in ('', '.', '..') for s in parts):
        return 'empty, "." or ".." segment'
    if any(s.startswith('.') for s in parts[:-1]):
        return 'dot-directory segment'
    return None


def check_regular_inside(root_real, root, rel):
    """Return (abs_path, problem). Rejects symlinks at any level and escapes."""
    cur = root
    for seg in rel.split('/'):
        cur = os.path.join(cur, seg)
        try:
            st = os.lstat(cur)
        except OSError:
            return cur, 'missing'
        if stat.S_ISLNK(st.st_mode):
            return cur, 'symlink'
    real = os.path.realpath(cur)
    if os.path.commonpath([root_real, real]) != root_real:
        return cur, 'resolves outside root'
    if not stat.S_ISREG(os.lstat(cur).st_mode):
        return cur, 'not a regular file'
    return cur, None


def normalise_gaps(rp):
    """Return (open_gaps, closed_gaps, problem) as lists of dicts with 'id' and 'class'."""
    gaps = rp.get('gaps') if isinstance(rp, dict) else None
    if not isinstance(gaps, list):
        return [], [], 'gaps is not a list'
    out = []
    for i, g in enumerate(gaps):
        if isinstance(g, str):                       # schema v1: unclassified, treated as blocking
            out.append({'id': f'gap-{i+1}', 'class': 'blocker', 'text': g})
        elif isinstance(g, dict) and isinstance(g.get('id'), str) and g.get('class') in OPEN_CLASSES:
            out.append(g)
        else:
            return [], [], f'gap[{i}] has no id or an unknown open class'
    closed = rp.get('resolved', [])
    if not isinstance(closed, list) or any(not isinstance(g, dict) or g.get('class') not in CLOSED_CLASSES for g in closed):
        return [], [], 'resolved entries must have class resolved or duplicate'
    return out, closed, None


def main():
    ap = argparse.ArgumentParser(description='Verify a native notice tree against MANIFEST.json')
    ap.add_argument('root')
    ap.add_argument('--repo-root', help='repository checkout to check reused_repo_paths against')
    ap.add_argument('--manifest-sha256', help='expected SHA-256 of MANIFEST.json (pins the gap classification)')
    ap.add_argument('--require-release-complete', action='store_true')
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    if os.path.islink(root) or not os.path.isdir(root):
        print(f'USAGE-ERROR: {a.root} is not a directory')
        return 2
    if a.manifest_sha256 is not None and not HEX64.match(a.manifest_sha256):
        print('USAGE-ERROR: --manifest-sha256 must be 64 lowercase hex digits')
        return 2
    root_real = os.path.realpath(root)
    mpath = os.path.join(root, MANIFEST)
    try:
        if os.path.islink(mpath):
            raise ValueError('MANIFEST.json is a symlink')
        with open(mpath, 'rb') as f:
            mbytes = f.read()
        m = json.loads(mbytes)
        members = m['members']
        comps = m['components']
        required = m['required_components']
        packet = m.get('packet_members', [])
        if not isinstance(members, list) or not isinstance(comps, dict) or not isinstance(required, list):
            raise ValueError('members/components/required_components have the wrong type')
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f'MANIFEST-ERROR: {type(e).__name__}: {e}')
        return 2

    errors = []
    mdigest = hashlib.sha256(mbytes).hexdigest()
    print(f'manifest: {MANIFEST} sha256={mdigest} bytes={len(mbytes)}')
    print(f'schema: {m.get("schema")}  status: {m.get("status")}  target: {m.get("target")}')
    print(f'public_release_approved: {m.get("public_release_approved")}')
    if a.manifest_sha256 is not None:
        if mdigest != a.manifest_sha256:
            errors.append(f'MANIFEST-SHA256-MISMATCH expected {a.manifest_sha256} found {mdigest}')
        else:
            print('manifest pin: matches --manifest-sha256')

    # 1. members: safe paths, uniqueness, existence, bytes, sha256
    seen = {}
    total = 0
    for i, mem in enumerate(members):
        p = mem.get('path') if isinstance(mem, dict) else None
        prob = path_problem(p)
        if prob:
            errors.append(f'UNSAFE-PATH member[{i}] {p!r}: {prob}')
            continue
        if p == MANIFEST:
            errors.append(f'UNSAFE-PATH member[{i}] {p}: manifest cannot list itself')
            continue
        if p in seen:
            errors.append(f'DUPLICATE-MEMBER {p}')
            continue
        seen[p] = mem
        if not isinstance(mem.get('bytes'), int) or not HEX64.match(str(mem.get('sha256', ''))):
            errors.append(f'BAD-MEMBER-RECORD {p}: bytes/sha256 missing or malformed')
            continue
        ap_, prob = check_regular_inside(root_real, root, p)
        if prob:
            errors.append(f'{prob.upper().replace(" ", "-")} {p}')
            continue
        size = os.lstat(ap_).st_size
        if size != mem['bytes']:
            errors.append(f'SIZE-MISMATCH {p}: expected {mem["bytes"]} found {size}')
            continue
        digest = sha256_file(ap_)
        if digest != mem['sha256']:
            errors.append(f'SHA256-MISMATCH {p}: expected {mem["sha256"]} found {digest}')
            continue
        total += size
    print(f'members listed: {len(members)}  verified bytes: {total}')

    # 2. tree walk: no symlinks, no unlisted files
    on_disk = 0
    for dp, dns, fns in os.walk(root, followlinks=False):
        for n in sorted(dns):
            full = os.path.join(dp, n)
            if os.path.islink(full):
                errors.append(f'SYMLINK {os.path.relpath(full, root).replace(os.sep, "/")}')
        for n in sorted(fns):
            full = os.path.join(dp, n)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            if rel == MANIFEST:
                continue
            on_disk += 1
            if os.path.islink(full):
                if rel not in seen:
                    errors.append(f'SYMLINK {rel}')
                continue
            if rel not in seen:
                errors.append(f'UNLISTED-FILE {rel}')
    print(f'files on disk (excluding {MANIFEST}): {on_disk}')

    # 3. references: each member referenced exactly once; component tags agree
    refs = {}
    for p in packet:
        refs.setdefault(p, []).append('packet')
    for cid, c in comps.items():
        missing_keys = [k for k in COMPONENT_KEYS if k not in c]
        if missing_keys:
            errors.append(f'COMPONENT-RECORD {cid}: missing {", ".join(missing_keys)}')
            continue
        for kind in ('notice_members', 'provenance_members'):
            for p in c[kind]:
                refs.setdefault(p, []).append(cid)
    for p, owners in sorted(refs.items()):
        if p not in seen:
            errors.append(f'REFERENCED-NOT-MEMBER {p} (by {", ".join(owners)})')
        elif len(owners) != 1:
            errors.append(f'MULTIPLY-REFERENCED {p} (by {", ".join(owners)})')
        elif seen[p].get('component') != owners[0]:
            errors.append(f'COMPONENT-TAG {p}: member says {seen[p].get("component")!r}, referenced by {owners[0]!r}')
    for p in seen:
        if p not in refs:
            errors.append(f'UNREFERENCED-MEMBER {p}')

    # 4. required components, provenance entries and status consistency
    gapinfo = {}
    for cid, c in comps.items():
        if any(k not in c for k in COMPONENT_KEYS):
            continue
        open_, closed, prob = normalise_gaps(c['release_provenance'])
        if prob:
            errors.append(f'PROVENANCE-ENTRY {cid}: {prob}')
            continue
        blocking = [g for g in open_ if g['class'] in BLOCKING]
        status = c['release_provenance'].get('status')
        if status != ('INCOMPLETE' if blocking else 'COMPLETE'):
            errors.append(f'PROVENANCE-ENTRY {cid}: status {status!r} disagrees with {len(blocking)} blocking gap(s)')
        gapinfo[cid] = (open_, closed)
    for cid in required:
        c = comps.get(cid)
        if c is None:
            errors.append(f'REQUIRED-COMPONENT-MISSING {cid}')
            continue
        if any(k not in c for k in COMPONENT_KEYS):
            continue
        if not c['required']:
            errors.append(f'REQUIRED-COMPONENT-FLAG {cid}: required is false')
        if not isinstance(c['identity'], dict) or not c['identity']:
            errors.append(f'PROVENANCE-ENTRY {cid}: identity is empty')
        if not c['provenance_members']:
            errors.append(f'PROVENANCE-ENTRY {cid}: no provenance member')
    print(f'components: {len(comps)}  required: {", ".join(required)}')

    # 5. staged inventory (schema v2)
    staged_by = {}
    if 'staged_inventory' in m:
        inv = m['staged_inventory']
        count = m.get('staged_inventory_count')
        if not isinstance(inv, list) or not isinstance(count, int):
            errors.append('STAGED-INVENTORY: staged_inventory/staged_inventory_count malformed')
            inv = []
        elif len(inv) != count:
            errors.append(f'STAGED-INVENTORY-COUNT expected {count} found {len(inv)}')
        names = set()
        for i, e in enumerate(inv):
            n = e.get('path') if isinstance(e, dict) else None
            if path_problem(n):
                errors.append(f'STAGED-INVENTORY entry[{i}] {n!r}: {path_problem(n)}')
                continue
            if n.lower() in names:
                errors.append(f'STAGED-INVENTORY-DUPLICATE {n}')
            names.add(n.lower())
            if not isinstance(e.get('bytes'), int) or not HEX64.match(str(e.get('sha256', ''))):
                errors.append(f'STAGED-INVENTORY-RECORD {n}: bytes/sha256 missing or malformed')
            if e.get('component') not in comps:
                errors.append(f'STAGED-INVENTORY-COMPONENT {n}: unknown component {e.get("component")!r}')
            elif not e.get('mapping_basis'):
                errors.append(f'STAGED-INVENTORY-BASIS {n}: no mapping basis')
            else:
                staged_by.setdefault(e['component'], []).append(n)
        print(f'staged inventory: {len(inv)} entries across {len(staged_by)} components')
    else:
        print('staged inventory: not present (schema v1)')

    # 6. optional repository reuse check
    if a.repo_root:
        rr = os.path.abspath(a.repo_root)
        rr_real = os.path.realpath(rr)
        checked = 0
        for cid, c in sorted(comps.items()):
            for r in c.get('reused_repo_paths', []):
                p = r.get('path')
                prob = path_problem(p)
                if prob:
                    errors.append(f'REPO-UNSAFE-PATH {cid} {p!r}: {prob}')
                    continue
                ap_, prob = check_regular_inside(rr_real, rr, p)
                if prob:
                    errors.append(f'REPO-{prob.upper().replace(" ", "-")} {cid} {p}')
                    continue
                if os.lstat(ap_).st_size != r.get('bytes') or sha256_file(ap_) != r.get('sha256'):
                    errors.append(f'REPO-MISMATCH {cid} {p}')
                    continue
                checked += 1
        print(f'reused repository paths verified: {checked}')
    else:
        n = sum(len(c.get('reused_repo_paths', [])) for c in comps.values())
        print(f'reused repository paths: {n} recorded, NOT CHECKED (no --repo-root)')

    for e in errors:
        print(f'FAIL {e}')
    integrity = not errors
    print(f'CONTENT-INTEGRITY: {"PASS" if integrity else "FAIL"} ({len(errors)} problem{"s" if len(errors) != 1 else ""})')

    # Release provenance: factual gap classes; independent of integrity.
    counts = {k: 0 for k in ('blocker', 'obligation', 'advisory', 'resolved', 'duplicate')}
    blocking_total = 0
    incomplete = []
    for cid in sorted(gapinfo):
        open_, closed = gapinfo[cid]
        for g in open_ + closed:
            counts[g['class']] += 1
        blk = [g['id'] for g in open_ if g['class'] in BLOCKING]
        c = comps[cid]
        uncovered = bool(staged_by.get(cid)) and not c['notice_members'] and not c['reused_repo_paths'] \
            and not c.get('notice_not_required_reason') and not blk
        if uncovered:
            blk.append('no-notice-for-staged-files')
        blocking_total += len(blk)
        if blk:
            incomplete.append(cid)
            print(f'release-blocking {cid}: {", ".join(blk)}')
        adv = [g['id'] for g in open_ if g['class'] == 'advisory']
        if adv:
            print(f'release-advisory {cid}: {", ".join(adv)}')
    if m.get('public_release_approved') is not False:
        incomplete.append('packet')
        print('release-blocking packet: public_release_approved is not false')
    print('gap classes: ' + ', '.join(f'{k}={v}' for k, v in counts.items()))
    print(f'RELEASE-PROVENANCE: {"INCOMPLETE" if incomplete else "COMPLETE"} '
          f'({blocking_total} blocking gaps across {len(incomplete)} components)')
    if not integrity:
        return 1
    if a.require_release_complete and incomplete:
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
