#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble the FFmpeg corresponding-source bundle from the reviewed component index.

Each component in ffmpeg/provenance/ffmpeg-components.tsv is fetched from its
recorded official source and exactly its pinned tree is archived (git archive,
or svn export for SVN pins). Fetched code is never executed. A component that
cannot be fetched is listed as missing, and the bundle then says it is
incomplete. Not a legal review and not a release approval.

Usage: python3 -I build_ffmpeg_source_bundle.py NOTICE_TREE CACHE_DIR OUTPUT_DIR [--jobs N]
Rerunning with the same CACHE_DIR and OUTPUT_DIR reuses finished archives.
"""
import argparse, concurrent.futures, csv, gzip, hashlib, io, json, os, re, shutil, subprocess, sys, tarfile
from pathlib import Path

INDEX = 'ffmpeg/provenance/ffmpeg-components.tsv'
RECOVERED = 'ffmpeg/provenance/mac-recovered-components-20261010.tsv'
# Sources the v3 index leaves blank, taken from the pinned BtbN scripts
# (ffmpeg/provenance/btbn-9acad4a9-script-pins.txt).
SCRIPT_SOURCES = {
    'opencore-amr': ('git', 'https://git.code.sf.net/p/opencore-amr/code'),
    'lame': ('svn', 'https://svn.code.sf.net/p/lame/svn/trunk/lame'),
}
# Recorded refusals are not retried here.
UNAVAILABLE = {
    'xvidcore': 'svn.xvid.org required authentication on 2026-10-10; no credentials are used',
}
EPOCH = 315532800  # 1980-01-01, fixed archive timestamps for SVN exports


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run(*command, cwd=None):
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))


def components(tree):
    recovered = {}
    if (tree/RECOVERED).is_file():
        for row in csv.DictReader((tree/RECOVERED).read_text().splitlines(), delimiter='\t'):
            recovered[row['component']] = row['official_source'].split(' ')[0]
    out = []
    for row in csv.DictReader((tree/INDEX).read_text().splitlines(), delimiter='\t'):
        name, ref = row['component'], row['pinned_ref']
        commit = row['resolved_commit']
        if name in UNAVAILABLE:
            kind, url = 'unavailable', None
        elif row['fetched_from']:
            kind, url = 'git', row['fetched_from']
        elif name in recovered:
            kind, url, commit = 'git', recovered[name], ref
        elif name in SCRIPT_SOURCES:
            kind, url = SCRIPT_SOURCES[name]
            commit = ref if kind == 'git' else None
        else:
            kind, url = 'unavailable', None
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]*', name):
            raise ValueError(f'Unsafe component name {name!r}')
        out.append(dict(component=name, role=row['role'], pinned_ref=ref, commit=commit, kind=kind, url=url,
                        note=row['primary_or_mirror'] or None))
    return out


def git_archive(item, cache, target):
    repo = cache/f'{item["component"]}.git'
    if not repo.exists():
        run('git', 'init', '-q', '--bare', str(repo))
    commit = item['commit']
    if not re.fullmatch(r'[0-9a-f]{40}', commit or ''):
        raise ValueError(f'No full commit id for {item["component"]}: {commit!r}')
    try:
        run('git', '-C', str(repo), 'cat-file', '-e', f'{commit}^{{commit}}')
    except subprocess.CalledProcessError:
        try:
            run('git', '-C', str(repo), 'fetch', '-q', '--depth', '1', '--no-tags', item['url'], commit)
        except subprocess.CalledProcessError:
            # Some servers refuse fetching an unadvertised commit; fetch the refs instead.
            run('git', '-C', str(repo), 'fetch', '-q', '--no-tags', item['url'],
                '+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*')
        run('git', '-C', str(repo), 'cat-file', '-e', f'{commit}^{{commit}}')
    prefix = f'{item["component"]}-{commit[:12]}/'
    run('git', '-C', str(repo), 'archive', '--format=tar.gz', f'--prefix={prefix}', '-o', str(target), commit)


def deterministic_tar_gz(source, prefix, target):
    """Archive a directory with sorted names, fixed times and no owner names."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as tar:
        for path in [source, *sorted(source.rglob('*'))]:
            arcname = prefix.rstrip('/') if path == source else prefix + path.relative_to(source).as_posix()
            info = tar.gettarinfo(str(path), arcname=arcname)
            info.mtime, info.uid, info.gid, info.uname, info.gname = EPOCH, 0, 0, '', ''
            if info.isreg():
                with path.open('rb') as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)
    # No embedded file name or time, so equal trees give equal bytes.
    with open(target, 'wb') as stream, gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as f:
        f.write(raw.getvalue())


def svn_archive(item, cache, target):
    revision = item['pinned_ref'].removeprefix('r')
    if not revision.isdigit():
        raise ValueError(f'No SVN revision for {item["component"]}: {item["pinned_ref"]!r}')
    export = cache/f'{item["component"]}-r{revision}'
    if not export.exists():
        partial = export.with_name(export.name + '.partial')
        shutil.rmtree(partial, ignore_errors=True)
        run('svn', 'export', '--non-interactive', '-q', '-r', revision, f'{item["url"]}@{revision}', str(partial))
        partial.rename(export)
    deterministic_tar_gz(export, f'{item["component"]}-r{revision}/', target)


def archive(item, cache, components_dir):
    if item['kind'] == 'unavailable':
        return dict(item, archive=None, error=UNAVAILABLE.get(item['component'], 'no recorded official source'))
    pin = item['commit'][:12] if item['kind'] == 'git' else item['pinned_ref']
    target = components_dir/f'{item["component"]}-{pin}.tar.gz'
    try:
        if not target.exists():
            partial = target.with_name(target.name + '.partial')
            (git_archive if item['kind'] == 'git' else svn_archive)(item, cache, partial)
            partial.rename(target)
    except (subprocess.CalledProcessError, ValueError, OSError) as failure:
        detail = getattr(failure, 'stderr', '') or str(failure)
        return dict(item, archive=None, error=detail.strip().splitlines()[-1][:300] if detail.strip() else repr(failure))
    return dict(item, archive=f'components/{target.name}', bytes=target.stat().st_size, sha256=sha256(target))


def bundle(output, members, name):
    """Uncompressed tar of the finished members with fixed metadata."""
    target = output/name
    with tarfile.open(target, 'w', format=tarfile.PAX_FORMAT) as tar:
        for rel in sorted(members):
            info = tar.gettarinfo(str(output/rel), arcname=f'{Path(name).stem}/{rel}')
            info.mtime, info.uid, info.gid, info.uname, info.gname = EPOCH, 0, 0, '', ''
            with (output/rel).open('rb') as f:
                tar.addfile(info, f)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('tree', type=Path, help='reviewed native notice tree (contains MANIFEST.json)')
    parser.add_argument('cache', type=Path, help='fetch cache, reused between runs')
    parser.add_argument('output', type=Path, help='bundle output directory, reused between runs')
    parser.add_argument('--jobs', type=int, default=6)
    args = parser.parse_args()
    tree = args.tree.resolve(strict=True)
    # git archive runs inside each cached repository, so paths must be absolute.
    args.cache, args.output = args.cache.resolve(), args.output.resolve()
    manifest = json.loads((tree/'MANIFEST.json').read_text())
    identity = manifest['components']['ffmpeg']['identity']
    args.cache.mkdir(parents=True, exist_ok=True)
    components_dir = args.output/'components'
    components_dir.mkdir(parents=True, exist_ok=True)
    items = components(tree)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda item: archive(item, args.cache, components_dir), items))
    for result in results:
        state = result['archive'] or f'MISSING: {result["error"]}'
        print(f'{result["component"]}: {state}', flush=True)
    missing = [dict(component=r['component'], pinned_ref=r['pinned_ref'], reason=r['error'])
               for r in results if not r['archive']]
    index = dict(schema='gyroflow-plus/ffmpeg-corresponding-source/v1',
        ffmpeg_commit=identity['ffmpeg_commit'], btbn_commit=identity['btbn_commit'],
        archive_sha256=identity['archive_sha256'],
        notice_manifest_sha256=sha256(tree/'MANIFEST.json'),
        component_index=INDEX, components_listed=len(results),
        components_archived=len(results) - len(missing), missing=missing,
        complete=not missing, public_release_approved=False,
        limits=['Archives the pinned upstream trees; build-time patches are applied by the archived BtbN scripts.',
                'Rust crates resolved from rav1e/librsvg Cargo.lock files are not separately archived.',
                'Toolchain rows record their own provenance notes; see each entry.'],
        components=[{k: r.get(k) for k in ('component', 'role', 'pinned_ref', 'commit', 'kind', 'url', 'note',
                                           'archive', 'bytes', 'sha256')} for r in results])
    (args.output/'SOURCE-INDEX.json').write_text(json.dumps(index, indent=1) + '\n')
    shutil.copy2(tree/INDEX, args.output/'ffmpeg-components.tsv')
    members = ['SOURCE-INDEX.json', 'ffmpeg-components.tsv'] + [r['archive'] for r in results if r['archive']]
    name = f'FFmpeg-{identity["ffmpeg_commit"][:10]}-corresponding-source.tar'
    target = bundle(args.output, members, name)
    print(json.dumps(dict(bundle=str(target), bytes=target.stat().st_size, sha256=sha256(target),
                          archived=index['components_archived'], listed=len(results),
                          missing=[m['component'] for m in missing]), indent=1))
    return 0 if not missing else 4


if __name__ == '__main__':
    sys.exit(main())
