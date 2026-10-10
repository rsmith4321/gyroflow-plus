#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic tar of `cargo vendor` output for the corresponding-source archive.

  cargo vendor --frozen --versioned-dirs <work>/cargo-vendor > <work>/vendor-config.toml
  python3 vendor_archive.py <work>/cargo-vendor <commit> <out>/Gyroflow-Plus-rust-vendor-<commit12>.tar <work>/vendor-config.toml

The archive holds cargo-vendor/ plus .cargo/config.toml pointing at it with a
relative path. Extract it into a new parent directory, and extract the matching
Git source archive into that directory's src/ child. Invoke Cargo from src/ so
the parent source config merges with the unchanged repository target config.
NEVER overlay this archive on the Git source: both contain .cargo/config.toml,
and overlay would erase the repository's target linker flags. The directory is
not called vendor/ because the
repository already has vendor/ (the patched ffmpeg-sys-next and qmetaobject_impl
path crates); a vendor source there fails with "failed to load checksum
.cargo-checksum.json of ffmpeg-sys-next". Entries are sorted; owner, group and
mtime are fixed (mtime = the commit's committer time from `git log -1 --format=%ct`),
so the same vendor tree gives the same bytes. Run it from the repository
checkout, because it reads the commit time with git. Standard library only.
"""
import io, os, subprocess, sys, tarfile

CONFIG = '''# Generated for the Gyroflow+ corresponding-source archive.
[source.crates-io]
replace-with = "vendored-sources"
{git}
[source.vendored-sources]
directory = "cargo-vendor"
'''


def git_sources(vendor_config_text):
    # Keep cargo vendor's own [source."git+..."] stanzas, which map git deps to the vendor dir.
    out, keep = [], False
    for line in vendor_config_text.splitlines():
        if line.startswith('[source.'):
            keep = line.startswith('[source."git+')
        if keep:
            out.append(line)
    return '\n'.join(out) + '\n'


def main(vendor_dir, commit, out_path, vendor_config=None):
    mtime = int(subprocess.run(['git', 'log', '-1', '--format=%ct', commit], check=True, capture_output=True, text=True).stdout.strip())
    git = git_sources(open(vendor_config, encoding='utf-8').read()) if vendor_config else ''

    def info(name, size, mode, kind=tarfile.REGTYPE):
        ti = tarfile.TarInfo(name)
        ti.size, ti.mtime, ti.mode, ti.type = size, mtime, mode, kind
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ''
        return ti

    with (sys.stdout.buffer if out_path == '-' else open(out_path, 'wb')) as raw, \
            tarfile.open(fileobj=raw, mode='w|', format=tarfile.PAX_FORMAT) as tar:
        cfg = CONFIG.format(git=git).encode()
        tar.addfile(info('.cargo/config.toml', len(cfg), 0o644), io.BytesIO(cfg))
        entries = []
        for root, dirs, files in os.walk(vendor_dir):
            dirs.sort()
            for f in files:
                entries.append(os.path.join(root, f))
        for path in sorted(entries, key=lambda p: os.path.relpath(p, vendor_dir).replace(os.sep, '/')):
            rel = 'cargo-vendor/' + os.path.relpath(path, vendor_dir).replace(os.sep, '/')
            if os.path.islink(path):
                raise SystemExit('symlink in vendor tree, refusing: ' + rel)
            mode = 0o755 if os.stat(path).st_mode & 0o100 else 0o644
            with open(path, 'rb') as f:
                tar.addfile(info(rel, os.path.getsize(path), mode), f)


if __name__ == '__main__':
    if len(sys.argv) not in (4, 5):
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
