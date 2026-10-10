#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a locked Mac Cargo build and record its reported executable identity.

This local build receipt is provenance, not a signature or a public-release
approval. Windows uses the receipt produced by its existing deploy recipe.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# Not tracked (.gitignore: resources/camera_presets), so a clean checkout does
# not identify it; the receipt must. Deploy recipes copy this exact file.
LENS_DB = Path('resources/camera_presets/profiles.cbor.gz')
LENS_PIN = Path('src/core/lens_profiles.pin')


def source_identity():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip())
    if dirty:
        raise RuntimeError('Build receipts require committed source, including newly added files')
    return commit


def read_lens_pin(root):
    """Same trivial key=value format that src/core/lens_db_input.rs parses."""
    data = (root/LENS_PIN).read_bytes()
    values = {}
    for line in data.decode().splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        key, sep, value = line.partition('=')
        if not sep or key.strip() not in ('tag', 'url', 'sha256') or key.strip() in values:
            raise RuntimeError(f'Malformed lens profile pin line: {line!r}')
        values[key.strip()] = value.strip()
    if (not values.get('tag') or not values.get('url', '').startswith('https://') or '/latest/' in values['url']
            or not re.fullmatch(r'[0-9a-f]{64}', values.get('sha256', ''))):
        raise RuntimeError('Lens profile pin needs a tag, a versioned https url and a lowercase SHA-256')
    return dict(values, pin_file=LENS_PIN.as_posix(), pin_file_sha256=hashlib.sha256(data).hexdigest())


def lens_identity(root, mode, pin, supplied):
    path = root/LENS_DB
    if not path.is_file():
        raise RuntimeError(f'{LENS_DB} is missing after the build; no receipt written')
    data = path.read_bytes()
    facts = dict(mode=mode, path=LENS_DB.as_posix(), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                 supplied_file=str(supplied) if supplied else None, pin=pin)
    if mode == 'pinned' and facts['sha256'] != pin['sha256']:
        raise RuntimeError(f'{LENS_DB} SHA-256 {facts["sha256"]} is not pinned {pin["sha256"]}; no receipt written')
    return facts


def build(output, profile='deploy', features='', target=None, jobs=4, offline=False,
          lens_profiles='pinned', lens_profiles_file=None, no_default_features=False):
    if sys.platform != 'darwin':
        raise RuntimeError('Use this build receipt helper on Mac; Windows uses just deploy')
    output = output.resolve()
    if output.exists():
        raise RuntimeError('Build receipt already exists; use a fresh output')
    # Create the directory before checking Git so a new non-ignored output
    # directory cannot silently become part of the supposedly clean source.
    output.parent.mkdir(parents=True, exist_ok=True)
    commit = source_identity()
    if lens_profiles not in ('pinned', 'latest'):
        raise RuntimeError('lens_profiles must be pinned or latest')
    pin = read_lens_pin(ROOT) if lens_profiles == 'pinned' else None
    supplied = Path(lens_profiles_file).resolve(strict=True) if lens_profiles_file else None
    if supplied and not pin:
        raise RuntimeError('--lens-profiles-file requires --lens-profiles pinned')
    # Cargo does not pass --offline to build scripts; the core build script reads these.
    env = dict(os.environ, GYROFLOW_LENS_PROFILES=lens_profiles)
    env.pop('GYROFLOW_LENS_PROFILES_FILE', None)
    if supplied: env['GYROFLOW_LENS_PROFILES_FILE'] = str(supplied)
    if offline: env.update(GYROFLOW_BUILD_OFFLINE='1', CARGO_NET_OFFLINE='true')
    # A different clean checkout may share Cargo's normal target directory.
    # Its build can replace the executable after Cargo releases its lock but
    # before we hash it. Keep this invocation's artifacts exclusively owned.
    target_dir = output.parent/(output.name+'.target')
    target_dir.mkdir(exist_ok=False)
    command = ['cargo', 'build', '--locked', '--manifest-path', str(ROOT/'Cargo.toml'),
               '--bin', 'gyroflow', '--profile', profile, '--jobs', str(jobs),
               '--target-dir', str(target_dir),
               '--message-format', 'json-render-diagnostics']
    if no_default_features: command.append('--no-default-features')
    if features: command += ['--features', features]
    if target: command += ['--target', target]
    if offline: command.append('--offline')
    # Cargo emits diagnostics to stderr. Select the executable from its
    # compiler-artifact message rather than guessing a target-directory path.
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, text=True, check=True, env=env)
    artifacts = []
    for line in result.stdout.splitlines():
        message = json.loads(line)
        if (message.get('reason') == 'compiler-artifact'
                and message.get('target', {}).get('name') == 'gyroflow'
                and 'bin' in message.get('target', {}).get('kind', [])
                and Path(message.get('manifest_path', '')).resolve() == ROOT/'Cargo.toml'
                and message.get('executable')):
            artifacts.append(Path(message['executable']).resolve(strict=True))
    if len(artifacts) != 1:
        raise RuntimeError('Cargo did not report exactly one executable from this package')
    binary = artifacts[0]
    if not binary.is_relative_to(target_dir):
        raise RuntimeError('Cargo reported an executable outside this build\'s owned target directory')
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    lens = lens_identity(ROOT, lens_profiles, pin, supplied)
    if source_identity() != commit:
        raise RuntimeError('Source commit changed during the build; no receipt written')
    receipt = dict(platform='mac', commit=commit, dirty=False,
                   features=features, default_features=not no_default_features, target=target, profile=profile,
                   target_directory=str(target_dir),
                   command=command, executable=str(binary), exe_sha256=binary_hash,
                   lens_profiles=lens, public_release_approved=False)
    # Exclusive creation also refuses a receipt created by another build
    # while this one was running.
    with output.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2)+'\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new build receipt, preferably under ignored _dev/')
    parser.add_argument('--profile', default='deploy')
    parser.add_argument('--features', default='')
    parser.add_argument('--no-default-features', action='store_true',
                        help='pass through to Cargo; select opencv explicitly when required')
    parser.add_argument('--target')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--offline', action='store_true', help='also forbids the core build script\'s lens profile fetch')
    parser.add_argument('--lens-profiles', choices=['pinned', 'latest'], default='pinned',
                        help='pinned: verify src/core/lens_profiles.pin (default); latest: record whatever is used')
    parser.add_argument('--lens-profiles-file', type=Path, help='supplied pinned database, e.g. for --offline')
    args = parser.parse_args()
    if args.jobs < 1: parser.error('--jobs must be positive')
    print(json.dumps(build(args.output, args.profile, args.features, args.target, args.jobs, args.offline,
                           args.lens_profiles, args.lens_profiles_file, args.no_default_features), indent=2))


if __name__ == '__main__': main()
