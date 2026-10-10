# SPDX-License-Identifier: GPL-3.0-or-later
"""Static dependency audit of a portable Windows stage.

PE parsing uses the pinned pefile package (_scripts/requirements-package.txt);
on a Windows host every FileVersion is also read through the native version
API and must agree. This proves import-table closure, exported-symbol presence
for staged providers and one C++ runtime set. It does not prove that the stage
runs: LoadLibrary use (MDK codecs, GPU drivers, Qt plugins), symbols provided
by Windows itself and behaviour under a given Windows build need a Windows run.
"""
import re
import sys
from pathlib import Path

import pefile

MACHINES = {0x8664: 'x64', 0xAA64: 'arm64', 0x14C: 'x86'}
# Windows 10+ in-box DLLs that staged images may import. Anything else must be
# staged beside the executable. Redistributable C++ runtime DLLs are deliberately
# absent; msvcrt is Windows' legacy CRT, not the application's vcruntime140 set.
WINDOWS_SYSTEM_DLLS = frozenset('''
advapi32 authz avicap32 avrt bcrypt bcryptprimitives cfgmgr32 combase comctl32 comdlg32 crypt32 d2d1 d3d9
d3d11 d3d12 d3dcompiler_47 dbghelp dcomp dnsapi dwmapi dwrite dxcore dxgi dxva2
dsound gdi32 gdiplus hid imagehlp imm32 iphlpapi kernel32 ksuser mf mfplat mfreadwrite mpr msimg32 msvcrt
ncrypt netapi32 normaliz ntdll ole32 oleacc oleaut32 opengl32 glu32 powrprof
propsys psapi rpcrt4 secur32 setupapi shcore shell32 shlwapi user32 userenv
usp10 uxtheme version winhttp wininet winmm winspool.drv wintrust wldap32
ws2_32 wtsapi32 windowscodecs
'''.split())
# Staged deliberately for loaders outside Qt; Qt itself loads D3DCompiler from
# System32 only (QSystemLibrary default). Any other system name would shadow
# Windows or be ignored, so staging it is an error.
STAGED_SYSTEM_EXCEPTIONS = frozenset({'d3dcompiler_47'})
# Documented optional delay loads. Empty: a missing delay load is an error.
OPTIONAL_DELAY_IMPORTS = frozenset()
CRT = re.compile(r'(msvcp140(_\w+)?|vcruntime140(_\w+)?|concrt140|vcomp140|vccorlib140|mfc140\w*)\.dll')
# Microsoft debug runtimes belong on test machines, not portable release stages.
# Check known runtime families, not arbitrary application DLLs ending in "d".
# Older toolsets (VC6 to VS 2013) used versioned names such as mfc42ud, msvcm90d,
# vcomp120d and vcamp120d, which an imported prebuilt DLL can still require.
DEBUG_CRT = re.compile(r'(ucrtbased|msvcrtd|msvcirtd|(msvcp|msvcr|msvcm)\d+d'
                       r'|(msvcp|vcruntime|concrt|vccorlib|vcomp|vcamp)\d+d(_\w+)?'
                       r'|(msvcp|vcruntime)140_\w+d|mfcm?\d+u?d)\.dll')
FAMILIES = re.compile(r'(avcodec|avdevice|avfilter|avformat|avutil|postproc|swresample|swscale)-\d+\.dll'
                      r'|(opencolorio)_\d+_\d+\.dll|(opencv_[a-z0-9]+?)\d+\.dll')


def _system(name):
    stem = name[:-4] if name.endswith('.dll') else name
    return stem in WINDOWS_SYSTEM_DLLS or name in WINDOWS_SYSTEM_DLLS


def _native_version(path):
    """FileVersion through GetFileVersionInfoW/VerQueryValueW (Windows only)."""
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('version', use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR,
                                 ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT))
    api.VerQueryValueW.restype = wintypes.BOOL
    size = api.GetFileVersionInfoSizeW(str(path), None)
    if not size: return None
    buffer = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(path), 0, size, buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    value, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.VerQueryValueW(buffer, '\\', ctypes.byref(value), ctypes.byref(length)) or length.value < 52:
        return None
    signature, _, high, low = ctypes.cast(value, ctypes.POINTER(wintypes.DWORD * 4)).contents
    if signature != 0xFEEF04BD: raise RuntimeError(f'Invalid VS_FIXEDFILEINFO: {path}')
    return (high >> 16, high & 0xFFFF, low >> 16, low & 0xFFFF)


# pefile's corruption heuristics stop at 8,192 imports or exports; real Qt 6.7.3
# DLLs exceed both. Raise the bounds so tables are read whole; any remaining
# parser warning still fails the audit.
SYMBOL_LIMIT = 1 << 20


def read_image(path):
    pefile.MAX_IMPORT_SYMBOLS = SYMBOL_LIMIT
    pe = pefile.PE(str(path), fast_load=True, max_symbol_exports=SYMBOL_LIMIT)
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY[name] for name in (
            'IMAGE_DIRECTORY_ENTRY_IMPORT', 'IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT',
            'IMAGE_DIRECTORY_ENTRY_EXPORT', 'IMAGE_DIRECTORY_ENTRY_RESOURCE')])
        def entries(attribute, delayed):
            return [dict(dll=entry.dll.decode('ascii').lower(), delayed=delayed,
                         names=sorted({i.name.decode('ascii') for i in entry.imports if i.name}),
                         ordinals=sorted({i.ordinal for i in entry.imports if not i.name and i.ordinal is not None}))
                    for entry in getattr(pe, attribute, [])]
        exports = getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None)
        fixed = getattr(pe, 'VS_FIXEDFILEINFO', None)
        version = None
        if fixed:
            if fixed[0].Signature != 0xFEEF04BD: raise RuntimeError('invalid VS_FIXEDFILEINFO')
            version = (fixed[0].FileVersionMS >> 16, fixed[0].FileVersionMS & 0xFFFF,
                       fixed[0].FileVersionLS >> 16, fixed[0].FileVersionLS & 0xFFFF)
        return dict(
            machine=MACHINES.get(pe.FILE_HEADER.Machine, hex(pe.FILE_HEADER.Machine)),
            dll=bool(pe.FILE_HEADER.Characteristics & 0x2000),
            linker=(pe.OPTIONAL_HEADER.MajorLinkerVersion, pe.OPTIONAL_HEADER.MinorLinkerVersion),
            imports=entries('DIRECTORY_ENTRY_IMPORT', False) + entries('DIRECTORY_ENTRY_DELAY_IMPORT', True),
            export_names=sorted({s.name.decode('ascii') for s in exports.symbols if s.name}) if exports else [],
            export_ordinals=sorted({s.ordinal for s in exports.symbols}) if exports else [],
            forwarders=sorted({s.forwarder.decode('ascii') for s in exports.symbols if s.forwarder}) if exports else [],
            file_version=version, warnings=pe.get_warnings())
    finally:
        pe.close()


def collect(app):
    """Facts for every file in the stage; parse failures become errors later."""
    files, images = [], {}
    for path in sorted(app.rglob('*')):
        if path.is_symlink(): files.append((path.relative_to(app).as_posix(), 'symlink'))
        elif path.is_file():
            relative = path.relative_to(app).as_posix()
            files.append((relative, 'file'))
            if path.suffix.lower() in ('.exe', '.dll'):
                try: images[relative] = read_image(path)
                except (OSError, RuntimeError, ValueError, pefile.PEFormatError) as failure:
                    images[relative] = dict(error=str(failure))
    return dict(files=files, images=images)


def evaluate(facts, executable, redist_floor=None, native_versions=None):
    """Pure rules over collected facts, so each rule is testable without binaries."""
    errors = []
    files, images = facts['files'], facts['images']
    seen = {}
    for relative, kind in files:
        if kind == 'symlink': errors.append(f'{relative}: symbolic links are not portable stage content')
        key = relative.casefold()
        if key in seen: errors.append(f'{relative} and {seen[key]} collide on a case-insensitive file system')
        seen.setdefault(key, relative)
    for relative, info in images.items():
        if 'error' in info: errors.append(f'Cannot inspect {relative}: {info["error"]}')
        elif info['warnings']: errors.append(f'{relative}: PE parser warnings: {"; ".join(info["warnings"])}')
    good = {k: v for k, v in images.items() if 'error' not in v}
    main = good.get(executable)
    if not main or main['dll']:
        return dict(errors=errors + [f'Missing PE executable: {executable}'])
    # The loader resolves imports of every module, plugins included, from the
    # executable directory (Qt 6.7 loads plugins by full path with LoadLibrary).
    root = {k.casefold(): k for k in good if '/' not in k}
    for relative, info in good.items():
        name = relative.rsplit('/', 1)[-1].casefold()
        if relative.casefold().endswith('.dll') and not info['dll']: errors.append(f'{relative}: not a DLL image')
        if info['machine'] != main['machine']:
            errors.append(f'{relative}: {info["machine"]} image in {main["machine"]} stage')
        if '/' in relative and name in root:
            errors.append(f'{relative} shadows {root[name]}; only the executable directory satisfies imports')
        if DEBUG_CRT.fullmatch(name):
            errors.append(f'{relative}: debug C++ runtime is not redistributable')
        for entry in info['imports']:
            if DEBUG_CRT.fullmatch(entry['dll'].casefold()):
                errors.append(f'{relative}: imports debug C++ runtime {entry["dll"]}')
        if '/' not in relative and _system(name) and name[:-4] not in STAGED_SYSTEM_EXCEPTIONS:
            errors.append(f'{relative}: staged copy of a Windows system DLL')
    families = {}
    for key in root:
        match = FAMILIES.fullmatch(key)
        if match: families.setdefault(next(g for g in match.groups() if g), []).append(root[key])
    for family, members in sorted(families.items()):
        if len(members) > 1: errors.append(f'Several {family} versions staged: {", ".join(sorted(members))}')

    for relative, info in good.items():
        for entry in info['imports']:
            dll, kind = entry['dll'], 'delay-loaded' if entry['delayed'] else 'required'
            if dll in root:
                target = good[root[dll]]
                missing = [n for n in entry['names'] if n not in target['export_names']]
                missing += [f'#{o}' for o in entry['ordinals'] if o not in target['export_ordinals']]
                if missing:
                    errors.append(f'{relative}: {kind} {root[dll]} lacks {len(missing)} imported symbols, '
                                  f'e.g. {", ".join(missing[:5])}')
            elif dll.startswith('api-ms-win-') or _system(dll): continue
            elif dll.startswith('ext-ms-win-') and entry['delayed']: continue
            elif entry['delayed'] and dll in OPTIONAL_DELAY_IMPORTS: continue
            else: errors.append(f'{relative}: {kind} {dll} is neither staged nor a Windows system DLL')
        for forward in info['forwarders']:
            module, separator, symbol = forward.rpartition('.')
            module = module.casefold()
            if not module.endswith('.dll'): module += '.dll'
            if not separator or not symbol:
                errors.append(f'{relative}: malformed export forwarder {forward}')
                continue
            if DEBUG_CRT.fullmatch(module):
                errors.append(f'{relative}: forwards to debug C++ runtime {module}')
            if not (module.startswith(('api-ms-win-', 'ext-ms-win-')) or _system(module) or module in root):
                errors.append(f'{relative}: export forwards to unstaged {forward}')
            elif module in root:
                provider = good[root[module]]
                present = (symbol[1:].isdigit() and int(symbol[1:]) in provider['export_ordinals']) \
                    if symbol.startswith('#') else symbol in provider['export_names']
                if not present: errors.append(f'{relative}: export forwards to missing symbol {forward}')

    # One C++ runtime set, at least as new as every user. The app-local copy wins
    # over System32 because these are not KnownDLLs.
    crt = {k: good[v] for k, v in root.items() if CRT.fullmatch(k)}
    users = [(info['linker'], relative) for relative, info in good.items()
             if any(CRT.fullmatch(e['dll']) for e in info['imports']) and not CRT.fullmatch(relative.casefold())]
    versions = {k: v['file_version'] for k, v in crt.items()}
    for key, version in sorted(versions.items()):
        if version is None: errors.append(f'{root[key]}: missing VS_FIXEDFILEINFO')
    distinct = {v for v in versions.values() if v}
    if len(distinct) > 1:
        errors.append('Mixed C++ runtime versions: ' + ', '.join(f'{root[k]} {".".join(map(str, v))}'
                                                                  for k, v in sorted(versions.items()) if v))
    staged_crt = min(distinct) if distinct else None
    if users and staged_crt:
        linker, user = max(users)
        if staged_crt[:2] < linker:
            errors.append(f'C++ runtime {".".join(map(str, staged_crt))} is older than linker '
                          f'{linker[0]}.{linker[1]} of {user}')
        if redist_floor and staged_crt < redist_floor:
            errors.append(f'C++ runtime {".".join(map(str, staged_crt))} is below the declared toolset floor '
                          f'{".".join(map(str, redist_floor))}')
    if native_versions is not None:
        for relative, info in good.items():
            if native_versions.get(relative) != info['file_version']:
                errors.append(f'{relative}: native FileVersion {native_versions.get(relative)} != '
                              f'parsed {info["file_version"]}')
    imported = {e['dll'] for e in main['imports']}
    return dict(machine=main['machine'], errors=errors,
                ocio_runtime_linked=any(d.startswith('opencolorio_') for d in imported),
                shader_tools_linked='qt6shadertools.dll' in imported,
                crt_version=staged_crt, crt_users=len(users),
                images={k: dict(imports=[e['dll'] + (' (delay)' if e['delayed'] else '') for e in v['imports']],
                                linker='%d.%d' % v['linker'], file_version=v['file_version'])
                        for k, v in good.items()})


def audit(app, executable, redist_floor=None):
    facts = collect(app)
    native = None
    if sys.platform == 'win32':
        native = {}
        for relative, info in facts['images'].items():
            if 'error' not in info: native[relative] = _native_version(app / relative)
    report = evaluate(facts, executable, redist_floor, native)
    report['native_version_check'] = native is not None
    report['pefile_version'] = pefile.__version__
    return report
