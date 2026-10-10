#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the actual build script in an offline disposable Cargo crate."""
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BuildScriptTests(unittest.TestCase):
    def test_missing_optional_database_settles_and_existing_database_is_watched(self):
        with tempfile.TemporaryDirectory(prefix='gyroflow-build-script-') as temporary:
            work = Path(temporary)
            core = work / 'repo/src/core'
            (core / 'src').mkdir(parents=True)
            for name in ('build.rs', 'lens_db_input.rs'):
                shutil.copy2(ROOT / 'src/core' / name, core / name)
            (core / 'src/lib.rs').write_text('pub fn probe() -> u32 { 1 }\n')
            (core / 'Cargo.toml').write_text(
                '[package]\nname="gyroflow-build-script-probe"\nversion="0.1.0"\n'
                'edition="2024"\npublish=false\n[workspace]\n[build-dependencies]\n'
                'ureq="=3.4.0"\nring="=0.17.14"\nflate2="=1.1.10"\n')
            supplied = work / 'supplied.gz'
            supplied.write_bytes(gzip.compress(b'synthetic database', mtime=0))
            digest = hashlib.sha256(supplied.read_bytes()).hexdigest()
            (core / 'lens_profiles.pin').write_text(
                'tag=probe\nurl=https://example.invalid/profiles.cbor.gz\n'
                f'sha256={digest}\n')
            env = os.environ.copy()
            for key in ('GYROFLOW_LENS_PROFILES_FILE', 'CARGO_FEATURE_BUNDLE_LENS_PROFILES',
                        'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_RUSTFLAGS'):
                env.pop(key, None)
            env.update(GYROFLOW_LENS_PROFILES='latest', GYROFLOW_BUILD_OFFLINE='1',
                       CARGO_NET_OFFLINE='true', CARGO_TARGET_DIR=str(work / 'target'))

            def build(expect_fresh=False):
                result = subprocess.run(['cargo', 'build', '--offline', '-vv'], cwd=core,
                                        env=env, capture_output=True, text=True, timeout=120)
                log = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, log[-12000:])
                if expect_fresh:
                    self.assertIn('Fresh gyroflow-build-script-probe', log, log[-12000:])
                    self.assertFalse(any('Running `' in line and
                                         '--crate-name gyroflow_build_script_probe' in line
                                         for line in log.splitlines()), log[-12000:])

            # A missing optional watched path previously made every build stale.
            build()
            build(expect_fresh=True)
            build(expect_fresh=True)
            # Publication is watched once present. Cargo may rerun once because
            # the published file is newer than the build-script start stamp.
            env.update(GYROFLOW_LENS_PROFILES='pinned',
                       GYROFLOW_LENS_PROFILES_FILE=str(supplied))
            build()
            build()
            build(expect_fresh=True)
            database = work / 'repo/resources/camera_presets/profiles.cbor.gz'
            self.assertEqual(database.read_bytes(), supplied.read_bytes())
            # Deleting a previously watched database causes one re-evaluation;
            # optional/offline mode must then settle again without a database.
            database.unlink()
            env['GYROFLOW_LENS_PROFILES'] = 'latest'
            env.pop('GYROFLOW_LENS_PROFILES_FILE')
            build()
            build(expect_fresh=True)
            self.assertFalse(database.exists())


if __name__ == '__main__':
    unittest.main()
