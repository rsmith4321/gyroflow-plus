#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate and supplement for cargo-about output (Task C rust-dependency-notices-v2).

This is not a licence collector: cargo-about 0.9.2 collects. It checks the
cargo-about JSON against the crates that `cargo tree` says are linked for the
shipped target(s), and copies the few upstream notice files cargo-about cannot
emit (supplement.json) after a sha256 check. Standard library only.

  python3 rust_notices_check.py \
      --about-json work/cargo-about.json \
      --linked work/linked-<triple>.txt [--linked ...] \
      --metadata work/metadata-<triple>.json [--metadata ...] \
      --supplement recipe/supplement.json \
      --out-dir out/notices

Exit status:
  0  every linked crate has a non-blank licence text from its own package or an
     allowed canonical fallback, and every supplement file matched its sha256;
  1  the gate failed: a linked crate is missing, has an "Unknown" licence, has no
     text, or fell back to canonical text for an attribution licence without an
     entry in supplement.json's canonical_fallback_allowed; or a licence entry's
     text is blank; or a supplement file changed;
  2  the inputs are unusable: a linked-crates file is empty, has a blank or
     unparseable line, or the cargo-about JSON is not the 0.9.2 shape.
"""
import argparse, hashlib, json, os, re, sys

# Licences whose terms require the copyright notice itself to be reproduced, so a
# canonical SPDX text (no holder line) is not enough on its own.
ATTRIBUTION = {"MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib", "BSL-1.0",
               "Unicode-3.0", "Unicode-DFS-2015", "Unicode-DFS-2016", "CDLA-Permissive-2.0"}
# One `cargo tree --prefix none -f '{p}|{l}'` line: name, version, optional source, licence (may be empty).
LINE = re.compile(r'^([A-Za-z0-9_-]+) v([0-9][0-9A-Za-z.+-]*)(?: \([^()]*\))?(?: \(\*\))?\|[^|\n]*$')


class InputError(Exception):
    pass


def linked_crates(paths):
    """Every line must be one crate; an empty file or a blank/unparseable line is refused."""
    out = set()
    for p in paths:
        with open(p, encoding='utf-8') as f:
            lines = f.read().split('\n')
        if lines and lines[-1] == '':
            lines.pop()  # final newline
        if not lines:
            raise InputError('linked-crates file is empty: %s' % p)
        for n, line in enumerate(lines, 1):
            m = LINE.match(line)
            if not m:
                raise InputError('%s:%d: not a cargo tree crate line: %r' % (p, n, line[:120]))
            out.add((m.group(1), m.group(2)))
    return out


def _str(v):
    return isinstance(v, str) and v != ''


def validate_about(about):
    """Refuse anything that is not cargo-about 0.9.2's JSON shape (src/generate.rs LicenseList)."""
    if not isinstance(about, dict) or not isinstance(about.get('crates'), list) or not isinstance(about.get('licenses'), list):
        raise InputError('cargo-about JSON must be an object with "crates" and "licenses" lists')
    if not about['crates']:
        raise InputError('cargo-about JSON lists no crates')
    for i, c in enumerate(about['crates']):
        pkg = c.get('package') if isinstance(c, dict) else None
        if not isinstance(pkg, dict) or not _str(pkg.get('name')) or not _str(pkg.get('version')) or not _str(c.get('license')):
            raise InputError('crates[%d] lacks package.name, package.version or license' % i)
    for i, lic in enumerate(about['licenses']):
        if not isinstance(lic, dict) or not _str(lic.get('id')) or not isinstance(lic.get('text'), str) \
                or not (lic.get('source_path') is None or isinstance(lic.get('source_path'), str)) \
                or not isinstance(lic.get('used_by'), list) or not lic['used_by']:
            raise InputError('licenses[%d] lacks id, text, source_path or a non-empty used_by' % i)
        for u in lic['used_by']:
            cr = u.get('crate') if isinstance(u, dict) else None
            if not isinstance(cr, dict) or not _str(cr.get('name')) or not _str(cr.get('version')):
                raise InputError('licenses[%d].used_by has an entry without crate.name/version' % i)


def check(about, linked, allowed):
    crates = {(c['package']['name'], c['package']['version']): c['license'] for c in about['crates']}
    texts = {}
    errors, info = [], []
    for lic in about['licenses']:
        users = ['%s %s' % (u['crate']['name'], u['crate']['version']) for u in lic['used_by']]
        if not lic['text'].strip():
            errors.append('blank %s licence text for: %s' % (lic['id'], ', '.join(users)))
            continue
        for used in lic['used_by']:
            key = (used['crate']['name'], used['crate']['version'])
            texts.setdefault(key, []).append((lic['id'], lic['source_path'] is not None))
    allow = {(a['crate'], a['version'], a['license']) for a in allowed}
    for key in sorted(linked):
        name = '%s %s' % key
        if key not in crates:
            errors.append('missing from notices: ' + name)
        elif crates[key] == 'Unknown':
            errors.append('licence unknown: ' + name)
        elif key not in texts:
            errors.append('no licence text: ' + name)
        else:
            for lic_id, from_file in texts[key]:
                if not from_file and lic_id in ATTRIBUTION and (key[0], key[1], lic_id) not in allow:
                    errors.append('canonical %s text without holder line: %s' % (lic_id, name))
    for key in sorted(set(crates) - linked):
        info.append('in notices but not linked (proc-macro or host-only): %s %s' % key)
    for a in allowed:
        if (a['crate'], a['version']) not in linked:
            info.append('allow entry not in this graph: %s %s' % (a['crate'], a['version']))
    return errors, info


def package_dirs(paths):
    dirs = {}
    for p in paths:
        with open(p, encoding='utf-8') as f:
            for pkg in json.load(f)['packages']:
                dirs[(pkg['name'], pkg['version'])] = os.path.dirname(pkg['manifest_path'])
    return dirs


def supplement(spec, spec_dir, linked, dirs, out_dir):
    copied, errors = [], []
    for e in spec['entries']:
        users = [(e['crate'], e['version'])] + [tuple(a.split(' ', 1)) for a in e.get('also', [])]
        users = [u for u in users if u in linked]
        if not users:
            continue
        src = os.path.join(dirs[(e['crate'], e['version'])], e['package']) if 'package' in e else os.path.join(spec_dir, e['committed'])
        with open(src, 'rb') as f:
            data = f.read()
        if hashlib.sha256(data).hexdigest() != e['sha256']:
            errors.append('supplement checksum mismatch: ' + src)
            continue
        name = '%s-%s-%s' % (e['crate'], e['version'], os.path.basename(src))
        os.makedirs(os.path.join(out_dir, 'SUPPLEMENT'), exist_ok=True)
        with open(os.path.join(out_dir, 'SUPPLEMENT', name), 'wb') as f:
            f.write(data)
        copied.append(dict(file='SUPPLEMENT/' + name, sha256=e['sha256'], crates=['%s %s' % u for u in users], reason=e['reason']))
    return copied, errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--about-json', required=True)
    ap.add_argument('--linked', action='append', required=True)
    ap.add_argument('--metadata', action='append', default=[])
    ap.add_argument('--supplement', required=True)
    ap.add_argument('--out-dir')
    a = ap.parse_args(argv)
    try:
        with open(a.about_json, encoding='utf-8') as f:
            about = json.load(f)
        validate_about(about)
        linked = linked_crates(a.linked)
    except (InputError, ValueError, OSError) as e:
        print('ERROR: unusable input:', e)
        return 2
    with open(a.supplement, encoding='utf-8') as f:
        spec = json.load(f)
    errors, info = check(about, linked, spec.get('canonical_fallback_allowed', []))
    copied = []
    if a.out_dir:
        if not a.metadata:
            ap.error('--out-dir needs --metadata to locate package files')
        copied, sup_errors = supplement(spec, os.path.dirname(os.path.abspath(a.supplement)), linked, package_dirs(a.metadata), a.out_dir)
        errors += sup_errors
    for line in info:
        print('info:', line)
    for line in errors:
        print('ERROR:', line)
    print(json.dumps(dict(linked=len(linked), notice_crates=len(about['crates']), errors=len(errors), supplement=copied), indent=1))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
