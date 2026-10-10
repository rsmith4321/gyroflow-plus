#!/usr/bin/env python3
"""Test our archive acquisition using stdlib data fixtures; never execute upstream source."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('libass_archive_candidate', HERE/'rebuild_libass_windows.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sha = lambda data: hashlib.sha256(data).hexdigest()


def archive_row(entries, index=0):
    location, repository, commit = m.SOURCES[index]
    root = 'source-'+str(index)
    out = io.BytesIO()
    links = []
    total = 0
    with tarfile.open(fileobj=out, mode='w:gz') as tar:
        top = tarfile.TarInfo(root); top.type = tarfile.DIRTYPE; tar.addfile(top)
        for name, content, kind in entries:
            info = tarfile.TarInfo(root+'/'+name)
            if kind == 'file':
                info.size = len(content); total += info.size; tar.addfile(info, io.BytesIO(content))
            elif kind == 'symlink':
                info.type = tarfile.SYMTYPE; info.linkname = content
                links.append({'name':info.name, 'target':content}); tar.addfile(info)
            elif kind == 'hardlink':
                info.type = tarfile.LNKTYPE; info.linkname = content; tar.addfile(info)
    data = out.getvalue()
    return data, {'location':location,'repository':repository,'commit':commit,'archive':str(index)+'.tar.gz',
                  'bytes':len(data),'sha256':sha(data),'root':root,'archive_members':len(entries)+1,
                  'link_members':links,'uncompressed_file_bytes':total}


def fixture_bundle(folder, change=None, compression=zipfile.ZIP_STORED):
    pairs = [archive_row([('data.txt', b'data', 'file')], i) for i in range(len(m.SOURCES))]
    if change:
        change(pairs)
    p = folder/'bundle.zip'
    with zipfile.ZipFile(p, 'w', compression=compression) as z:
        for data, row in pairs:
            z.writestr(row['archive'], data)
    return p, {'source_bundle':{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())},'archives':[row for _,row in pairs]}


class ArchiveAcquisition(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root/'work'; self.work.mkdir()
        for name in ('Popen','run','call','check_call','check_output'):
            guard = mock.patch.object(subprocess, name, side_effect=AssertionError('External execution forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def test_default_admission_still_requires_git_workflow(self):
        # Both modes bind to their own exact workflow; never fake provider environment identity.
        env = {'GITHUB_WORKFLOW_REF':m.REPOSITORY+'/'+m.ARCHIVE_WORKFLOW+'@refs/heads/'+m.BRANCH}
        self.assertIn('GITHUB_WORKFLOW_REF', m.admission_errors(env, 'win32'))
        env[m.SOURCE_MODE] = 'archives'
        self.assertNotIn('GITHUB_WORKFLOW_REF', m.admission_errors(env, 'win32'))
        env[m.SOURCE_MODE] = 'anything'
        self.assertIn(m.SOURCE_MODE, m.admission_errors(env, 'win32'))

    def test_real_stdlib_extract_assembles_twelve_locations(self):
        bundle, manifest = fixture_bundle(self.root)
        records = m.extract_source_bundle(bundle, self.work, manifest)
        self.assertEqual(len(records), 12)
        for location, _, _ in m.SOURCES:
            self.assertEqual((self.work/location/'data.txt').read_bytes(), b'data')

    def test_bundle_mismatch_refuses_before_source_writes(self):
        bundle, manifest = fixture_bundle(self.root)
        manifest['source_bundle']['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'bundle size/hash'):
            m.extract_source_bundle(bundle, self.work, manifest)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_source_pin_mismatch_refuses_before_source_writes(self):
        bundle, manifest = fixture_bundle(self.root)
        manifest['archives'][0]['commit'] = '0'*40
        with self.assertRaisesRegex(ValueError, 'pins differ'):
            m.extract_source_bundle(bundle, self.work, manifest)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_inner_hash_mismatch_refuses_before_source_writes(self):
        bundle, manifest = fixture_bundle(self.root)
        manifest['archives'][-1]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'archive size/hash'):
            m.extract_source_bundle(bundle, self.work, manifest)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_compressed_zip_members_refused(self):
        bundle, manifest = fixture_bundle(self.root, compression=zipfile.ZIP_DEFLATED)
        with self.assertRaisesRegex(ValueError, 'ZIP members'):
            m.extract_source_bundle(bundle, self.work, manifest)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_nonempty_existing_destination_preserved(self):
        bundle, manifest = fixture_bundle(self.root)
        target = self.work/'devpkgs'; target.mkdir(); (target/'authored').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'not empty'):
            m.extract_source_bundle(bundle, self.work, manifest)
        self.assertEqual((target/'authored').read_bytes(), b'keep')

    def test_unsafe_duplicate_and_reserved_paths(self):
        for names in [('x/../../escape',), ('C:escape',), ('x\\escape',), ('.git/config',),
                      ('NUL.txt',), ('COM1.log',), ('bad.','okay'), ('bad ',), ('same','SAME')]:
            with self.subTest(names=names):
                data, row = archive_row([(n,b'x','file') for n in names])
                with self.assertRaises(ValueError):
                    m.inspect_source_archive(data, row)

    def test_hardlink_unregistered_symlink_counts_and_sizes_refused(self):
        data, row = archive_row([('linked','target','hardlink')])
        with self.assertRaisesRegex(ValueError, 'member type'): m.inspect_source_archive(data, row)
        data, row = archive_row([('linked','target','symlink')]); row['link_members'] = []
        with self.assertRaisesRegex(ValueError, 'links'): m.inspect_source_archive(data, row)
        data, row = archive_row([('normal',b'x','file')]); row['archive_members'] += 1
        with self.assertRaisesRegex(ValueError, 'member count'): m.inspect_source_archive(data, row)
        row['archive_members'] -= 1; row['uncompressed_file_bytes'] += 1
        with self.assertRaisesRegex(ValueError, 'uncompressed size'): m.inspect_source_archive(data, row)

    def test_standard_windows_link_copy_fallback_is_recorded(self):
        def change(pairs):
            pairs[4] = archive_row([('AGENTS.md',b'inert source document','file'),
                                    ('CLAUDE.md','AGENTS.md','symlink')],4)
        bundle, manifest = fixture_bundle(self.root, change)
        with mock.patch.object(os, 'symlink', side_effect=OSError('No symlink privilege')):
            records = m.extract_source_bundle(bundle, self.work, manifest)
        self.assertEqual(records[4]['links'][0]['materialized_as'], 'target-content copy')
        self.assertEqual((self.work/m.SOURCES[4][0]/'CLAUDE.md').read_bytes(), b'inert source document')

    @unittest.skipUnless(os.environ.get('V18_SOURCE_BUNDLE'), 'Set V18_SOURCE_BUNDLE for exact retained source-data fixture')
    def test_twelve_real_archives_unicode_and_nasm_headers_without_execution(self):
        environ = {'RUNNER_TEMP':str(self.work),'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1',
                   m.SOURCE_MODE:'archives','LIBASS_SOURCE_BUNDLE':os.environ['V18_SOURCE_BUNDLE']}
        runner = m.Run(self.root, environ=environ)
        runner.acquire()
        self.assertEqual(len(runner.sources),12)
        self.assertEqual(runner.commands, [])
        m.nasm_configuration(runner.work/'nasm')
        self.assertFalse(any(p.name.casefold()=='.git' for p in runner.work.rglob('*')))
        records = json.loads((runner.evidence/'ARCHIVE-ACQUISITION.json').read_text())
        self.assertFalse(records['git_checkout_used'])
        self.assertFalse(records['network_isolation_enforced'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
