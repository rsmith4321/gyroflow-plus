#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local synthetic repositories only; no network."""
import contextlib, hashlib, importlib.util, io, json, os, subprocess, sys, tarfile, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('builder', HERE/'build_ffmpeg_source_bundle.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
HEADER = 'component\trole\tbtbn_script\tpinned_ref\tresolved_commit\tfetched_from\tprimary_or_mirror\tstatus\tnotice_files\n'


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class SourceBundleBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='plus-ffmpeg-source-')
        self.root = Path(self.temporary.name)
        self.repo = self.root/'upstream'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        (self.repo/'COPYING').write_text('synthetic licence\n')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-q', '-m', 'pinned')
        self.pinned = git(self.repo, 'rev-parse', 'HEAD')
        (self.repo/'COPYING').write_text('later change, not part of the pin\n')
        git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-q', '-am', 'later')
        self.tree = self.root/'tree'
        (self.tree/'ffmpeg/provenance').mkdir(parents=True)
        (self.tree/'MANIFEST.json').write_text(json.dumps(dict(components=dict(ffmpeg=dict(identity=dict(
            ffmpeg_commit='f'*40, btbn_commit='b'*40, archive_sha256='a'*64))))))
        rows = [f'ffmpeg\tdirect\t\t{self.pinned[:10]}\t{self.pinned}\t{self.repo}\tpinned-url\tcollected\tCOPYING',
                'xvidcore\tdep\t\tr2204\t\t\t\tGAP:svn-not-fetched\t',
                'unknown\tdep\t\tv1\t\t\t\tGAP:fetch-failed\t']
        (self.tree/builder.INDEX).write_text(HEADER + '\n'.join(rows) + '\n')

    def tearDown(self):
        self.temporary.cleanup()

    def run_builder(self):
        # Relative cache and output paths, as a user would pass them.
        argv = ['build', str(self.tree), 'cache', 'out', '--jobs', '2']
        saved, sys.argv, cwd = sys.argv, argv, os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = builder.main()
        finally:
            sys.argv = saved
            os.chdir(cwd)
        return self.root/'out', code

    def test_pinned_tree_is_archived_and_missing_components_are_listed(self):
        output, code = self.run_builder()
        self.assertEqual(code, 4)
        index = json.loads((output/'SOURCE-INDEX.json').read_text())
        self.assertFalse(index['complete'])
        self.assertFalse(index['public_release_approved'])
        self.assertEqual([m['component'] for m in index['missing']], ['xvidcore', 'unknown'])
        entry = index['components'][0]
        archive = output/entry['archive']
        self.assertEqual(entry['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
        with tarfile.open(archive) as tar:
            data = tar.extractfile(f'ffmpeg-{self.pinned[:12]}/COPYING').read()
        self.assertEqual(data, b'synthetic licence\n')
        bundle = output/'FFmpeg-ffffffffff-corresponding-source.tar'
        with tarfile.open(bundle) as tar:
            names = tar.getnames()
        self.assertIn('FFmpeg-ffffffffff-corresponding-source/SOURCE-INDEX.json', names)
        self.assertIn(f'FFmpeg-ffffffffff-corresponding-source/{entry["archive"]}', names)

    def test_rerun_reuses_archives_and_is_reproducible(self):
        output, _ = self.run_builder()
        first = (output/'FFmpeg-ffffffffff-corresponding-source.tar').read_bytes()
        output, _ = self.run_builder()
        self.assertEqual((output/'FFmpeg-ffffffffff-corresponding-source.tar').read_bytes(), first)

    def test_unsafe_component_name_is_refused(self):
        (self.tree/builder.INDEX).write_text(HEADER + f'../x\tdep\t\tv1\t{self.pinned}\t{self.repo}\t\tcollected\t\n')
        with self.assertRaises(ValueError):
            builder.components(self.tree)

    def test_deterministic_export_archive(self):
        source = self.root/'export'
        (source/'sub').mkdir(parents=True)
        (source/'sub/file.txt').write_text('x')
        first, second = self.root/'a.tar.gz', self.root/'b.tar.gz'
        builder.deterministic_tar_gz(source, 'lame-r6835/', first)
        (source/'sub/file.txt').touch()
        builder.deterministic_tar_gz(source, 'lame-r6835/', second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with tarfile.open(first) as tar:
            self.assertEqual(tar.getnames(), ['lame-r6835', 'lame-r6835/sub', 'lame-r6835/sub/file.txt'])


if __name__ == '__main__':
    unittest.main()
