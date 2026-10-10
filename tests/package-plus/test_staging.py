#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaging guards; synthetic fixtures only, no app/video execution."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package_plus', ROOT / '_scripts/package_plus.py')
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)
PACKET = 'resources/color/ocio-third-party'


class StagingTests(unittest.TestCase):
    def test_legacy_windows_deploy_receipt_without_platform_passes_preflight(self):
        with tempfile.TemporaryDirectory(prefix='plus-windows-receipt-') as temporary:
            root=Path(temporary);runtime=root/'runtime';runtime.mkdir()
            (root/'Cargo.toml').write_text('[package]\nversion="0.1.0-dev"\n')
            binary=root/'gyroflow.exe';binary.write_bytes(b'synthetic; never executed')
            shutil.copy2(binary,runtime/'Gyroflow.exe')
            receipt=root/'receipt.json';commit='a'*40
            receipt.write_text(json.dumps(dict(commit=commit,dirty=False,features='ocio-runtime',
                exe_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),crt_source='fixture')))
            command=['package_plus.py','windows',str(runtime),str(root/'stage'),
                '--binary',str(binary),'--licenses',str(root/'notices'),
                '--deploy-receipt',str(receipt),'--msvc-redist-floor','14.51.36260.0',
                '--native-notices-sha256','0'*64]
            with patch.object(stager,'ROOT',root),patch.object(sys,'argv',command), \
                 patch.object(stager,'git',side_effect=lambda *args: b'' if args[0]=='status' else commit.encode()), \
                 patch.object(stager.shutil,'copytree',side_effect=RuntimeError('staging reached')), \
                 self.assertRaisesRegex(RuntimeError,'staging reached'):
                stager.main()
            self.assertTrue((root/'stage').exists())

    def test_invalid_binary_source_receipts_are_refused_before_output_creation(self):
        with tempfile.TemporaryDirectory(prefix='plus-receipt-test-') as temporary:
            root=Path(temporary)
            runtime=root/'runtime';runtime.mkdir()
            (root/'Cargo.toml').write_text('[package]\nversion="0.1.0-dev"\n')
            binary=root/'gyroflow';binary.write_bytes(b'not executed')
            commit='a'*40
            valid=dict(platform='mac',commit=commit,dirty=False,
                       exe_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
            invalid=[None, b'{', b'[]', dict(valid,commit='b'*40),
                     dict(valid,dirty=True), dict(valid,dirty=0),
                     dict(valid,exe_sha256='0'*64), dict(valid,platform='windows')]
            for value in invalid:
                with self.subTest(receipt=value):
                    output=root/'stage'
                    command=['package_plus.py','mac',str(runtime),str(output),
                             '--binary',str(binary),'--licenses',str(root/'notices')]
                    if value is not None:
                        path=root/'receipt.json'
                        path.write_bytes(value if isinstance(value,bytes) else json.dumps(value).encode())
                        command+=['--deploy-receipt',str(path)]
                    with patch.object(stager,'ROOT',root),patch.object(sys,'argv',command), \
                         patch.object(stager,'git',side_effect=lambda *args: b'' if args[0]=='status' else commit.encode()), \
                         contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as failure:
                        stager.main()
                    self.assertEqual(failure.exception.code,2)
                    self.assertFalse(output.exists())

    def test_dirty_and_untracked_source_is_refused_before_output_creation(self):
        with tempfile.TemporaryDirectory(prefix='plus-stage-test-') as temporary:
            root = Path(temporary)
            repo = root / 'repo'
            repo.mkdir()
            (repo / 'tracked.rs').write_text('initial source')
            def git(*args):
                subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
            git('init')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '-m', 'Synthetic fixture')
            runtime = root / 'runtime'
            runtime.mkdir()
            binary = root / 'fixture.exe'
            binary.write_bytes(b'packaging fixture; never executed')
            output = root / 'stage'
            command = ['package_plus.py', 'windows', str(runtime), str(output),
                       '--binary', str(binary), '--development-runtime']
            for untracked in (False, True):
                with self.subTest(untracked=untracked):
                    if untracked:
                        (repo / 'tracked.rs').write_text('initial source')
                        (repo / 'new_color.rs').write_text('new source')
                    else:
                        (repo / 'tracked.rs').write_text('modified source')
                    with patch.object(stager, 'ROOT', repo), patch.object(sys, 'argv', command), \
                         contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                        stager.main()
                    self.assertEqual(failure.exception.code, 2)
                    self.assertFalse(output.exists())

    def test_windows_release_stage_requires_native_notice_pin_before_output_creation(self):
        with tempfile.TemporaryDirectory(prefix='plus-windows-notice-pin-') as temporary:
            root=Path(temporary);runtime=root/'runtime';runtime.mkdir()
            (root/'Cargo.toml').write_text('[package]\nversion="0.1.0-dev"\n')
            binary=root/'gyroflow.exe';binary.write_bytes(b'synthetic; never executed')
            shutil.copy2(binary,runtime/'Gyroflow.exe')
            receipt=root/'receipt.json';commit='a'*40
            receipt.write_text(json.dumps(dict(commit=commit,dirty=False,features='ocio-runtime',
                exe_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())))
            base=['package_plus.py','windows',str(runtime),str(root/'stage'),'--binary',str(binary),
                '--licenses',str(root/'notices'),'--deploy-receipt',str(receipt),'--msvc-redist-floor','14.51.36260.0']
            for extra in ([],['--native-notices-sha256','ABC'],['--native-notices-sha256','0'*63]):
                with self.subTest(extra=extra), patch.object(stager,'ROOT',root), patch.object(sys,'argv',base+extra), \
                     patch.object(stager,'git',side_effect=lambda *args: b'' if args[0]=='status' else commit.encode()), \
                     contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    stager.main()
                self.assertEqual(failure.exception.code,2)
                self.assertFalse((root/'stage').exists())
            bundle=root/'qt.tar';bundle.write_bytes(b'synthetic')
            for command,message in ((base+['--source-bundle',f'qt={bundle}'],'requires --native-notices-sha256'),
                    (['package_plus.py','mac']+base[2:]+['--native-notices-sha256','0'*64,'--source-bundle',f'qt={bundle}'],
                     'applies to Windows stages'),
                    (base+['--native-notices-sha256','0'*64,'--source-bundle',f'qt={root/"absent.tar"}'],'is not a file')):
                stderr=io.StringIO()
                with self.subTest(message=message), patch.object(stager,'ROOT',root), patch.object(sys,'argv',command), \
                     patch.object(stager,'git',side_effect=lambda *args: b'' if args[0]=='status' else commit.encode()), \
                     contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as failure:
                    stager.main()
                self.assertEqual(failure.exception.code,2)
                self.assertIn(message,stderr.getvalue())
                self.assertFalse((root/'stage').exists())


class NativeNoticeBindingTests(unittest.TestCase):
    """Binds the tracked reviewed tree; the verifier runs offline on copies only."""
    TREE=ROOT/'resources/notices/native/windows-x64'

    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='plus-native-notices-')
        cls.dependencies=Path(cls.temporary.name)/'Dependencies'
        shutil.copytree(cls.TREE,cls.dependencies/'native/windows-x64')
        cls.pin=hashlib.sha256((cls.TREE/'MANIFEST.json').read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_pinned_tree_records_integrity_and_release_gaps(self):
        report=stager.bind_native_notices(self.dependencies,self.pin)
        self.assertEqual(report['errors'],[])
        self.assertEqual(report['manifest_path'],'native/windows-x64/MANIFEST.json')
        self.assertEqual(report['integrity_exit'],0)
        # Recorded release gaps remain; binding never turns them into approval.
        self.assertEqual(report['release_complete_exit'],3)

    def test_recorded_qt_and_libass_bundle_identities_are_read_from_the_tree(self):
        expected=stager.expected_source_bundles(self.dependencies/'native/windows-x64')
        self.assertEqual(expected['qt'],dict(file='Qt-6.7.3-source-bundle.tar',
            sha256='cb7f4c24d5ca9c5f597631d24fe6ea04e22c81a86449e6e4701b3171e102c523'))
        self.assertEqual(expected['libass']['sha256'],'154d2e09f724744168554775a140a20a353649f22053b1c91318414e9c9f1b8f')
        self.assertEqual(stager.expected_source_bundles(None),{})

    def test_unmatched_pin_or_missing_tree_is_an_error(self):
        for dependencies,pin in ((self.dependencies,'0'*64),(self.dependencies/'absent',self.pin)):
            with self.subTest(dependencies=dependencies.name,pin=pin[:8]):
                report=stager.bind_native_notices(dependencies,pin)
                self.assertIsNone(report['integrity_exit'])
                self.assertIn('found 0',report['errors'][0])

    def test_edited_member_fails_integrity(self):
        with tempfile.TemporaryDirectory(prefix='plus-native-notices-edited-') as temporary:
            dependencies=Path(temporary)/'Dependencies'
            shutil.copytree(self.TREE,dependencies/'windows-x64')
            member=next(p for p in sorted((dependencies/'windows-x64').rglob('*'))
                        if p.is_file() and p.name not in ('MANIFEST.json','README.md'))
            member.write_bytes(member.read_bytes()+b'\nedited')
            report=stager.bind_native_notices(dependencies,self.pin)
            self.assertNotEqual(report['integrity_exit'],0)
            self.assertTrue(any('integrity' in error for error in report['errors']))


class SourceBundleTests(unittest.TestCase):
    """Synthetic bundles and recorded identities only."""
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='plus-source-bundles-')
        self.root=Path(self.temporary.name)
        self.bundles={}
        for name in stager.SOURCE_BUNDLES:
            path=self.root/'inputs'/f'{name}-source.tar';path.parent.mkdir(exist_ok=True)
            path.write_bytes(f'synthetic {name} source'.encode());self.bundles[name]=path
        digest=lambda name: hashlib.sha256(self.bundles[name].read_bytes()).hexdigest()
        self.tree=self.root/'tree'
        (self.tree/'qt-6.7.3').mkdir(parents=True)
        (self.tree/'qt-6.7.3/source-bundle.sha256').write_text(f'{digest("qt")}  qt-source.tar\n')
        (self.tree/'mdk-0.39.0/bundled/evidence').mkdir(parents=True)
        (self.tree/'mdk-0.39.0/bundled/evidence/LIBASS-SOURCE-QUALIFICATION.json').write_text(
            json.dumps(dict(retained_source_kit=dict(file='libass-source.tar',sha256=digest('libass')))))

    def tearDown(self):
        self.temporary.cleanup()

    def stage(self, bundles):
        return stager.stage_source_bundles(bundles,self.root/'stage-Source',self.tree)

    def test_all_matching_bundles_are_delivered_beside_the_package(self):
        report,errors=self.stage(list(self.bundles.items()))
        self.assertEqual(errors,[])
        self.assertEqual(report['delivery'],'beside-package')
        self.assertEqual(report['qt']['sha256'],report['qt']['expected_sha256'])
        self.assertIsNone(report['ffmpeg']['expected_sha256'])
        self.assertEqual((self.root/'stage-Source/qt-source.tar').read_bytes(),self.bundles['qt'].read_bytes())

    def test_missing_mismatched_or_repeated_bundles_keep_delivery_open(self):
        report,errors=self.stage([('qt',self.bundles['qt'])])
        self.assertEqual((errors,report['delivery'],report['libass']),([],'open',None))
        self.bundles['libass'].write_bytes(b'edited kit')
        report,errors=stager.stage_source_bundles(list(self.bundles.items()),self.root/'other-Source',self.tree)
        self.assertEqual(report['delivery'],'open')
        self.assertIn('does not match the recorded',errors[0])
        report,errors=stager.stage_source_bundles([('qt',self.bundles['qt'])]*2,self.root/'third-Source',self.tree)
        self.assertIn('supplied more than once',errors[0])

    def test_bundle_arguments_are_validated(self):
        self.assertEqual(stager.source_bundle('qt=a.tar'),('qt',Path('a.tar')))
        for value in ('mesa=a.tar','qt','qt=','=a.tar'):
            with self.subTest(value=value), self.assertRaises(stager.argparse.ArgumentTypeError):
                stager.source_bundle(value)


class QtNoticeTests(unittest.TestCase):
    def test_pinned_derive_license_and_patch_record_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='plus-qt-notices-') as temporary:
            notices=Path(temporary)
            stager.copy_qmetaobject_notices(notices)
            for name in ('LICENSE', 'PATCHES.md', 'UPSTREAM.json'):
                self.assertEqual((notices/'qmetaobject-rs'/name).read_bytes(),
                                 (ROOT/'vendor/qmetaobject-rs'/name).read_bytes())
            pin=json.loads((notices/'qmetaobject-rs/UPSTREAM.json').read_text())
            self.assertEqual(pin['revision'],'ff1e23dcdd722a0c335bbd51f7dcfdb722384db2')
            self.assertEqual(pin['modified_files'],['qmetaobject_impl/src/qobject_impl.rs'])

    def test_existing_notice_packet_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory(prefix='plus-qt-notices-existing-') as temporary:
            notices=Path(temporary);target=notices/'qmetaobject-rs';target.mkdir()
            prior=target/'LICENSE';prior.write_bytes(b'prior packet: preserve')
            with self.assertRaises(FileExistsError):
                stager.copy_qmetaobject_notices(notices)
            self.assertEqual(prior.read_bytes(),b'prior packet: preserve')


class FfmpegSysNoticeTests(unittest.TestCase):
    def test_published_license_declaration_and_patch_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='plus-ffmpeg-sys-notices-') as temporary:
            notices=Path(temporary)
            stager.copy_ffmpeg_sys_notices(notices)
            sources={'README.md':'ffmpeg-sys-next-9.0.0/README.md',
                     'Cargo.toml.orig':'ffmpeg-sys-next-9.0.0/Cargo.toml.orig',
                     'PROVENANCE.md':'README.md', 'PATCH.diff':'ffmpeg-sys-next-9.0.0.patch'}
            for destination,source in sources.items():
                self.assertEqual((notices/'ffmpeg-sys-next'/destination).read_bytes(),
                                 (ROOT/'vendor'/source).read_bytes())
            self.assertIn('license = "WTFPL"',(notices/'ffmpeg-sys-next/Cargo.toml.orig').read_text())

    def test_existing_notice_packet_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory(prefix='plus-ffmpeg-sys-existing-') as temporary:
            notices=Path(temporary); target=notices/'ffmpeg-sys-next';target.mkdir()
            prior=target/'PROVENANCE.md'; prior.write_bytes(b'prior packet: preserve')
            with self.assertRaises(FileExistsError): stager.copy_ffmpeg_sys_notices(notices)
            self.assertEqual(prior.read_bytes(),b'prior packet: preserve')


class MacDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='plus-mach-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.app = self.root / 'GyroGrade.app'
        self.app.mkdir()
        self.metadata = {}
        self.stage_app = None
        self.tool_calls = []
        self.mock = patch.object(stager.subprocess, 'run', side_effect=self.run_tool)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def slice(self, dependencies=(), rpaths=(), minimum='11.0', legacy=False, weak=()):
        return dict(dependencies=dependencies, rpaths=rpaths, minimum=minimum, legacy=legacy, weak=weak)

    def binary(self, relative, slices):
        path = relative if isinstance(relative, Path) else self.app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes.fromhex('cffaedfe') + b'synthetic; never executed')
        self.metadata[path.resolve()] = slices
        return path

    def main_binary(self, data=None, architectures=('arm64',)):
        return self.binary('Contents/MacOS/gyroflow',
                           {architecture: data or self.slice() for architecture in architectures})

    def run_tool(self, args, **kwargs):
        self.tool_calls.append(tuple(args))
        if args[0] in ('codesign', 'git'):
            return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
        path = Path(args[-1]).resolve()
        slices = self.metadata.get(path)
        if slices is None and self.stage_app and path.is_relative_to(self.stage_app):
            slices = self.metadata.get(self.app / path.relative_to(self.stage_app))
        if slices is None:
            return subprocess.CompletedProcess(args, 1, stdout='', stderr='No synthetic Mach-O')
        if args[:2] == ('lipo', '-archs'):
            return subprocess.CompletedProcess(args, 0, stdout=' '.join(slices) + '\n', stderr='')
        self.assertEqual(args[:2], ('otool', '-arch'))
        self.assertEqual(args[3], '-l')
        architecture = args[2]
        data = slices[architecture]
        # IDs are deliberately external; unlike LC_LOAD_DYLIB they are not loads.
        blocks = ['cmd LC_ID_DYLIB\nname /build/fixture-id.dylib (offset 24)']
        if data['legacy']:
            blocks.append(f'cmd LC_VERSION_MIN_MACOSX\nversion {data["minimum"]}\nsdk 14.0')
        else:
            blocks.append(f'cmd LC_BUILD_VERSION\nplatform 1\nminos {data["minimum"]}\nsdk 27.0')
        blocks += [f'cmd LC_RPATH\npath {value} (offset 12)' for value in data['rpaths']]
        blocks += [f'cmd LC_LOAD_DYLIB\nname {value} (offset 24)' for value in data['dependencies']]
        blocks += [f'cmd LC_LOAD_WEAK_DYLIB\nname {value} (offset 24)' for value in data['weak']]
        output = f'{path} (architecture {architecture}):\n' + ''.join(
            f'Load command {index}\n{block}\n' for index, block in enumerate(blocks))
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr='')

    def audit(self):
        return stager.check_mac_dependencies(self.app)

    def stage(self, development=False):
        repo = self.root / 'repo'
        for relative, value in (('Cargo.toml', '[package]\nversion="0.1.0-dev"\n'),
                                ('LICENSE', 'synthetic license fixture'),
                                ('docs/PLUS-DISTRIBUTION.md', 'synthetic distribution fixture')):
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        shutil.copytree(ROOT / PACKET, repo / PACKET)
        shutil.copy2(ROOT / 'resources/color/OCIO-LICENSE.txt', repo / 'resources/color')
        (repo / 'resources/gyrograde').mkdir(parents=True)
        shutil.copy2(ROOT / 'resources/gyrograde/AppIcon.icns', repo / 'resources/gyrograde')
        shutil.copytree(ROOT / 'resources/lens-profiles-v41', repo / 'resources/lens-profiles-v41')
        shutil.copytree(ROOT / 'vendor/qmetaobject-rs', repo / 'vendor/qmetaobject-rs')
        shutil.copytree(ROOT / 'vendor/ffmpeg-sys-next-9.0.0', repo / 'vendor/ffmpeg-sys-next-9.0.0')
        for name in ('README.md', 'ffmpeg-sys-next-9.0.0.patch'):
            shutil.copy2(ROOT / 'vendor' / name, repo / 'vendor' / name)
        lens = b'\x1f\x8bsynthetic lens database'
        lens_sha = hashlib.sha256(lens).hexdigest()
        (repo / 'src/core').mkdir(parents=True, exist_ok=True)
        (repo / 'src/core/lens_profiles.pin').write_text(
            f'tag=v41\nurl=https://github.com/gyroflow/lens_profiles/releases/download/v41/profiles.cbor.gz\nsha256={lens_sha}\n')
        presets = self.app / 'Contents/Resources/camera_presets'
        presets.mkdir(parents=True, exist_ok=True)
        if not (presets / 'profiles.cbor.gz').exists(): (presets / 'profiles.cbor.gz').write_bytes(lens)
        notices = self.root / 'dependency-notices'
        notices.mkdir()
        (notices / 'NOTICE').write_text('Synthetic; does not establish license acceptance')
        plist = self.app / 'Contents/Info.plist'
        with plist.open('wb') as stream:
            plistlib.dump({'LSMinimumSystemVersion': '11.0'}, stream)
        output = self.root / 'stage'
        self.stage_app = output / 'GyroGrade.app'
        command = ['package_plus.py', 'mac', str(self.app), str(output),
                   '--binary', str(self.app / 'Contents/MacOS/gyroflow'), '--licenses', str(notices)]
        if development: command.append('--development-runtime')
        else:
            receipt=self.root/'build-receipt.json'
            receipt.write_text(json.dumps(dict(platform='mac',commit='1234567890abcdef',dirty=False,
                exe_sha256=hashlib.sha256((self.app/'Contents/MacOS/gyroflow').read_bytes()).hexdigest(),
                lens_profiles=dict(mode='pinned',sha256=lens_sha,bytes=len(lens)))))
            command+=['--deploy-receipt',str(receipt)]
        with patch.object(stager, 'ROOT', repo), patch.object(sys, 'argv', command), \
             patch.object(stager, 'git', side_effect=lambda *args: b'' if args[0] == 'status' else b'1234567890abcdef'), \
             contextlib.redirect_stdout(io.StringIO()):
            stager.main()
        return output

    def test_universal_slices_resolve_ocio_and_transitive_imath_symlink(self):
        self.main_binary(self.slice(('@rpath/libOpenColorIO.2.4.dylib',
                                     '/usr/lib/libSystem.B.dylib'),
                                    ('@loader_path/../Frameworks',)), ('x86_64', 'arm64'))
        ocio = self.binary('Contents/Frameworks/libOpenColorIO.2.4.2.dylib', {
            architecture: self.slice(('@loader_path/libImath.dylib',), minimum=minimum)
            for architecture, minimum in (('x86_64', '13.0'), ('arm64', '14.0'))})
        (ocio.parent / 'libOpenColorIO.2.4.dylib').symlink_to(ocio.name)
        self.binary('Contents/Frameworks/libImath.dylib', {
            architecture: self.slice(('/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation',),
                                      minimum='11.0', legacy=True)
            for architecture in ('x86_64', 'arm64')})
        report = self.audit()
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['external_dependencies'], [])
        self.assertEqual(report['maximum_embedded_minimum_macos'], '14.0')
        self.assertEqual(len(report['embedded_minimum_macos']), 6)
        stager.check_mac_minimum(report, {'LSMinimumSystemVersion': '14.0'})
        self.assertEqual(report['errors'], [])

    def test_missing_rpath_ocio_is_rejected(self):
        (self.app / 'Contents/Frameworks').mkdir(parents=True)
        self.main_binary(self.slice(('@rpath/libOpenColorIO.2.4.dylib',),
                                    ('@executable_path/../Frameworks',)))
        self.assertIn('Missing dependency', '\n'.join(self.audit()['errors']))

    def test_obsolete_framework_loads_are_refused_even_in_system_locations(self):
        for name in ('QTKit', 'VideoDecodeAcceleration'):
            with self.subTest(framework=name):
                self.main_binary(self.slice((f'/System/Library/Frameworks/{name}.framework/Versions/A/{name}',)))
                self.assertIn('Obsolete FFmpeg framework dependency', '\n'.join(self.audit()['errors']))
        self.main_binary(self.slice(('/System/Library/Frameworks/VideoToolbox.framework/Versions/A/VideoToolbox',)))
        self.assertEqual(self.audit()['errors'], [])

    def test_unused_external_rpath_is_recorded_even_with_bundled_ocio(self):
        development = self.root / 'SSD/_dev/ocio-runtime/install/lib'
        development.mkdir(parents=True)
        self.main_binary(self.slice(('@rpath/libOpenColorIO.2.4.dylib',),
                                    ('@loader_path/../Frameworks', str(development))))
        self.binary('Contents/Frameworks/libOpenColorIO.2.4.dylib', {'arm64': self.slice()})
        report = self.audit()
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['external_dependencies'], [str(development)])

    def test_development_external_dependency_closure_records_imath(self):
        ocio = self.root / 'SSD/_dev/ocio/libOpenColorIO.2.4.dylib'
        imath = self.root / 'homebrew/lib/libImath.dylib'
        self.binary(imath, {'arm64': self.slice(minimum='26.0')})
        self.binary(ocio, {'arm64': self.slice((str(imath),), minimum='11.0')})
        self.main_binary(self.slice(('@rpath/libOpenColorIO.2.4.dylib',), (str(ocio.parent),)))
        report = self.audit()
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['external_dependencies'], sorted(map(str, (ocio.parent, ocio, imath))))
        self.assertEqual(report['maximum_embedded_minimum_macos'], '11.0')

    def test_inherited_executable_rpath_resolves_a_transitive_dependency(self):
        self.main_binary(self.slice(('@rpath/libOpenColorIO.dylib',), ('@loader_path/../Frameworks',)))
        self.binary('Contents/Frameworks/libOpenColorIO.dylib',
                    {'arm64': self.slice(('@rpath/libImath.dylib',))})
        self.binary('Contents/Frameworks/libImath.dylib', {'arm64': self.slice()})
        self.assertEqual(self.audit()['errors'], [])

    def test_framework_directory_symlink_resolves_inside_bundle(self):
        self.main_binary(self.slice(('@rpath/QtCore.framework/QtCore',), ('@loader_path/../Frameworks',)))
        core = self.binary('Contents/Frameworks/QtCore.framework/Versions/A/QtCore',
                           {'arm64': self.slice()})
        (core.parent.parent / 'Current').symlink_to('A', target_is_directory=True)
        (core.parent.parent.parent / 'QtCore').symlink_to('Versions/Current/QtCore')
        self.assertEqual(self.audit()['errors'], [])
        self.assertEqual(self.audit()['external_dependencies'], [])

    def test_escaping_symlink_cannot_hide_an_external_dependency(self):
        self.main_binary(self.slice(('@loader_path/../Frameworks/libOpenColorIO.dylib',)))
        outside = self.binary(self.root / 'outside/libOpenColorIO.dylib', {'arm64': self.slice()})
        bundled = self.app / 'Contents/Frameworks/libOpenColorIO.dylib'
        bundled.parent.mkdir(parents=True)
        bundled.symlink_to(outside)
        report = self.audit()
        self.assertIn(str(outside), report['external_dependencies'])
        self.assertTrue(any(' -> ' in item for item in report['external_dependencies']))

    def test_rpath_escape_and_missing_directory_are_not_accepted(self):
        self.main_binary(self.slice(rpaths=('@loader_path/../../../outside/missing',)))
        report = self.audit()
        self.assertEqual(report['external_dependencies'], [str(self.root / 'outside/missing')])
        self.assertIn('Missing LC_RPATH directory', '\n'.join(report['errors']))

    def mdk(self, slices):
        """Main executable loading a bundled framework whose own loads the test chooses."""
        self.main_binary(self.slice(('@rpath/mdk.framework/mdk',), ('@loader_path/../Frameworks',)))
        return self.binary('Contents/Frameworks/mdk.framework/mdk', slices)

    def test_missing_weak_load_is_optional_where_the_same_hard_load_fails(self):
        name = '@rpath/libdav1d.7.dylib'
        self.mdk({'arm64': self.slice((name,), ('@loader_path/..',))})
        report = self.audit()
        self.assertIn(f"Missing dependency '{name}'", '\n'.join(report['errors']))
        self.assertEqual(report['optional_weak_missing'], [])
        self.mdk({'arm64': self.slice(rpaths=('@loader_path/..',), weak=(name,))})
        report = self.audit()
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['external_dependencies'], [])
        self.assertEqual(report['optional_weak_missing'],
                         [f'{name} in Contents/Frameworks/mdk.framework/mdk [arm64]'])

    def test_present_weak_load_keeps_hard_closure_slices_and_minimum(self):
        self.mdk({'arm64': self.slice(rpaths=('@loader_path/..',), weak=('@rpath/libmdk-braw.dylib',))})
        braw = self.binary('Contents/Frameworks/libmdk-braw.dylib', {'arm64': self.slice(
            ('@rpath/libBlackmagicRawAPI.dylib',), minimum='27.0')})
        report = self.audit()
        self.assertIn("Missing dependency '@rpath/libBlackmagicRawAPI.dylib'", '\n'.join(report['errors']))
        self.assertEqual(report['optional_weak_missing'], [])
        self.assertEqual(report['maximum_embedded_minimum_macos'], '27.0')
        self.binary(braw, {'x86_64': self.slice()})
        self.assertIn('Missing arm64 Mach-O slice', '\n'.join(self.audit()['errors']))

    def test_weak_load_from_outside_the_bundle_is_still_external(self):
        homebrew = self.root / 'homebrew/lib'
        homebrew.mkdir(parents=True)
        self.binary(homebrew / 'libdav1d.7.dylib', {'arm64': self.slice()})
        self.mdk({'arm64': self.slice(rpaths=(str(homebrew),), weak=('@rpath/libdav1d.7.dylib',))})
        report = self.audit()
        self.assertEqual(report['external_dependencies'], sorted([str(homebrew), str(homebrew / 'libdav1d.7.dylib')]))
        self.assertEqual(report['optional_weak_missing'], [])
        # A fixed outside path is external even while absent from this machine.
        missing = self.root / 'usr-local/lib/libx265.dylib'
        self.mdk({'arm64': self.slice(weak=(str(missing),))})
        report = self.audit()
        self.assertEqual(report['external_dependencies'], [str(missing)])
        self.assertEqual(report['optional_weak_missing'], [])

    def test_missing_weak_rpath_parent_escape_is_still_external(self):
        self.mdk({'arm64': self.slice(rpaths=('@loader_path/..',),
                                     weak=('@rpath/../../../outside/missing.dylib',))})
        report = self.audit()
        self.assertEqual(report['external_dependencies'], [str(self.root / 'outside/missing.dylib')])
        self.assertEqual(report['optional_weak_missing'], [])

    def test_unresolved_weak_symlink_resolution_error_keeps_audit_report(self):
        self.mdk({'arm64': self.slice(rpaths=('@loader_path/..',),
                                     weak=('@rpath/loop.dylib',))})
        loop = self.app / 'Contents/Frameworks/loop.dylib'
        loop.symlink_to(loop.name)
        resolve = Path.resolve
        # Python 3.11/3.12 raise for this loop even with strict=False.
        # Simulate both documented failure types on newer Python as well.
        for failure in (RuntimeError('Symlink loop'), OSError('Symlink loop')):
            def resolving(path, *args, **kwargs):
                if path == loop: raise failure
                return resolve(path, *args, **kwargs)
            with self.subTest(failure=type(failure).__name__):
                with patch.object(Path, 'resolve', resolving):
                    report = self.audit()
                self.assertTrue(any('Invalid dependency' in error and 'loop.dylib' in error
                                    for error in report['errors']))

    def test_weak_obsolete_framework_load_is_still_refused(self):
        self.mdk({'arm64': self.slice(weak=('/System/Library/Frameworks/QTKit.framework/Versions/A/QTKit',))})
        self.assertIn('Obsolete FFmpeg framework dependency', '\n'.join(self.audit()['errors']))

    def test_absent_search_directory_inside_bundle_is_a_diagnostic(self):
        self.mdk({'arm64': self.slice(rpaths=('@loader_path/Frameworks', '@loader_path/..'))})
        report = self.audit()
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['external_dependencies'], [])
        self.assertEqual(report['absent_contained_search_paths'], [
            '@loader_path/Frameworks (Contents/Frameworks/mdk.framework/Frameworks) in '
            'Contents/Frameworks/mdk.framework/mdk [arm64]'])

    def test_missing_universal_dependency_slice_is_rejected(self):
        self.main_binary(self.slice(('@loader_path/../Frameworks/libOpenColorIO.dylib',)),
                         ('x86_64', 'arm64'))
        self.binary('Contents/Frameworks/libOpenColorIO.dylib', {'arm64': self.slice()})
        self.assertIn('Missing x86_64 Mach-O slice', '\n'.join(self.audit()['errors']))

    def test_extra_universal_framework_slice_under_thin_application_is_valid(self):
        self.main_binary(self.slice(('@loader_path/../Frameworks/libOpenColorIO.dylib',)))
        self.binary('Contents/Frameworks/libOpenColorIO.dylib',
                    {architecture: self.slice() for architecture in ('x86_64', 'arm64')})
        self.assertEqual(self.audit()['errors'], [])

    def test_shared_library_is_rechecked_in_both_plugin_loader_contexts(self):
        self.main_binary()
        self.binary('Contents/Frameworks/shared.dylib', {'arm64': self.slice(('@rpath/libImath.dylib',))})
        for name in ('A', 'B'):
            self.binary(f'Contents/PlugIns/{name}/plugin.dylib', {'arm64': self.slice(
                ('@loader_path/../../Frameworks/shared.dylib',), ('@loader_path/Libraries',))})
            (self.app / f'Contents/PlugIns/{name}/Libraries').mkdir()
        self.binary('Contents/PlugIns/A/Libraries/libImath.dylib', {'arm64': self.slice()})
        report = self.audit()
        missing = [value for value in report['errors'] if "Missing dependency '@rpath/libImath.dylib'" in value]
        self.assertEqual(len(missing), 1)
        self.binary('Contents/PlugIns/B/Libraries/libImath.dylib', {'arm64': self.slice()})
        self.assertEqual(self.audit()['errors'], [])

    def test_dynamic_plugin_minimum_is_included_and_false_plist_claim_fails(self):
        self.main_binary()
        self.binary('Contents/PlugIns/platforms/libqcocoa.dylib', {'arm64': self.slice(minimum='27.0')})
        report = self.audit()
        self.assertEqual(report['maximum_embedded_minimum_macos'], '27.0')
        stager.check_mac_minimum(report, {'LSMinimumSystemVersion': '14.0'})
        self.assertIn('below embedded Mach-O minimum 27.0', '\n'.join(report['errors']))

    def test_architecture_specific_plist_claim_is_checked(self):
        self.main_binary(architectures=('x86_64', 'arm64'))
        report = self.audit()
        stager.check_mac_minimum(report, {'LSMinimumSystemVersion': '14.0',
                                       'LSMinimumSystemVersionByArchitecture': {'arm64': '10.15'}})
        self.assertIn('LSMinimumSystemVersionByArchitecture arm64', '\n'.join(report['errors']))

    def test_higher_arm_minimum_override_is_valid_for_universal_runtime(self):
        self.binary('Contents/MacOS/gyroflow', {
            'x86_64': self.slice(minimum='11.0'), 'arm64': self.slice(minimum='14.0')})
        for arm_minimum, valid in (('14.0', True), ('13.0', False)):
            with self.subTest(arm_minimum=arm_minimum):
                report = self.audit()
                stager.check_mac_minimum(report, {'LSMinimumSystemVersion': '11.0',
                                               'LSMinimumSystemVersionByArchitecture': {'arm64': arm_minimum}})
                self.assertEqual(not report['errors'], valid)
        report = self.audit()
        stager.check_mac_minimum(report, {'LSMinimumSystemVersionByArchitecture': {'x86_64': '11.0', 'arm64': '14.0'}})
        self.assertEqual(report['errors'], [])

    def test_missing_or_malformed_minimum_claim_is_rejected(self):
        self.main_binary()
        for info in ({}, {'LSMinimumSystemVersion': 'future'}, {'LSMinimumSystemVersion': 14}):
            with self.subTest(info=info):
                report = self.audit()
                stager.check_mac_minimum(report, info)
                self.assertIn('Invalid macOS minimum version', '\n'.join(report['errors']))

    def test_portable_stage_rejects_missing_ocio_before_signing(self):
        (self.app / 'Contents/Frameworks').mkdir(parents=True)
        self.main_binary(self.slice(('@rpath/libOpenColorIO.2.4.dylib',),
                                    ('@loader_path/../Frameworks',)))
        with self.assertRaisesRegex(RuntimeError, 'Missing dependency'):
            self.stage()
        self.assertFalse(any(call[0] == 'codesign' for call in self.tool_calls))
        self.assertFalse((self.root / 'stage/PACKAGE.json').exists())

    def test_portable_stage_records_matching_binary_commit_and_input_receipt(self):
        self.main_binary()
        output=self.stage()
        receipt=json.loads((output/'PACKAGE.json').read_text())
        build=json.loads((self.stage_app/'Contents/Resources/Notices/BUILD.json').read_text())
        self.assertTrue(receipt['binary_source_verified'])
        self.assertEqual(receipt['source_commit'],'1234567890abcdef')
        self.assertEqual(build['commit'],receipt['source_commit'])
        with (self.stage_app/'Contents/Info.plist').open('rb') as stream:
            self.assertEqual(plistlib.load(stream)['GyroGradeSourceCommit'],receipt['source_commit'])
        self.assertEqual((self.stage_app/'Contents/Resources/Notices/BUILD-INPUT.json').read_bytes(),
                         (self.root/'build-receipt.json').read_bytes())
        self.assertEqual(receipt['lens_profiles']['errors'],[])
        self.assertEqual(receipt['lens_profiles']['staged']['sha256'],build['lens_profiles']['pin']['sha256'])
        self.assertEqual((self.stage_app/'Contents/Resources/Notices/lens-profiles-v41/LICENSE.txt').read_bytes(),
                         (ROOT/'resources/lens-profiles-v41/LICENSE.txt').read_bytes())

    def test_portable_mac_stage_refuses_a_different_lens_database_before_signing(self):
        self.main_binary()
        presets=self.app/'Contents/Resources/camera_presets';presets.mkdir(parents=True)
        (presets/'profiles.cbor.gz').write_bytes(b'\x1f\x8bnewer upstream db')
        with self.assertRaisesRegex(RuntimeError,'Staged lens profile SHA-256'):
            self.stage()
        self.assertFalse(any(call[0]=='codesign' for call in self.tool_calls))
        self.assertFalse((self.root/'stage/PACKAGE.json').exists())

    def test_binary_replaced_during_copy_is_refused_before_signing(self):
        binary=self.main_binary()
        copy=shutil.copy2
        def changed_copy(source,destination,*args,**kwargs):
            result=copy(source,destination,*args,**kwargs)
            if Path(source)==binary:
                with Path(destination).open('ab') as stream: stream.write(b'replaced executable')
            return result
        with patch.object(stager.shutil,'copy2',side_effect=changed_copy), \
             self.assertRaisesRegex(RuntimeError,'Executable changed during staging'):
            self.stage()
        self.assertFalse(any(call[0]=='codesign' for call in self.tool_calls))
        self.assertFalse((self.root/'stage/PACKAGE.json').exists())

    def test_portable_stage_records_a_missing_weak_load(self):
        self.mdk({'arm64': self.slice(rpaths=('@loader_path/..', '@loader_path/Frameworks'),
                                      weak=('@rpath/libdav1d.7.dylib',))})
        output = self.stage()
        audit = json.loads((output / 'PACKAGE.json').read_text())['mac_runtime_audit']
        self.assertEqual(audit['errors'], [])
        self.assertEqual(audit['optional_weak_missing'],
                         ['@rpath/libdav1d.7.dylib in Contents/Frameworks/mdk.framework/mdk [arm64]'])
        self.assertEqual(len(audit['absent_contained_search_paths']), 1)

    def test_portable_stage_refuses_the_same_load_when_it_is_hard(self):
        self.mdk({'arm64': self.slice(('@rpath/libdav1d.7.dylib',), ('@loader_path/..',))})
        with self.assertRaisesRegex(RuntimeError, "Missing dependency '@rpath/libdav1d.7.dylib'"):
            self.stage()
        self.assertFalse(any(call[0] == 'codesign' for call in self.tool_calls))
        self.assertFalse((self.root / 'stage/PACKAGE.json').exists())

    def test_portable_stage_rejects_external_rpath_even_with_bundled_ocio(self):
        development = self.root / 'SSD/_dev/ocio-runtime/install/lib'
        development.mkdir(parents=True)
        self.main_binary(self.slice(('@rpath/libOpenColorIO.2.4.dylib',),
                                    ('@loader_path/../Frameworks', str(development))))
        self.binary('Contents/Frameworks/libOpenColorIO.2.4.dylib', {'arm64': self.slice()})
        with self.assertRaisesRegex(RuntimeError, 'External runtime path:'):
            self.stage()
        self.assertFalse(any(call[0] == 'codesign' for call in self.tool_calls))

    def test_portable_stage_refuses_false_minimum_without_rewriting_claim(self):
        self.main_binary()
        self.binary('Contents/PlugIns/platforms/libqcocoa.dylib', {'arm64': self.slice(minimum='27.0')})
        with self.assertRaisesRegex(RuntimeError, 'below embedded Mach-O minimum 27.0'):
            self.stage()
        with (self.stage_app / 'Contents/Info.plist').open('rb') as stream:
            self.assertEqual(plistlib.load(stream)['LSMinimumSystemVersion'], '11.0')
        self.assertFalse(any(call[0] == 'codesign' for call in self.tool_calls))

    def test_development_stage_records_floor_and_external_paths_in_both_manifests(self):
        outside = self.binary(self.root / 'homebrew/lib/libImath.dylib', {'arm64': self.slice()})
        self.main_binary(self.slice((str(outside),)))
        self.binary('Contents/PlugIns/platforms/libqcocoa.dylib', {'arm64': self.slice(minimum='27.0')})
        output = self.stage(development=True)
        build = json.loads((self.stage_app / 'Contents/Resources/Notices/BUILD.json').read_text())
        receipt = json.loads((output / 'PACKAGE.json').read_text())
        self.assertEqual(build['mac_runtime_audit'], receipt['mac_runtime_audit'])
        self.assertEqual(receipt['mac_runtime_audit']['maximum_embedded_minimum_macos'], '27.0')
        self.assertIn(str(outside), receipt['mac_runtime_audit']['external_dependencies'])
        self.assertIn('below embedded Mach-O minimum 27.0', '\n'.join(receipt['mac_runtime_audit']['errors']))
        self.assertTrue(receipt['development_runtime'])
        self.assertFalse(receipt['binary_source_verified'])
        self.assertIsNone(receipt['source_commit'])
        self.assertIsNone(build['commit'])
        self.assertIsNone(build['source'])
        self.assertEqual(build['checkout_commit'],'1234567890abcdef')
        with (self.stage_app/'Contents/Info.plist').open('rb') as stream:
            info=plistlib.load(stream)
        self.assertNotIn('GyroGradeSourceCommit',info)
        self.assertEqual(info['GyroGradeCheckoutCommit'],'1234567890abcdef')
        self.assertEqual(info['CFBundleIconFile'],'AppIcon.icns')
        self.assertEqual((self.stage_app/'Contents/Resources/AppIcon.icns').read_bytes(),(ROOT/'resources/gyrograde/AppIcon.icns').read_bytes())
        self.assertFalse(receipt['public_release_approved'])
        check = self.stage_app / 'Contents/Resources/Notices/OpenColorIO-third-party/STAGE-CHECK.json'
        self.assertEqual(json.loads(check.read_text())['errors'], [])


class OcioNoticeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='plus-notice-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / 'repo'
        shutil.copytree(ROOT / PACKET, self.repo / PACKET)
        shutil.copy2(ROOT / 'resources/color/OCIO-LICENSE.txt', self.repo / 'resources/color')
        self.app = self.root / 'GyroGrade'
        self.app.mkdir()

    def check(self):
        notices = self.root / f'Notices-{len(list(self.root.iterdir()))}'
        notices.mkdir()
        with patch.object(stager, 'ROOT', self.repo):
            report = stager.copy_ocio_notices(self.app, notices)
        self.assertTrue((notices / 'OpenColorIO-third-party/expat/COPYING').is_file())
        return report

    def test_packet_matches_its_manifest_and_windows_zlib_pin(self):
        (self.app / 'OpenColorIO_2_4.dll').write_bytes(
            b'MZ synthetic; never executed deflate 1.2.13 Copyright 1995-2022 not well-formed (invalid token)')
        report = self.check()
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['libraries']['OpenColorIO_2_4.dll']['embedded_zlib'], '1.2.13')
        self.assertTrue(report['libraries']['OpenColorIO_2_4.dll']['embedded_expat'])

    def test_other_embedded_zlib_and_changed_notice_are_errors(self):
        (self.app / 'OpenColorIO_2_4.dll').write_bytes(b'MZ synthetic deflate 1.3.1 Copyright 1995-2024')
        (self.repo / PACKET / 'zlib/LICENSE').write_text('edited')
        errors = '\n'.join(self.check()['errors'])
        self.assertIn('embeds zlib 1.3.1; notices are for 1.2.13', errors)
        self.assertIn('Notice missing or changed: zlib/LICENSE', errors)


class LensProfileStagingTests(unittest.TestCase):
    """The lens database is untracked; portable stages must tie it to the pin."""
    DB = b'\x1f\x8bsynthetic lens database'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='plus-lens-stage-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sha = hashlib.sha256(self.DB).hexdigest()
        pin = self.root / 'src/core/lens_profiles.pin'
        pin.parent.mkdir(parents=True)
        pin.write_text('tag=v41\nurl=https://github.com/gyroflow/lens_profiles/releases/download/v41/profiles.cbor.gz\n'
                       f'sha256={self.sha}\n')

    def stage(self, platform, data=DB):
        app = self.root / platform
        path = app / ('Contents/Resources/camera_presets' if platform == 'mac' else 'camera_presets')
        path.mkdir(parents=True)
        if data is not None: (path / 'profiles.cbor.gz').write_bytes(data)
        return app

    def check(self, app, platform, receipt, development=False):
        with patch.object(stager, 'ROOT', self.root):
            return stager.check_lens_profiles(app, platform, receipt, development)

    def receipt(self, **lens):
        return dict(lens_profiles=dict(dict(mode='pinned', sha256=self.sha, bytes=len(self.DB)), **lens))

    def test_pinned_receipt_and_staged_copy_pass_on_both_platforms(self):
        for platform in ('mac', 'windows'):
            with self.subTest(platform=platform):
                report = self.check(self.stage(platform), platform, self.receipt())
                self.assertEqual(report['errors'], [])
                self.assertEqual(report['staged']['sha256'], self.sha)
                self.assertEqual(report['pin']['tag'], 'v41')

    def test_portable_stage_refuses_missing_unpinned_or_changed_database(self):
        cases = [('missing', None, self.receipt(), 'Missing regular lens profile database'),
                 ('legacy', self.DB, dict(commit='a'*40), 'does not record a pinned'),
                 ('latest', self.DB, self.receipt(mode='latest'), 'does not record a pinned'),
                 ('receipt', self.DB, self.receipt(sha256='0'*64), 'Receipt lens profile SHA-256'),
                 ('swapped', b'\x1f\x8bnewer upstream db', self.receipt(), 'Staged lens profile SHA-256')]
        for name, data, receipt, message in cases:
            with self.subTest(case=name), self.assertRaisesRegex(RuntimeError, message):
                self.check(self.stage(name, data), 'windows', receipt)

    def test_symlinked_database_is_not_accepted(self):
        app = self.stage('mac', None)
        target = self.root / 'outside.cbor.gz'; target.write_bytes(self.DB)
        (app / 'Contents/Resources/camera_presets/profiles.cbor.gz').symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, 'Missing regular'):
            self.check(app, 'mac', self.receipt())

    def test_development_stage_records_without_requiring_pin(self):
        report = self.check(self.stage('windows', b'\x1f\x8bdeveloper db'), 'windows', None, development=True)
        self.assertEqual(report['staged']['sha256'], hashlib.sha256(b'\x1f\x8bdeveloper db').hexdigest())
        self.assertIn('Build receipt does not record a pinned lens profile database', report['errors'])


if __name__ == '__main__':
    unittest.main()
