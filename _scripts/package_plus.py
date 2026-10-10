#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage the community fork from an explicitly prepared desktop runtime.

Does not install, publish, register file associations, or use upstream Store
identities. All staging requires a clean source checkout; portable staging also
requires supplied dependency notices. --development-runtime permits local dependency paths and
records that the result is not a redistributable release.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def msvc_version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', value):
        raise argparse.ArgumentTypeError('Use the full MSVC redistributable FileVersion, e.g. 14.44.35211.0')
    return tuple(map(int, value.split('.')))


def sha256_hex(value):
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise argparse.ArgumentTypeError('Use a lowercase 64-character SHA-256')
    return value


def copy_qmetaobject_notices(notices):
    """Retain the pinned derive dependency's license and downstream patch record."""
    target = notices/'qmetaobject-rs'
    target.mkdir()
    for name in ('LICENSE', 'PATCHES.md', 'UPSTREAM.json'):
        shutil.copy2(ROOT/'vendor/qmetaobject-rs'/name, target/name)


def copy_ffmpeg_sys_notices(notices):
    """Retain the published binding crate's license declaration and exact patch."""
    target = notices/'ffmpeg-sys-next'
    target.mkdir()
    for name in ('README.md', 'Cargo.toml.orig'):
        shutil.copy2(ROOT/'vendor/ffmpeg-sys-next-9.0.0'/name, target/name)
    shutil.copy2(ROOT/'vendor/README.md', target/'PROVENANCE.md')
    shutil.copy2(ROOT/'vendor/ffmpeg-sys-next-9.0.0.patch', target/'PATCH.diff')


def bind_native_notices(dependencies, manifest_sha256):
    """Identify the reviewed native notice tree a Windows stage carries.

    Exactly one MANIFEST.json inside the copied --licenses tree must match the
    pin. Integrity must pass; the release-complete result (3 while recorded
    gaps remain) is recorded, never treated as approval."""
    sha=lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report=dict(manifest_sha256=manifest_sha256,manifest_path=None,integrity_exit=None,
        release_complete_exit=None,errors=[])
    found=[p for p in sorted(dependencies.rglob('MANIFEST.json')) if p.is_file() and sha(p)==manifest_sha256] \
        if dependencies.is_dir() else []
    if len(found)!=1:
        report['errors'].append(f'Expected one native notice MANIFEST.json with SHA-256 {manifest_sha256} '
                                f'in the supplied notices; found {len(found)}')
    else:
        report['manifest_path']=found[0].relative_to(dependencies).as_posix()
        verify=[sys.executable,'-I',str(ROOT/'_scripts/notices/verify_native_notices.py'),str(found[0].parent),
                '--repo-root',str(ROOT),'--manifest-sha256',manifest_sha256]
        report['integrity_exit']=subprocess.run(verify,capture_output=True).returncode
        report['release_complete_exit']=subprocess.run(verify+['--require-release-complete'],capture_output=True).returncode
        if report['integrity_exit']!=0:
            report['errors'].append(f'Native notice integrity check exited {report["integrity_exit"]}')
    return report


SOURCE_BUNDLES=('qt','libass','ffmpeg','mdk-ffmpeg9')


def source_bundle(value):
    name,sep,path=value.partition('=')
    if not sep or name not in SOURCE_BUNDLES or not path:
        raise argparse.ArgumentTypeError(f'Use NAME=PATH with NAME one of {", ".join(SOURCE_BUNDLES)}')
    return name,Path(path)


def expected_source_bundles(tree):
    """Source-bundle identities the reviewed native notice tree records."""
    expected={}
    for line in (tree.glob('qt-*/source-bundle.sha256') if tree else []):
        for digest,_,file in (row.partition('  ') for row in line.read_text().splitlines() if row.strip()):
            expected['qt']=dict(file=file,sha256=digest)
    for record in (tree.glob('mdk-*/bundled/evidence/LIBASS-SOURCE-QUALIFICATION.json') if tree else []):
        kit=json.loads(record.read_text()).get('retained_source_kit') or {}
        if kit.get('sha256'): expected['libass']=dict(file=kit.get('file'),sha256=kit['sha256'])
    return expected


def stage_source_bundles(bundles, destination, tree):
    """Copy corresponding-source bundles beside the stage and check recorded identities.

    Delivery is complete only when every required bundle is present and every
    recorded identity matches; otherwise it stays open, which is never approval."""
    expected=expected_source_bundles(tree)
    report={name:None for name in SOURCE_BUNDLES};errors=[]
    for name,path in bundles:
        if report[name] is not None:
            errors.append(f'Source bundle {name} supplied more than once');continue
        path=path.resolve(strict=True);destination.mkdir(exist_ok=True)
        target=destination/path.name
        if target.exists():
            errors.append(f'Source bundle file name {path.name} is already used');continue
        shutil.copy2(path,target)
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        want=expected.get(name,{}).get('sha256')
        report[name]=dict(file=f'{destination.name}/{path.name}',bytes=target.stat().st_size,sha256=digest,
                          expected_sha256=want)
        if want and digest!=want:
            errors.append(f'Source bundle {name} SHA-256 {digest} does not match the recorded {want}')
    complete=all(report[name] for name in SOURCE_BUNDLES) and not errors
    report['delivery']='beside-package' if complete else 'open'
    return report,errors


def copy_ocio_notices(app, notices):
    """Copy the OCIO dependency notice packet after checking it against its manifest.

    A staged OCIO library embedding a zlib other than the packet's pin is an
    error. Embedded Expat has no version string and is recorded for review."""
    packet = ROOT/'resources/color/ocio-third-party'
    manifest = json.loads((packet/'manifest.json').read_text())
    report = dict(errors=[], libraries={})
    for item in manifest['notice_files']:
        path = packet/item['path']
        if not path.is_file() or path.stat().st_size != item['bytes'] or \
                hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            report['errors'].append(f'Notice missing or changed: {item["path"]}')
    zlib = next(pin['ref'].lstrip('v') for pin in manifest['pins'] if pin['component'] == 'zlib')
    for library in sorted(app.rglob('*OpenColorIO*')):
        if library.is_symlink() or not library.is_file() or library.suffix.lower() not in ('.dll', '.dylib'):
            continue
        data = library.read_bytes()
        embedded = re.search(rb' deflate (\d+\.\d+\.\d+) Copyright ', data)
        facts = dict(sha256=hashlib.sha256(data).hexdigest(),
                     embedded_zlib=embedded.group(1).decode() if embedded else None,
                     embedded_expat=b'not well-formed (invalid token)' in data)
        report['libraries'][library.relative_to(app).as_posix()] = facts
        if facts['embedded_zlib'] not in (None, zlib):
            report['errors'].append(f'{library.name} embeds zlib {facts["embedded_zlib"]}; notices are for {zlib}')
    shutil.copytree(packet, notices/'OpenColorIO-third-party')
    (notices/'OpenColorIO-third-party/STAGE-CHECK.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def read_lens_pin(root):
    spec = importlib.util.spec_from_file_location('build_plus', Path(__file__).with_name('build_plus.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.read_lens_pin(root)


def check_lens_profiles(app, platform, receipt, development):
    """Tie the staged, untracked lens database to the build receipt and the tracked pin.

    The database is not in the git archive, the executable hash or Cargo.lock.
    Development stages record what they contain; portable stages require the pin."""
    relative = 'Contents/Resources/camera_presets/profiles.cbor.gz' if platform == 'mac' else 'camera_presets/profiles.cbor.gz'
    staged = app/relative
    facts = dict(path=relative, sha256=None, bytes=None)
    if staged.is_file() and not staged.is_symlink():
        data = staged.read_bytes()
        facts.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    build = receipt.get('lens_profiles') if isinstance(receipt, dict) else None
    errors, pin = [], None
    if facts['sha256'] is None: errors.append(f'Missing regular lens profile database {relative}')
    if not isinstance(build, dict) or build.get('mode') != 'pinned':
        errors.append('Build receipt does not record a pinned lens profile database')
    else:
        try: pin = read_lens_pin(ROOT)
        except (OSError, RuntimeError, UnicodeDecodeError) as failure: errors.append(f'Cannot read lens profile pin: {failure}')
        if pin and build.get('sha256') != pin['sha256']:
            errors.append(f'Receipt lens profile SHA-256 {build.get("sha256")} is not pinned {pin["sha256"]}')
        if pin and facts['sha256'] not in (None, pin['sha256']):
            errors.append(f'Staged lens profile SHA-256 {facts["sha256"]} is not pinned {pin["sha256"]}')
    report = dict(staged=facts, build=build, pin=pin, errors=errors)
    if not development and errors:
        raise RuntimeError('Lens profile input check failed: '+'; '.join(errors))
    return report


MACHO_MAGIC = {bytes.fromhex(value) for value in
               ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe',
                'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}
DYLIB_COMMANDS = {'LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB',
                  'LC_LAZY_LOAD_DYLIB', 'LC_LOAD_UPWARD_DYLIB'}


def macos_version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+){0,2}', value):
        raise ValueError(f'Invalid macOS minimum version: {value!r}')
    return tuple((list(map(int, value.split('.'))) + [0, 0])[:3])


def read_macho(path):
    """Read each slice explicitly; architecture headers and dylib IDs are not loads."""
    with path.open('rb') as stream:
        if stream.read(4) not in MACHO_MAGIC:
            return {}
    def run(*args):
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f'Cannot inspect {path}: {result.stderr.strip()}')
        return result.stdout
    architectures = run('lipo', '-archs', str(path)).split()
    if not architectures:
        raise RuntimeError(f'No Mach-O architectures in {path}')
    slices = {}
    for architecture in architectures:
        loads, weak, rpaths, minimums = [], [], [], []
        output = run('otool', '-arch', architecture, '-l', str(path))
        for block in re.split(r'\nLoad command \d+\n', output):
            command = re.search(r'^\s*cmd\s+(\S+)\s*$', block, re.M)
            if not command: continue
            command = command.group(1)
            if command in DYLIB_COMMANDS or command == 'LC_RPATH':
                field = 'path' if command == 'LC_RPATH' else 'name'
                value = re.search(r'^\s*' + field + r'\s+(.+?)\s+\(offset \d+\)\s*$', block, re.M)
                if not value: raise RuntimeError(f'Malformed {command} in {path} [{architecture}]')
                # dyld skips a missing weak library; every other load is required.
                (rpaths if command == 'LC_RPATH' else weak if command == 'LC_LOAD_WEAK_DYLIB'
                 else loads).append(value.group(1))
            elif command in ('LC_BUILD_VERSION', 'LC_VERSION_MIN_MACOSX'):
                if command == 'LC_BUILD_VERSION':
                    platform = re.search(r'^\s*platform\s+(\S+)\s*$', block, re.M)
                    if not platform or platform.group(1) not in ('1', 'MACOS'):
                        raise RuntimeError(f'Non-macOS slice in {path} [{architecture}]')
                field = 'minos' if command == 'LC_BUILD_VERSION' else 'version'
                value = re.search(r'^\s*' + field + r'\s+(\S+)\s*$', block, re.M)
                if not value: raise RuntimeError(f'Missing macOS minimum in {path} [{architecture}]')
                macos_version(value.group(1))
                minimums.append(value.group(1))
        if len(minimums) != 1:
            raise RuntimeError(f'Expected one macOS minimum in {path} [{architecture}]')
        slices[architecture] = dict(dependencies=loads, weak_dependencies=weak, rpaths=rpaths,
                                    minimum_macos=minimums[0])
    return slices


def check_mac_dependencies(app):
    """Resolve the bundle and its transitive loads without trusting the host's paths.

    Development-only external loads are inspected but never count toward the
    embedded deployment floor. Apple shared-cache libraries need not be on disk.
    Absent weak libraries and absent in-bundle run-path directories are what
    dyld skips; they are reported separately and are not closure errors. A
    weak library that is present is audited like any other.
    """
    app = app.resolve(strict=True)
    executable = app / 'Contents/MacOS/gyroflow'
    external, errors, inventory, inspected, embedded_minimums = set(), set(), set(), {}, {}
    optional_weak_missing, absent_search_paths = set(), set()
    def contained(path): return path.is_relative_to(app)
    def shown(path): return path.relative_to(app) if contained(path) else path
    def system(path): return path.is_relative_to('/usr/lib') or path.is_relative_to('/System/Library')
    def expand(value, loader):
        for prefix, base in (('@loader_path', loader.parent), ('@executable_path', executable.parent)):
            if value == prefix or value.startswith(prefix + '/'):
                return (base / value[len(prefix):].lstrip('/')).resolve()
        return Path(value).resolve() if value.startswith('/') else None
    def inspect(path):
        if path not in inspected:
            try: inspected[path] = read_macho(path)
            except (OSError, RuntimeError, ValueError) as failure:
                errors.add(str(failure)); inspected[path] = {}
            if contained(path):
                for architecture, data in inspected[path].items():
                    embedded_minimums[f'{path.relative_to(app)} [{architecture}]'] = data['minimum_macos']
        return inspected[path]
    for path in app.rglob('*'):
        try: resolved = path.resolve()
        except (OSError, RuntimeError) as failure:
            errors.add(f'Invalid bundle path {path}: {failure}'); continue
        if path.is_symlink() and (not contained(resolved) or not path.exists()):
            external.add(str(path) + ' -> ' + str(resolved))
            if not path.exists(): errors.add(f'Broken bundle symlink: {path}')
        if path.is_file() and contained(resolved): inventory.add(resolved)
    for path in sorted(inventory): inspect(path)
    main = inspect(executable)
    if not main: errors.add(f'Missing Mach-O application executable: {executable}')
    def runpaths(path, architecture, inherited):
        result = []
        for value in inspect(path).get(architecture, {}).get('rpaths', []):
            try: resolved = expand(value, path)
            except (OSError, RuntimeError) as failure:
                errors.add(f'Invalid LC_RPATH {value!r} in {path}: {failure}'); continue
            if resolved is None:
                errors.add(f'Unresolvable LC_RPATH {value!r} in {path} [{architecture}]'); continue
            if not contained(resolved) and not system(resolved): external.add(str(resolved))
            if not resolved.is_dir() and not system(resolved):
                if contained(resolved):
                    absent_search_paths.add(f'{value} ({shown(resolved)}) in {shown(path)} [{architecture}]')
                else:
                    errors.add(f'Missing LC_RPATH directory {resolved} in {path} [{architecture}]')
            result.append(resolved)
        return tuple(dict.fromkeys(result + list(inherited)))
    visited, reached = set(), set()
    def visit(path, architecture, inherited):
        data = inspect(path).get(architecture)
        if not data:
            errors.add(f'Missing {architecture} Mach-O slice: {path}'); return
        paths = runpaths(path, architecture, inherited)
        key = (path, architecture, paths)
        if key in visited: return
        if len(visited) >= 4096:
            errors.add('Too many distinct Mach-O loader contexts to audit safely'); return
        visited.add(key)
        reached.add((path, architecture))
        for value, weak in ([(value, False) for value in data['dependencies']] +
                            [(value, True) for value in data['weak_dependencies']]):
            if any(part in ('QTKit.framework', 'VideoDecodeAcceleration.framework')
                   for part in Path(value).parts):
                errors.add(f'Obsolete FFmpeg framework dependency {value!r} in {path} [{architecture}]')
            if value.startswith('@rpath/'):
                candidates = [directory / value[len('@rpath/'):] for directory in paths]
            else:
                candidate = expand(value, path)
                candidates = [candidate] if candidate is not None else []
            resolved = None
            for candidate in candidates:
                try: candidate = candidate.resolve()
                except (OSError, RuntimeError) as failure:
                    errors.add(f'Invalid dependency {value!r} in {path}: {failure}'); continue
                if system(candidate) or candidate.is_file():
                    resolved = candidate; break
            if resolved is None:
                if not weak:
                    errors.add(f'Missing dependency {value!r} in {path} [{architecture}]'); continue
                # A user's machine could supply an outside path, including
                # one reached by parent traversal in an @rpath load.
                outside = []
                for candidate in candidates:
                    try: candidate = candidate.resolve()
                    except (OSError, RuntimeError): continue  # Invalid dependency recorded above.
                    if not contained(candidate) and not system(candidate):
                        outside.append(str(candidate))
                external.update(outside)
                if not outside:
                    optional_weak_missing.add(f'{value} in {shown(path)} [{architecture}]')
                continue
            if system(resolved): continue
            if not contained(resolved): external.add(str(resolved))
            visit(resolved, architecture, paths)
    for architecture in main:
        visit(executable, architecture, ())
    # Plugins are loaded dynamically. Audit their closure against the same
    # executable run paths even when no LC_LOAD_DYLIB refers to the plugin.
    # Visit plugin entry points before orphan libraries. A shared dependency
    # reached from a plugin must retain that caller's run-path stack, and may
    # be reached again from another plugin with a different stack.
    def plugin_first(path):
        return (not any(part in ('PlugIns', 'plugins', 'qml') for part in path.relative_to(app).parts), path)
    for path in sorted(inventory, key=plugin_first):
        for architecture in inspect(path):
            if (path, architecture) not in reached:
                visit(path, architecture, runpaths(executable, architecture, ()))
    floor = max(embedded_minimums.values(), key=macos_version, default=None)
    return dict(external_dependencies=sorted(external), errors=sorted(errors),
                optional_weak_missing=sorted(optional_weak_missing),
                absent_contained_search_paths=sorted(absent_search_paths),
                maximum_embedded_minimum_macos=floor, embedded_minimum_macos=embedded_minimums)


def check_mac_minimum(report, info):
    """Fail an inaccurate deployment claim instead of silently changing support."""
    base = info.get('LSMinimumSystemVersion')
    by_architecture = info.get('LSMinimumSystemVersionByArchitecture', {})
    if not isinstance(by_architecture, dict):
        report['errors'].append('Invalid LSMinimumSystemVersionByArchitecture mapping'); return
    if base is not None:
        try: macos_version(base)
        except ValueError as failure: report['errors'].append(str(failure))
    floors = {}
    for key, minimum in report['embedded_minimum_macos'].items():
        architecture = key.rsplit('[', 1)[1][:-1]
        floors[architecture] = max(floors.get(architecture, minimum), minimum, key=macos_version)
    claims = {}
    for architecture, minimum in sorted(floors.items()):
        value = by_architecture.get(architecture, base)
        try: claimed = macos_version(value)
        except ValueError as failure:
            report['errors'].append(f'{architecture}: {failure}'); continue
        claims[architecture] = value
        if claimed < macos_version(minimum):
            field = 'LSMinimumSystemVersionByArchitecture' if architecture in by_architecture else 'LSMinimumSystemVersion'
            report['errors'].append(f'{field} {architecture} {value} is below embedded Mach-O minimum {minimum}')
    report['claimed_minimum_macos_by_architecture'] = claims


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform',choices=['mac','windows'])
    parser.add_argument('runtime',type=Path,help='prepared .app or portable Windows directory')
    parser.add_argument('output',type=Path,help='new, nonexistent staging directory')
    parser.add_argument('--binary',type=Path,required=True,help='built from this source checkout')
    parser.add_argument('--licenses',type=Path,help='dependency copyright/license texts and source/build provenance')
    parser.add_argument('--development-runtime',action='store_true')
    parser.add_argument('--deploy-receipt',type=Path,help='Mac: build_plus.py receipt; Windows: win64-deploy.json written by just deploy')
    parser.add_argument('--msvc-redist-floor',type=msvc_version,help='Windows: required C++ redistributable FileVersion for the newest toolset among staged components, e.g. 14.44.35211.0')
    parser.add_argument('--native-notices-sha256',type=sha256_hex,help='Windows: SHA-256 of the reviewed native notice MANIFEST.json inside --licenses')
    parser.add_argument('--source-bundle',type=source_bundle,action='append',default=[],metavar='NAME=PATH',
        help=f'Windows: corresponding-source bundle copied beside the stage; NAME is one of {", ".join(SOURCE_BUNDLES)}')
    args=parser.parse_args()
    runtime=args.runtime.resolve(strict=True);binary=args.binary.resolve(strict=True)
    output=args.output.resolve()
    if output.exists(): parser.error('Output already exists; use a fresh staging directory')
    dirty=bool(git('status','--porcelain').strip())
    if dirty: parser.error('All staging requires committed source, including newly added files')
    if args.source_bundle and args.platform!='windows': parser.error('--source-bundle applies to Windows stages')
    if args.source_bundle and not args.native_notices_sha256:
        parser.error('--source-bundle requires --native-notices-sha256 to identify the recorded bundles')
    for name,path in args.source_bundle:
        if not path.is_file(): parser.error(f'Source bundle {name} is not a file: {path}')
    if not args.development_runtime and not args.licenses: parser.error('Supply dependency notices/provenance with --licenses')
    version=tomllib.loads((ROOT/'Cargo.toml').read_text())['package']['version']
    commit=git('rev-parse','HEAD').decode().strip()
    mac_audit = windows_audit = None
    receipt_in = receipt_bytes = None
    binary_hash=hashlib.sha256(binary.read_bytes()).hexdigest()
    if not args.development_runtime and not args.deploy_receipt:
        parser.error('Portable stages require --deploy-receipt matching the executable and source commit')
    if args.deploy_receipt:
        try:
            receipt_bytes=args.deploy_receipt.read_bytes()
            receipt_in=json.loads(receipt_bytes)
            matches=(isinstance(receipt_in,dict) and receipt_in.get('commit')==commit
                and receipt_in.get('dirty') is False and receipt_in.get('exe_sha256')==binary_hash
                and (args.platform!='mac' or receipt_in.get('platform')=='mac'))
        except (OSError,ValueError) as failure:
            parser.error(f'Cannot read build receipt: {failure}')
        if not matches:
            parser.error('Build receipt and --binary must be one clean build of this commit and platform')
    binary_commit=commit if receipt_in is not None else None
    if args.platform=='windows' and not args.development_runtime:
        if not args.msvc_redist_floor:
            parser.error('Windows stages require --deploy-receipt and --msvc-redist-floor')
        if not args.native_notices_sha256:
            parser.error('Windows stages require --native-notices-sha256 for the supplied native notice tree')
        runtime_exe=runtime/'Gyroflow.exe'
        if not runtime_exe.is_file() or hashlib.sha256(runtime_exe.read_bytes()).hexdigest()!=binary_hash:
            parser.error('Deploy receipt, --binary and runtime Gyroflow.exe must be one clean build of this commit')
    output.mkdir(parents=True)
    if args.platform=='mac':
        app=output/'GyroGrade.app'
        shutil.copytree(runtime,app,symlinks=True)
        shutil.rmtree(app/'Contents/_CodeSignature',ignore_errors=True)
        contents=app/'Contents';resources=contents/'Resources'
        resources.mkdir(exist_ok=True)
        shutil.copy2(ROOT/'resources/gyrograde/AppIcon.icns',resources/'AppIcon.icns')
        shutil.copy2(binary,contents/'MacOS/gyroflow')
        plist=contents/'Info.plist'
        with plist.open('rb') as f: info=plistlib.load(f)
        info.update(CFBundleDisplayName='GyroGrade',CFBundleName='GyroGrade',
                    CFBundleIdentifier='com.ryansmith.gyrograde',CFBundleExecutable='gyroflow',CFBundleIconFile='AppIcon.icns',
                    CFBundleShortVersionString=version.split('-')[0],CFBundleVersion=version.split('-')[0],
                    GyroGradeVersion=version,GyroGradeCheckoutCommit=commit,
                    GyroGradeDevelopmentRuntime=args.development_runtime,
                    NSHumanReadableCopyright='GyroGrade by Ryan Smith, based on Gyroflow. Original Gyroflow and third-party copyrights retained.')
        info.pop('GyroflowLUTSourceCommit',None)
        info.pop('GyroGradeSourceCommit',None)
        if binary_commit: info['GyroGradeSourceCommit']=binary_commit
        info.pop('UTExportedTypeDeclarations',None)
        # Be available in Open With, without becoming the owner/default handler.
        info['CFBundleDocumentTypes']=[dict(CFBundleTypeName='Gyroflow Project',CFBundleTypeRole='Editor',
            LSHandlerRank='None',LSItemContentTypes=['xyz.gyroflow.project'])]
        info['UTImportedTypeDeclarations']=[dict(UTTypeIdentifier='xyz.gyroflow.project',
            UTTypeDescription='Gyroflow Project',UTTypeConformsTo=['public.json'],
            UTTypeTagSpecification={'public.filename-extension':['gyroflow']})]
        if not args.development_runtime: info.pop('LSEnvironment',None)
        with plist.open('wb') as f: plistlib.dump(info,f)
        notices=resources/'Notices'
        mac_audit=check_mac_dependencies(app)
        check_mac_minimum(mac_audit, info)
        external=mac_audit['external_dependencies']
        if not args.development_runtime and (external or mac_audit['errors']):
            raise RuntimeError('Mac runtime audit failed: '+ '; '.join(mac_audit['errors'] +
                ['External runtime path: '+path for path in external]))
    else:
        app=output/'GyroGrade'
        shutil.copytree(runtime,app)
        # Keep the upstream executable name. The embedded MDK key displays a QR
        # overlay for a renamed executable (docs/WINDOWS-LUT-TESTING.md).
        # The folder, settings and update identities remain the fork's own.
        (app/'gyroflow.exe').unlink(missing_ok=True)
        shutil.copy2(binary,app/'Gyroflow.exe')
        # Portable ZIP only; no Appx, installer identity or association registry.
        if any(p.suffix.lower() in ('.appx','.msix','.pfx') for p in app.rglob('*')):
            raise RuntimeError('Expected a portable Windows runtime, without Store packages or signing keys')
        # windeployqt places QML modules under qml/, separately from plugins.
        (app/'qt.conf').write_text('[Paths]\nPrefix=.\nPlugins=.\nQmlImports=qml\n')
        notices=app/'Notices';external=[]
        import windows_runtime_audit  # pinned pefile: _scripts/requirements-package.txt
        floor=args.msvc_redist_floor
        windows_audit=windows_runtime_audit.audit(app,'Gyroflow.exe',floor)
        if not args.development_runtime:
            if not windows_audit['native_version_check']:
                windows_audit['errors'].append('Release staging must run on Windows to cross-check FileVersion natively')
            ocio='ocio-runtime' in receipt_in.get('features','').replace(',',' ').split()
            if windows_audit.get('ocio_runtime_linked')!=ocio or windows_audit.get('shader_tools_linked')!=ocio:
                windows_audit['errors'].append(f'Executable OCIO/ShaderTools imports do not match deploy features {receipt_in.get("features")!r}')
            if windows_audit['errors']:
                raise RuntimeError('Windows runtime audit failed: '+'; '.join(windows_audit['errors']))
    lens_profiles=check_lens_profiles(app,args.platform,receipt_in,args.development_runtime)
    notices.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'LICENSE',notices/'Gyroflow-GPL-3.0.txt')
    shutil.copy2(ROOT/'resources/color/OCIO-LICENSE.txt',notices/'OpenColorIO-BSD-3-Clause.txt')
    shutil.copy2(ROOT/'docs/PLUS-DISTRIBUTION.md',notices/'COMMUNITY-FORK.md')
    shutil.copytree(ROOT/'resources/lens-profiles-v41',notices/'lens-profiles-v41')
    copy_qmetaobject_notices(notices)
    copy_ffmpeg_sys_notices(notices)
    if args.licenses: shutil.copytree(args.licenses.resolve(strict=True),notices/'Dependencies')
    native_notices=None
    if args.platform=='windows' and args.native_notices_sha256:
        native_notices=bind_native_notices(notices/'Dependencies',args.native_notices_sha256)
        tree=(notices/'Dependencies'/native_notices['manifest_path']).parent if native_notices['manifest_path'] else None
        native_notices['source_bundles'],bundle_errors=stage_source_bundles(args.source_bundle,output/'Source',tree)
        native_notices['errors']+=bundle_errors
        if not args.development_runtime and native_notices['errors']:
            raise RuntimeError('Native notice binding failed: '+'; '.join(native_notices['errors']))
    ocio_notices=copy_ocio_notices(app,notices)
    if not args.development_runtime and ocio_notices['errors']:
        raise RuntimeError('OpenColorIO notice check failed: '+'; '.join(ocio_notices['errors']))
    packaged_binary = app/'Contents/MacOS/gyroflow' if args.platform=='mac' else app/'Gyroflow.exe'
    if hashlib.sha256(packaged_binary.read_bytes()).hexdigest()!=binary_hash:
        raise RuntimeError('Executable changed during staging; no completed package receipt written')
    if receipt_bytes is not None: (notices/'BUILD-INPUT.json').write_bytes(receipt_bytes)
    manifest=dict(name='GyroGrade',community_fork=True,version=version,commit=binary_commit,
        checkout_commit=commit,binary_source_verified=receipt_in is not None,
        dirty_source=dirty,development_runtime=args.development_runtime,
        input_binary_sha256=binary_hash,
        source=f'https://github.com/rsmith4321/gyrograde/tree/{binary_commit}' if binary_commit else None,
        checkout_source=f'https://github.com/rsmith4321/gyrograde/tree/{commit}',external_mac_dependencies=external,
        lens_profiles=lens_profiles,native_notices=native_notices,public_release_approved=False)
    if mac_audit is not None: manifest['mac_runtime_audit'] = mac_audit
    if windows_audit is not None: manifest['windows_runtime_audit'] = windows_audit
    (notices/'BUILD.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # A complete committed source archive accompanies every stage. Refusing
    # dirty builds avoids omitting untracked source or collecting private files.
    with (output/f'GyroGrade-source-{commit[:12]}.tar').open('wb') as f:
        subprocess.run(['git','archive','--format=tar',commit],cwd=ROOT,stdout=f,check=True)
    if args.platform=='mac':
        subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
        subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    # Signing changes the Mach-O executable bytes. Keep the final hash outside
    # the signed bundle to avoid a circular manifest/resource-signature hash.
    receipt = dict(source_commit=binary_commit, checkout_commit=commit,
        binary_source_verified=receipt_in is not None, platform=args.platform,
        packaged_binary_sha256=hashlib.sha256(packaged_binary.read_bytes()).hexdigest(),
        input_binary_sha256=manifest['input_binary_sha256'], lens_profiles=lens_profiles,
        development_runtime=args.development_runtime, native_notices=native_notices, public_release_approved=False)
    if mac_audit is not None: receipt['mac_runtime_audit'] = mac_audit
    if windows_audit is not None:
        receipt['windows_runtime_audit'] = {key: windows_audit.get(key) for key in ('machine', 'errors',
            'ocio_runtime_linked', 'shader_tools_linked', 'crt_version', 'native_version_check', 'pefile_version')}
    (output/'PACKAGE.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__': main()
