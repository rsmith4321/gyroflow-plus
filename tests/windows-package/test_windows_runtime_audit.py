# SPDX-License-Identifier: GPL-3.0-or-later
"""Rule tests for _scripts/windows_runtime_audit.py using synthetic image facts.

Run: python -m unittest tests/windows-package/test_windows_runtime_audit.py
Needs the pinned pefile only to import the module; no PE files are read.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_scripts'))
import windows_runtime_audit as audit


def image(imports=(), exports=(), ordinals=(), forwarders=(), version=None, linker=(14, 40), dll=True, machine='x64'):
    return dict(machine=machine, dll=dll, linker=linker, warnings=[], file_version=version, forwarders=list(forwarders),
                export_names=list(exports), export_ordinals=list(ordinals),
                imports=[dict(dll=d, delayed=delayed, names=list(names), ordinals=list(numbers))
                         for d, delayed, names, numbers in imports])


CRT = (14, 44, 35211, 0)


def stage(**images):
    images.setdefault('Gyroflow.exe', image(imports=[('kernel32.dll', False, ['ExitProcess'], [])], dll=False))
    return dict(files=[(name, 'file') for name in images], images=images)


def errors(facts, **options):
    return audit.evaluate(facts, 'Gyroflow.exe', **options)['errors']


class Rules(unittest.TestCase):
    def test_clean_stage(self):
        facts = stage(**{'Gyroflow.exe': image(imports=[('foo.dll', False, ['f'], [1]), ('api-ms-win-crt-heap-l1-1-0.dll', False, ['malloc'], [])], dll=False),
                         'foo.dll': image(exports=['f'], ordinals=[1])})
        self.assertEqual(errors(facts), [])

    def test_missing_hard_and_delay_imports_both_fail(self):
        facts = stage(**{'Gyroflow.exe': image(imports=[('a.dll', False, ['x'], []), ('b.dll', True, ['y'], [])], dll=False)})
        found = errors(facts)
        self.assertTrue(any('required a.dll' in e for e in found))
        self.assertTrue(any('delay-loaded b.dll' in e for e in found))

    def test_missing_symbol_and_ordinal(self):
        facts = stage(**{'Gyroflow.exe': image(imports=[('foo.dll', False, ['gone'], [7])], dll=False),
                         'foo.dll': image(exports=['kept'], ordinals=[1])})
        self.assertTrue(any('lacks 2 imported symbols' in e and 'gone' in e and '#7' in e for e in errors(facts)))

    def test_ext_ms_only_as_delay_load(self):
        hard = stage(**{'Gyroflow.exe': image(imports=[('ext-ms-win-foo-l1-1-0.dll', False, ['x'], [])], dll=False)})
        delayed = stage(**{'Gyroflow.exe': image(imports=[('ext-ms-win-foo-l1-1-0.dll', True, ['x'], [])], dll=False)})
        self.assertTrue(errors(hard)); self.assertEqual(errors(delayed), [])

    def test_plugin_imports_resolve_only_from_executable_directory(self):
        facts = stage(**{'platforms/qwindows.dll': image(imports=[('helper.dll', False, ['h'], [])]),
                         'platforms/helper.dll': image(exports=['h'])})
        self.assertTrue(any('platforms/qwindows.dll: required helper.dll' in e for e in errors(facts)))

    def test_subdirectory_dll_shadowing_root(self):
        facts = stage(**{'foo.dll': image(), 'QtQuick/foo.dll': image()})
        self.assertTrue(any('shadows foo.dll' in e for e in errors(facts)))

    def test_staged_system_dll_but_not_d3dcompiler(self):
        self.assertTrue(any('system DLL' in e for e in errors(stage(**{'kernel32.dll': image()}))))
        self.assertEqual(errors(stage(**{'d3dcompiler_47.dll': image()})), [])

    def test_inbox_multimedia_crypto_and_legacy_crt_imports_are_system_dependencies(self):
        for name in ('avicap32.dll','bcryptprimitives.dll','dsound.dll','imagehlp.dll','msvcrt.dll'):
            with self.subTest(name=name):
                facts=stage(**{'Gyroflow.exe':image(imports=[(name,False,['f'],[])],dll=False)})
                self.assertEqual(errors(facts),[])
                self.assertTrue(any('system DLL' in error for error in errors(stage(**{name:image()}))))
        # This classification must not accept the separate app C++ runtime or
        # arbitrary names resembling an in-box dependency.
        for name in ('vcruntime140.dll','msvcp140.dll','msvcrt140.dll','bcryptprimitives-extra.dll'):
            with self.subTest(name=name):
                facts=stage(**{'Gyroflow.exe':image(imports=[(name,False,['f'],[])],dll=False)})
                self.assertTrue(any(f'required {name}' in error for error in errors(facts)))

    def test_case_collision_and_symlink(self):
        facts = stage(**{'Foo.dll': image(), 'foo.dll': image()})
        facts['files'].append(('link.dll', 'symlink'))
        found = errors(facts)
        self.assertTrue(any('case-insensitive' in e for e in found))
        self.assertTrue(any('symbolic links' in e for e in found))

    def test_stale_library_families(self):
        facts = stage(**{'avcodec-62.dll': image(), 'avcodec-63.dll': image(),
                         'OpenColorIO_2_3.dll': image(), 'OpenColorIO_2_4.dll': image(),
                         'opencv_core4.dll': image(), 'opencv_core412.dll': image(),
                         'msvcp140.dll': image(version=CRT), 'msvcp140_1.dll': image(version=CRT)})
        found = errors(facts)
        for family in ('avcodec', 'opencolorio', 'opencv_core'):
            self.assertTrue(any(f'Several {family} versions' in e for e in found), family)
        self.assertFalse(any('msvcp140' in e for e in found))

    def test_forwarder_to_unstaged_module(self):
        facts = stage(**{'foo.dll': image(forwarders=['bar.Thing', 'NTDLL.RtlFoo', 'api-ms-win-core-synch-l1-2-0.Wake'])})
        found = errors(facts)
        self.assertEqual(len(found), 1); self.assertIn('bar.Thing', found[0])

    def test_forwarder_to_missing_symbol_and_ordinal(self):
        facts = stage(**{'foo.dll': image(forwarders=['bar.Thing', 'bar.#8']),
                         'bar.dll': image(exports=['Other'], ordinals=[7])})
        found = errors(facts)
        self.assertEqual(len(found), 2)
        self.assertTrue(all('missing symbol' in error for error in found))

    def test_forwarder_to_exported_symbol_and_ordinal(self):
        facts = stage(**{'foo.dll': image(forwarders=['bar.dll.Thing', 'bar.#8']),
                         'bar.dll': image(exports=['Thing'], ordinals=[8])})
        self.assertEqual(errors(facts), [])

    def test_uppercase_dll_extension_still_requires_a_dll_image(self):
        self.assertTrue(any('not a DLL image' in e for e in errors(stage(**{'broken.DLL': image(dll=False)}))))

    def test_delay_loaded_crt_user_counts(self):
        facts = stage(**{'Gyroflow.exe': image(imports=[('msvcp140.dll', True, ['f'], [])], linker=(14, 44), dll=False),
                         'msvcp140.dll': image(exports=['f'], version=(14, 40, 33810, 0))})
        self.assertTrue(any('older than linker 14.44' in e for e in errors(facts)))

    def test_mixed_and_unversioned_crt(self):
        facts = stage(**{'msvcp140.dll': image(version=CRT), 'vcruntime140.dll': image(version=(14, 42, 1, 0)),
                         'vcomp140.dll': image()})
        found = errors(facts)
        self.assertTrue(any('Mixed C++ runtime' in e for e in found))
        self.assertTrue(any('vcomp140.dll: missing VS_FIXEDFILEINFO' in e for e in found))

    def test_declared_floor(self):
        facts = stage(**{'Gyroflow.exe': image(imports=[('vcruntime140.dll', False, ['f'], [])], linker=(14, 40), dll=False),
                         'vcruntime140.dll': image(exports=['f'], version=(14, 42, 34433, 0))})
        self.assertEqual(errors(facts, redist_floor=(14, 42, 34433, 0)), [])
        self.assertTrue(any('declared toolset floor' in e for e in errors(facts, redist_floor=CRT)))

    def test_native_version_disagreement(self):
        facts = stage(**{'msvcp140.dll': image(version=CRT)})
        native = {'Gyroflow.exe': None, 'msvcp140.dll': (14, 44, 1, 0)}
        self.assertTrue(any('native FileVersion' in e for e in errors(facts, native_versions=native)))

    def test_machine_mismatch_and_parse_failure(self):
        facts = stage(**{'arm.dll': image(machine='arm64'), 'bad.dll': dict(error='not a PE file')})
        found = errors(facts)
        self.assertTrue(any('arm64 image in x64 stage' in e for e in found))
        self.assertTrue(any('Cannot inspect bad.dll' in e for e in found))

    def test_executable_must_be_exe_image(self):
        facts = stage(**{'Gyroflow.exe': image(dll=True)})
        self.assertEqual(errors(facts), ['Missing PE executable: Gyroflow.exe'])

    def test_staged_debug_runtime_is_rejected_in_every_directory(self):
        names = ('ucrtbased.dll', 'vcruntime140d.dll', 'vcruntime140_1d.dll',
                 'msvcp140d.dll', 'msvcp140d_1.dll', 'msvcp140_atomic_waitd.dll',
                 'concrt140d.dll', 'vccorlib140d.dll', 'vcomp140d.dll',
                 'vcamp140d.dll', 'mfc140d.dll', 'mfc140ud.dll',
                 'mfcm140d.dll', 'mfcm140ud.dll', 'msvcrtd.dll', 'msvcr120d.dll',
                 'msvcp140_1d.dll', 'msvcp140_2d.dll', 'msvcp140d_atomic_wait.dll',
                 'msvcp140d_codecvt_ids.dll', 'vcruntime140_threadsd.dll',
                 'mfc42d.dll', 'mfc42ud.dll', 'mfc120ud.dll', 'mfcm120ud.dll', 'msvcm90d.dll',
                 'msvcirtd.dll', 'vcomp120d.dll', 'vccorlib120d.dll', 'vcamp120d.dll')
        for name in names:
            for path in (name, 'plugins/' + name.upper()):
                with self.subTest(path=path):
                    found = errors(stage(**{path: image(version=CRT)}))
                    self.assertTrue(any('debug C++ runtime' in e for e in found), found)

    def test_required_and_delayed_debug_runtime_imports_are_rejected(self):
        for delayed in (False, True):
            for name in ('vcruntime140d.dll', 'ucrtbased.dll'):
                with self.subTest(name=name, delayed=delayed):
                    facts = stage(**{'Gyroflow.exe': image(imports=[(name, delayed, ['f'], [])], dll=False),
                                     name: image(exports=['f'], version=CRT)})
                    self.assertTrue(any('imports debug C++ runtime' in e for e in errors(facts)))

    def test_export_forwarder_cannot_hide_debug_runtime(self):
        facts = stage(**{'foo.dll': image(forwarders=['VCRUNTIME140D.f', 'ucrtbased.dll.#7']),
                         'vcruntime140d.dll': image(exports=['f'], version=CRT),
                         'ucrtbased.dll': image(ordinals=[7], version=CRT)})
        found = errors(facts)
        self.assertEqual(sum('forwards to debug C++ runtime' in e for e in found), 2)

    def test_release_runtime_names_remain_allowed(self):
        names = ('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll',
                 'msvcp140_1.dll', 'msvcp140_codecvt_ids.dll', 'msvcp140_atomic_wait.dll',
                 'concrt140.dll', 'vccorlib140.dll', 'vcomp140.dll',
                 'mfc140.dll', 'mfc140u.dll', 'mfcm140u.dll', 'my_debug_tool.dll',
                 'mfc42.dll', 'mfc42u.dll', 'mfc120u.dll', 'msvcp120.dll', 'msvcr120.dll',
                 'msvcm90.dll', 'msvcirt.dll', 'vcomp120.dll', 'vccorlib120.dll', 'vcamp120.dll',
                 'opencv_world4100d_helper.dll')
        for name in names:
            with self.subTest(name=name):
                facts = stage(**{'Gyroflow.exe': image(imports=[(name, False, ['f'], [])], dll=False),
                                 name: image(exports=['f'], version=CRT)})
                self.assertEqual(errors(facts), [])


if __name__ == '__main__':
    unittest.main()
