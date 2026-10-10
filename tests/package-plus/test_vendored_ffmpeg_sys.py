#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Vendored ffmpeg-sys-next overlay checks; no download, no FFmpeg, no app compilation."""
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('verify_vendored_ffmpeg_sys',ROOT/'_scripts/verify_vendored_ffmpeg_sys.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
VENDORED=ROOT/'vendor'/verifier.NAME
PATCH=ROOT/'vendor'/f'{verifier.NAME}.patch'


class VendoredFfmpegSysTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='plus-ffmpeg-sys-test-')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def synthetic_crate(self, vendored=VENDORED):
        """Rebuild an 'upstream' package by reversing the patch; its hash is not the published one."""
        upstream=self.root/'upstream'/verifier.NAME
        shutil.copytree(vendored,upstream)
        subprocess.run(['git','apply','-R',str(PATCH)],cwd=upstream,check=True,capture_output=True)
        (upstream/'Cargo.lock').write_text('# package lockfile, not vendored\n')
        crate=self.root/f'{verifier.NAME}.crate'
        with tarfile.open(crate,'w:gz') as archive: archive.add(upstream,arcname=verifier.NAME)
        return crate

    def test_patch_entry_and_lockfile_identify_the_vendored_package(self):
        manifest=(ROOT/'Cargo.toml').read_text()
        patch_section=manifest.split('[patch.crates-io]',1)[1].split('\n[',1)[0]
        self.assertRegex(patch_section,r'(?m)^ffmpeg-sys-next = \{ path = "vendor/ffmpeg-sys-next-9\.0\.0" \}\s*$')
        packages=(ROOT/'Cargo.lock').read_text().split('[[package]]')
        entry,=[package for package in packages if '\nname = "ffmpeg-sys-next"\n' in package]
        self.assertIn('\nversion = "9.0.0"\n',entry)
        self.assertNotIn('source =',entry); self.assertNotIn('checksum =',entry)

    def test_only_obsolete_macos_frameworks_are_removed(self):
        build=(VENDORED/'build.rs').read_text()
        requested=re.findall(r'^\s*"(\w+)",$',build.split('// Frameworks available on all Apple platforms',1)[1]
                             .split('check_features(',1)[0],re.M)
        self.assertEqual(requested,['AudioToolbox','AVFoundation','CoreFoundation','CoreGraphics','CoreMedia','CoreServices',
                                    'CoreVideo','Foundation','QuartzCore','Security','VideoToolbox','AppKit','OpenCL','OpenGL'])
        self.assertNotIn('"QTKit"',build); self.assertNotIn('"VideoDecodeAcceleration"',build)
        changed=[line for line in PATCH.read_text().splitlines()
                 if line[:1] in '+-' and not line.startswith(('+++','---'))]
        self.assertEqual([line for line in changed if line.startswith('-') and 'Frameworks only' not in line],
                         ['-                "QTKit",','-                "VideoDecodeAcceleration",'])
        self.assertTrue(all(line.lstrip('+').strip().startswith('//') for line in changed if line.startswith('+')))

    def test_verifier_accepts_package_plus_patch_and_rejects_changes(self):
        crate=self.synthetic_crate()
        sha=__import__('hashlib').sha256(crate.read_bytes()).hexdigest()
        self.assertEqual(verifier.verify(crate,expected_sha256=sha),[])
        self.assertIn('not the published',verifier.verify(crate)[0])
        changed=self.root/'changed'; shutil.copytree(VENDORED,changed)
        (changed/'src/lib.rs').write_bytes((changed/'src/lib.rs').read_bytes()+b'\n')
        (changed/'extra.rs').write_text('')
        errors=verifier.verify(crate,vendored=changed,expected_sha256=sha)
        self.assertIn('Vendored src/lib.rs differs from package + patch',errors)
        self.assertIn('Unexpected vendored file extra.rs',errors)

    def test_verifier_refuses_unsafe_package_members(self):
        crate=self.root/'evil.crate'
        with tarfile.open(crate,'w:gz') as archive:
            info=tarfile.TarInfo(f'{verifier.NAME}/../escape'); info.size=0
            archive.addfile(info,io.BytesIO())
        sha=__import__('hashlib').sha256(crate.read_bytes()).hexdigest()
        self.assertIn('Unexpected package member',verifier.verify(crate,expected_sha256=sha)[0])

    @unittest.skipUnless(os.environ.get('FFMPEG_SYS_CRATE'),'set FFMPEG_SYS_CRATE to the published .crate file')
    def test_published_package(self):
        self.assertEqual(verifier.verify(os.environ['FFMPEG_SYS_CRATE']),[])


if __name__=='__main__':
    unittest.main()
