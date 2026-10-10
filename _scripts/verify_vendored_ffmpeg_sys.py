#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove vendor/ffmpeg-sys-next-9.0.0 is the crates.io 9.0.0 package plus its patch.

    python3 _scripts/verify_vendored_ffmpeg_sys.py --crate path/to/ffmpeg-sys-next-9.0.0.crate

The .crate file is the published package, e.g. from
https://static.crates.io/crates/ffmpeg-sys-next/ffmpeg-sys-next-9.0.0.crate. It must have
the SHA-256 crates.io publishes (the checksum the unpatched Cargo.lock recorded). The script
extracts it to a temporary directory, applies vendor/ffmpeg-sys-next-9.0.0.patch with
`git apply` and requires the result to equal the vendored tree byte for byte. The package's
own Cargo.lock is not vendored: Cargo ignores it for path dependencies and the package's
.gitignore excludes it. Nothing is downloaded or built.
"""
import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'ffmpeg-sys-next-9.0.0'
CRATE_SHA256 = '9b939bf79dd5949412a4b81cfe21a07f48ea21b47fcbb5f57816c8c2de5ae30b'
NOT_VENDORED = {'Cargo.lock'}


def tree(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in sorted(directory.rglob('*')) if path.is_file()}


def verify(crate, vendored=ROOT/'vendor'/NAME, patch=ROOT/'vendor'/f'{NAME}.patch', expected_sha256=CRATE_SHA256):
    """Return a list of errors; empty means the vendored tree is exactly package + patch."""
    data = Path(crate).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        return [f'{crate} has SHA-256 {actual}, not the published {expected_sha256}']
    with tempfile.TemporaryDirectory(prefix='plus-ffmpeg-sys-') as temporary:
        temporary = Path(temporary)
        # Verify and extract the same bytes, even if the input path changes.
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            for member in archive.getmembers():
                parts = Path(member.name).parts
                if not (member.isfile() or member.isdir()) or not parts or parts[0] != NAME or '..' in parts:
                    return [f'Unexpected package member {member.name!r}']
            # Members were checked above; the data filter adds defence where available (3.12+, backports).
            archive.extractall(temporary, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
        upstream = temporary/NAME
        for name in NOT_VENDORED: (upstream/name).unlink(missing_ok=True)
        applied = subprocess.run(['git', 'apply', str(Path(patch).resolve())], cwd=upstream,
                                 capture_output=True, text=True, timeout=30)
        if applied.returncode:
            return [f'{patch} does not apply to the published package: {applied.stderr.strip()}']
        expected, found = tree(upstream), tree(Path(vendored))
    errors = [f'Missing vendored file {name}' for name in sorted(expected.keys() - found.keys())]
    errors += [f'Unexpected vendored file {name}' for name in sorted(found.keys() - expected.keys())]
    errors += [f'Vendored {name} differs from package + patch' for name in sorted(expected.keys() & found.keys())
               if expected[name] != found[name]]
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--crate', required=True, type=Path, help=f'the published {NAME}.crate file')
    errors = verify(parser.parse_args().crate)
    for error in errors: print(error, file=sys.stderr)
    print('vendored ffmpeg-sys-next: ' + ('MISMATCH' if errors else f'matches {NAME} {CRATE_SHA256} + patch'))
    return 1 if errors else 0


if __name__ == '__main__': sys.exit(main())
