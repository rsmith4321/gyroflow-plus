#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build provenance checks with synthetic Cargo messages; no app compilation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('build_plus',ROOT/'_scripts/build_plus.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class BuildReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='plus-build-receipt-')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.output=self.root/'_dev/receipt.json'
        self.binary=self.root/'_dev/receipt.json.target/deploy/gyroflow'
        self.commit='a'*40
        self.artifact=dict(reason='compiler-artifact',target=dict(name='gyroflow',kind=['bin']),
                           manifest_path=str(self.root/'Cargo.toml'),executable=str(self.binary))
        # Synthetic lens database and matching pin; the fake cargo publishes it.
        self.lens_bytes=b'\x1f\x8bsynthetic lens database'
        self.lens=self.root/builder.LENS_DB
        self.write_pin(hashlib.sha256(self.lens_bytes).hexdigest())

    def write_pin(self, sha256, url='https://github.com/gyroflow/lens_profiles/releases/download/v41/profiles.cbor.gz'):
        pin=self.root/builder.LENS_PIN;pin.parent.mkdir(parents=True,exist_ok=True)
        pin.write_text(f'# fixture\ntag=v41\nurl={url}\nsha256={sha256}\n')

    def run_build(self, messages=None, status=None, commits=None, failure=None, lens=b'default', **options):
        with patch.object(builder,'ROOT',self.root),patch.object(builder.sys,'platform','darwin'), \
             patch.object(builder.subprocess,'check_output',side_effect=[
                 (commits or [self.commit,self.commit])[0].encode(), status or b'',
                 (commits or [self.commit,self.commit])[1].encode(),b'']), \
             patch.object(builder.subprocess,'run') as cargo:
            if failure: cargo.side_effect=failure
            else:
                def compile_fixture(*args,**kwargs):
                    self.env=kwargs.get('env')
                    self.binary.parent.mkdir(parents=True,exist_ok=True)
                    self.binary.write_bytes(b'synthetic binary; never executed')
                    if lens is not None:
                        self.lens.parent.mkdir(parents=True,exist_ok=True)
                        self.lens.write_bytes(self.lens_bytes if lens==b'default' else lens)
                    return subprocess.CompletedProcess([],0,stdout='\n'.join(json.dumps(value)
                        for value in (messages if messages is not None else [self.artifact])))
                cargo.side_effect=compile_fixture
            receipt=builder.build(self.output,features='ocio-runtime',**dict(dict(offline=True),**options))
            command=cargo.call_args.args[0]
        return receipt,command

    def test_success_pins_cargo_reported_executable_and_exact_source(self):
        receipt,command=self.run_build()
        self.assertEqual(receipt['commit'],self.commit)
        self.assertIs(receipt['dirty'],False)
        self.assertEqual(receipt['exe_sha256'],hashlib.sha256(self.binary.read_bytes()).hexdigest())
        self.assertEqual(receipt,json.loads(self.output.read_text()))
        self.assertIn('--locked',command);self.assertIn('--offline',command)
        self.assertNotIn('--no-default-features',command)
        self.assertIs(receipt['default_features'],True)
        self.assertEqual(command[command.index('--manifest-path')+1],str(self.root/'Cargo.toml'))
        self.assertEqual(command[command.index('--target-dir')+1],str(self.binary.parents[1]))
        self.assertEqual(receipt['executable'],str(self.binary))

    def test_explicit_default_feature_opt_out_is_passed_and_recorded(self):
        receipt,command=self.run_build(no_default_features=True)
        self.assertEqual(command.count('--no-default-features'),1)
        self.assertEqual(command[command.index('--features')+1],'ocio-runtime')
        self.assertIs(receipt['default_features'],False)

    def test_failed_build_never_writes_receipt(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_build(failure=subprocess.CalledProcessError(101,['cargo']))
        self.assertFalse(self.output.exists())

    def test_dirty_source_never_starts_cargo(self):
        with patch.object(builder.subprocess,'run') as cargo, self.assertRaisesRegex(RuntimeError,'committed source'):
            self.run_build(status=b' M src/main.rs')
        cargo.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_source_change_during_build_never_writes_receipt(self):
        with self.assertRaisesRegex(RuntimeError,'Source commit changed'):
            self.run_build(commits=[self.commit,'b'*40])
        self.assertFalse(self.output.exists())

    def test_wrong_package_or_missing_or_multiple_artifacts_are_refused(self):
        for messages in ([],[dict(self.artifact,manifest_path=str(self.root/'dependency/Cargo.toml'))],
                         [self.artifact,self.artifact]):
            with self.subTest(messages=messages),self.assertRaisesRegex(RuntimeError,'exactly one executable'):
                self.run_build(messages=messages)
            self.assertFalse(self.output.exists())
            shutil.rmtree(self.output.parent/(self.output.name+'.target'))

    def test_shared_target_output_is_never_used_or_overwritten(self):
        self.binary.parent.mkdir(parents=True);self.binary.write_bytes(b'existing build evidence')
        with self.assertRaises(FileExistsError): self.run_build()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.binary.read_bytes(),b'existing build evidence')

    def test_cargo_artifact_outside_owned_directory_is_refused(self):
        outside=self.root/'target/deploy/gyroflow'
        outside.parent.mkdir(parents=True);outside.write_bytes(b'other checkout build')
        with self.assertRaisesRegex(RuntimeError,'outside this build'):
            self.run_build(messages=[dict(self.artifact,executable=str(outside))])
        self.assertFalse(self.output.exists())

    def test_existing_receipt_preserved_without_build(self):
        self.output.parent.mkdir();self.output.write_bytes(b'existing evidence')
        with patch.object(builder.subprocess,'run') as cargo,self.assertRaisesRegex(RuntimeError,'already exists'):
            self.run_build()
        cargo.assert_not_called()
        self.assertEqual(self.output.read_bytes(),b'existing evidence')

    def test_pinned_lens_database_is_verified_and_recorded(self):
        receipt,_=self.run_build()
        lens=receipt['lens_profiles']
        self.assertEqual(lens['mode'],'pinned')
        self.assertEqual(lens['sha256'],hashlib.sha256(self.lens_bytes).hexdigest())
        self.assertEqual(lens['bytes'],len(self.lens_bytes))
        self.assertEqual(lens['pin']['tag'],'v41')
        self.assertEqual(lens['pin']['pin_file_sha256'],hashlib.sha256((self.root/builder.LENS_PIN).read_bytes()).hexdigest())
        # Cargo's --offline is not visible to build scripts; the receipt helper forwards it.
        self.assertEqual(self.env['GYROFLOW_LENS_PROFILES'],'pinned')
        self.assertEqual(self.env['GYROFLOW_BUILD_OFFLINE'],'1')
        self.assertNotIn('GYROFLOW_LENS_PROFILES_FILE',self.env)

    def test_missing_or_unpinned_lens_database_never_writes_receipt(self):
        for lens,message in ((None,'missing after the build'),(b'\x1f\x8bnewer upstream db','is not pinned')):
            with self.subTest(lens=lens),self.assertRaisesRegex(RuntimeError,message):
                self.run_build(lens=lens)
            self.assertFalse(self.output.exists())
            shutil.rmtree(self.output.parent/(self.output.name+'.target'))
            self.lens.unlink(missing_ok=True)

    def test_mutable_or_malformed_pin_is_refused_before_cargo(self):
        for sha256,url in (('a'*64,'https://github.com/gyroflow/lens_profiles/releases/latest/download/profiles.cbor.gz'),
                           ('A'*64,'https://github.com/gyroflow/lens_profiles/releases/download/v41/profiles.cbor.gz'),
                           ('a'*64,'http://example.invalid/profiles.cbor.gz')):
            self.write_pin(sha256,url)
            with self.subTest(url=url),patch.object(builder.subprocess,'run') as cargo, \
                 self.assertRaisesRegex(RuntimeError,'Lens profile pin'):
                self.run_build()
            cargo.assert_not_called()
            self.assertFalse(self.output.exists());self.assertFalse(self.binary.exists())

    def test_supplied_lens_file_is_forwarded_and_latest_mode_is_recorded_unverified(self):
        supplied=self.root/'v41.cbor.gz';supplied.write_bytes(self.lens_bytes)
        receipt,_=self.run_build(lens_profiles_file=supplied)
        self.assertEqual(self.env['GYROFLOW_LENS_PROFILES_FILE'],str(supplied.resolve()))
        self.assertEqual(receipt['lens_profiles']['supplied_file'],str(supplied.resolve()))
        self.output.unlink();shutil.rmtree(self.output.parent/(self.output.name+'.target'))
        receipt,_=self.run_build(lens=b'\x1f\x8bwhatever latest was',lens_profiles='latest',offline=False)
        self.assertEqual(receipt['lens_profiles']['mode'],'latest')
        self.assertIsNone(receipt['lens_profiles']['pin'])
        self.assertEqual(self.env['GYROFLOW_LENS_PROFILES'],'latest')
        self.assertNotIn('GYROFLOW_BUILD_OFFLINE',self.env)

    def test_supplied_file_without_pinned_mode_is_refused(self):
        supplied=self.root/'v41.cbor.gz';supplied.write_bytes(self.lens_bytes)
        with patch.object(builder.subprocess,'run') as cargo,self.assertRaisesRegex(RuntimeError,'requires --lens-profiles pinned'):
            self.run_build(lens_profiles='latest',lens_profiles_file=supplied)
        cargo.assert_not_called()


if __name__=='__main__': unittest.main()
