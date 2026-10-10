#!/usr/bin/env python3
"""Hosted-Windows source/relink evidence for pinned libass; never installs an app.

Keep the upstream devpkgs CMake project unchanged. The unrelated dav1d,
libva-loader and lz4 targets are disabled; the ass link graph is checked
against the vendor x64 link line so disabling them cannot weaken it.
No binary download, library source patch, NO_ASM substitution or release upload.
The one adaptation is a guarded, recorded copy of NASM's MSVC build recipe
(derive_nasm_makefile): the pinned Mkfiles/msvc.mak stays byte-identical.
Only text evidence (.json/.log) is written to native-source-evidence/.
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import zipfile

SOURCES = (
    ("devpkgs", "wang-bin/devpkgs", "ce43c819981bb7ca028d08d1baa4847f1136f576"),
    ("devpkgs/cmake/tools", "wang-bin/cmake-tools", "a8a52d31cb5f2ab8916160069cbc7183c5e92a18"),
    ("devpkgs/src/freetype", "freetype/freetype", "0a0221a1347e2f1e07c395263540026e9a0aa7c7"),
    ("devpkgs/src/freetype/subprojects/dlg", "nyorain/dlg", "395ccad2c1e0daae535c4d20bb0a3f2424648e17"),
    ("devpkgs/src/harfbuzz", "harfbuzz/harfbuzz", "863d3f7787c6df18d20e4535c5906bf3eb803bd5"),
    ("devpkgs/src/fribidi", "fribidi/fribidi", "b93119f5fdc7ea47672cc304c1455ffa6dfe7536"),
    ("devpkgs/src/libass", "wang-bin/libass", "af5f116d243f060a708c82f0c6e3102a2270a336"),
    ("devpkgs/src/snappy", "google/snappy", "9c28114a38866f6deeaa826db918293bc28ae410"),
    ("devpkgs/src/glfw", "glfw/glfw", "d9d6f0f1f967807ffade6598ea9a631ebaf37a56"),
    ("devpkgs/src/zlib", "madler/zlib", "da607da739fa6047df13e66a2af6b8bec7c2a498"),
    ("devpkgs/src/oneVPL", "wang-bin/oneVPL", "3a3ca48d176ceb9733c2ea81d4f16a17d6c1702c"),
    ("nasm", "netwide-assembler/nasm", "d41598b3359d39c14e80f56bd8c3749f1d097932"),
)
REPOSITORY = "rsmith4321/gyrograde"
BRANCH = "codex/lut-preview-controls"  # already the repository default branch (root API check 2026-10-10)
WORKFLOW = ".github/workflows/native-libass-source.yml"
ARCHIVE_WORKFLOW = ".github/workflows/native-libass-archives.yml"
SOURCE_MODE = "GYROFLOWPLUS_LIBASS_SOURCE_MODE"
# Per-command and whole-run log caps. Checked by polling, so a log can pass a cap by up to one poll
# interval of output before the process tree is stopped; the retained file is then cut to the cap.
MAX_LOG_BYTES = 12 * 1024 * 1024
MAX_TOTAL_LOG_BYTES = 24 * 1024 * 1024
POLL_SECONDS = 0.2
WHOLE_SECONDS = 900
NOT_RUN = ("The hosted Visual Studio is whatever vswhere reports for this run (TOOLCHAIN.json); it is not shown "
           "to match the vendor's build and no vendor-identical compiler, version-metadata or DLL claim is made. "
           "No app install/runtime test, complete corresponding-source or release approval.")

# Vendor x64 link of libass.dll (devpkgs job log line 1630), relative to the build directory.
_OBJ = "projects\\libass\\CMakeFiles\\{}.dir\\__\\__\\src\\libass\\libass\\{}.obj"
VENDOR_OBJECTS = tuple(_OBJ.format("ass-objs", n + ".c") for n in (
    "ass", "ass_arabic_charmap", "ass_bitmap", "ass_bitmap_engine", "ass_blur", "ass_cache",
    "ass_directwrite", "ass_drawing", "ass_face", "ass_face_ft", "ass_filesystem", "ass_font",
    "ass_fontselect", "ass_library", "ass_outline", "ass_parse", "ass_rasterizer", "ass_render",
    "ass_render_api", "ass_shaper", "ass_string", "ass_strtod", "ass_utils", "c\\c_be_blur",
    "c\\c_blend_bitmaps", "c\\c_blur", "c\\c_rasterizer"))
ASM_NAMES = ("be_blur", "blend_bitmaps", "blur", "cpuid", "rasterizer", "utils", "x86inc")
VENDOR_OBJECTS += tuple(_OBJ.format("ass_asm", "x86\\" + n + ".asm") for n in ASM_NAMES)
VENDOR_STATIC_LIBRARIES = ("projects\\fribidi\\libfribidi.lib", "src\\freetype\\freetype.lib",
                           "src\\harfbuzz\\harfbuzz.lib")
DLL = "projects\\libass\\libass.dll"
# fribidi-gen.cmake POST_BUILD commands write these into the source tree's gen.tab directory.
FRIBIDI_OUTPUTS = {
    "fribidi-unicode-version.h": "gen-unicode-version", "bidi-type.tab.i": "gen-bidi-type-tab",
    "joining-type.tab.i": "gen-joining-type-tab", "arabic-shaping.tab.i": "gen-arabic-shaping-tab",
    "mirroring.tab.i": "gen-mirroring-tab", "brackets.tab.i": "gen-brackets-tab",
    "brackets-type.tab.i": "gen-brackets-type-tab"}
# NASM Mkfiles/msvc.mak PERLREQ (Perl-generated inputs; absent from the git snapshot except unconfig.h).
NASM_PERLREQ = (
    "config/unconfig.h", "x86/insnsb.c", "x86/insnsa.c", "x86/insnsd.c", "x86/insnsi.h", "x86/insnsn.c",
    "x86/regs.c", "x86/regs.h", "x86/regflags.c", "x86/regdis.c", "x86/regdis.h", "x86/regvals.c",
    "asm/tokhash.c", "asm/tokens.h", "asm/pptok.h", "asm/pptok.c", "x86/iflag.c", "x86/iflaggen.h",
    "macros/macros.c", "asm/pptok.ph", "asm/directbl.c", "asm/directiv.h", "asm/warnings.c",
    "include/warnings.h", "doc/warnings.src", "misc/nasmtok.el", "version.h", "version.mac",
    "version.mak", "nsis/version.nsh")
ERROR_SHARING_VIOLATION = 32  # Windows: another process still holds an open handle to the file
# NASM's MSVC build recipe. The pinned file is kept; NMake reads a derived copy (same directory, so every
# relative path is unchanged) with only these recipe lines adapted. Each original line must match exactly.
NASM_MAKEFILE = "Mkfiles/msvc.mak"
NASM_MAKEFILE_SHA256 = "a1404ea2617c0d0b06e3b064e11a9fbce8f3d6d5d77a79a33e03ec896f4e1f39"
NASM_COMPAT_MAKEFILE = "Mkfiles\\msvc.gyroflowplus-compat.mak"
NASM_CONFIGURATION_HEADERS = (
    ("config/unconfig.h", 3807, "e5b7b00426dfdccae75892c5f4aa46903631f0e77b495af2312ad7098473326b"),
    ("config/msvc.h", 6054, "901386cb1ea45bccf3e4abbf88623ec21f435ed9d0c3950c3f17e9a229e11a51"),
)
_WARNTIMES = "asm\\warnings.c.time include\\warnings.h.time doc\\warnings.src.time"
_RECURSE = "$(MAKE) /f " + NASM_COMPAT_MAKEFILE
_U1005 = "NMake rejects an empty search string in $(macro:old=new) (U1005 at line 238); the three names are listed"
_TOUCH = "':' is a POSIX shell no-op with no cmd.exe equivalent; 'type nul >' creates the same empty stamp file"
_SIDE = "'@:' is a POSIX no-op; 'rem' is cmd's no-op and this makefile already uses it (line 353)"
NASM_RECIPE_EDITS = (
    (162, "config\\unconfig.h: config\\config.h.in", "config\\unconfig.h:",
     "the pinned Git snapshot includes exact unconfig.h but no autoheader template; preserve the checked-in header"),
    (238, "\t$(RM_F) $(WARNFILES) $(WARNFILES:=.time)", "\t$(RM_F) $(WARNFILES) " + _WARNTIMES, _U1005),
    (239, "\t$(MAKE) asm\\warnings.time", "\t" + _RECURSE + " asm\\warnings.time",
     "a recursive NMake has no default makefile in the NASM directory; name the derived file"),
    (241, "asm\\warnings.time: $(ALLOBJ_NW:.$(O)=.c)", "asm\\warnings.time: $(ALLOBJ_NW:.obj=.c)",
     "no macro inside a substitution string; O is defined as obj (line 53), so the list is unchanged"),
    (242, "\t: > asm\\warnings.time", "\ttype nul > asm\\warnings.time", _TOUCH),
    (243, "\t$(MAKE) $(WARNFILES:=.time)", "\t" + _RECURSE + " " + _WARNTIMES,
     _U1005 + "; the recursion names the derived file"),
    (247, "\t: > asm\\warnings.c.time", "\ttype nul > asm\\warnings.c.time", _TOUCH),
    (250, "\t@: Side effect", "\t@rem Side effect", _SIDE),
    (254, "\t: > include\\warnings.h.time", "\ttype nul > include\\warnings.h.time", _TOUCH),
    (257, "\t@: Side effect", "\t@rem Side effect", _SIDE),
    (261, "\t: > doc\\warnings.src.time", "\ttype nul > doc\\warnings.src.time", _TOUCH),
    (264, "\t@: Side effect", "\t@rem Side effect", _SIDE),
    (302, '\t$(RUNPERL) $< $@ "$(srcdir)" "$(objdir)"', '\t$(RUNPERL) misc\\emacstbl.pl $@ "$(srcdir)" "$(objdir)"',
     "$< is defined only in inference rules; this explicit rule names its first dependency instead"),
    (392, "!ELSEIF [$(MAKE) /c MKDEP=1 /f Mkfiles\\msvc.mak msvc.dep] == 0",
     "!ELSEIF [$(MAKE) /c MKDEP=1 /f " + NASM_COMPAT_MAKEFILE + " msvc.dep] == 0",
     "this parse-time recursion must read the derived file; the original stops at line 238"),
)
# Unchanged lines the edits rely on, and construct counts in the pinned file (fail closed on any other file).
NASM_RECIPE_CONTEXT = {53: "O               = obj",
                       235: "WARNFILES = asm\\warnings.c include\\warnings.h doc\\warnings.src",
                       353: "\trem cd doc && $(MAKE) clean",
                       382: "\t$(RUNPERL) tools\\mkdep.pl -M Mkfiles\\msvc.mak -- $(DEPDIRS)"}
NASM_RECIPE_COUNTS = {"$(WARNFILES:=.time)": 2, "\t: > ": 4, "@: Side effect": 3, "$(MAKE)": 5, "$<": 2,
                      ":.$(O)=": 1, "Mkfiles\\msvc.mak": 2}
# sha256 of derive_nasm_makefile(pinned msvc.mak); any other result is refused at run time
NASM_COMPAT_SHA256 = "d7c819605cf2e2c24cef5c5b2ee16ac6c9f7088d0b7e45de621168f723bff37b"


def derive_nasm_makefile(original: bytes, expected_sha256: str = NASM_MAKEFILE_SHA256) -> tuple:
    """Return (derived bytes, change records) for the pinned NASM msvc.mak; refuse anything else."""
    if hashlib.sha256(original).hexdigest() != expected_sha256:
        raise ValueError("NASM makefile is not the pinned msvc.mak.")
    text = original.decode("ascii")
    if "\r" in text or not text.endswith("\n"):
        raise ValueError("Unexpected NASM makefile line endings.")
    for needle, count in NASM_RECIPE_COUNTS.items():
        if text.count(needle) != count:
            raise ValueError(f"Unexpected NASM makefile construct count: {needle}")
    lines = text.split("\n")
    for number, line in NASM_RECIPE_CONTEXT.items():
        if lines[number - 1] != line:
            raise ValueError(f"Unexpected NASM makefile context at line {number}.")
    changes = []
    for number, old, new, reason in NASM_RECIPE_EDITS:
        if lines[number - 1] != old:
            raise ValueError(f"Unexpected NASM makefile text at line {number}.")
        lines[number - 1] = new
        changes.append({"line": number, "original": old, "derived": new, "reason": reason})
    derived = "\n".join(lines).encode("ascii")
    left = derived.decode("ascii")
    if ":=" in left or ":.$(O)=" in left or left.count("$<") != 1 or "@:" in left or "\t: >" in left:
        raise ValueError("NASM makefile adaptation left an unsupported construct.")
    if left.count(NASM_COMPAT_MAKEFILE) != 3 or left.count("Mkfiles\\msvc.mak") != 1:  # 3 recursions; mkdep hint
        raise ValueError("NASM makefile recursion does not name the derived file.")
    return derived, changes


def nasm_configuration(nasm: Path) -> dict:
    """Require the pinned Git snapshot's official MSVC headers, never generate substitutes."""
    template = nasm / "config/config.h.in"
    if template.exists() or template.is_symlink():
        raise RuntimeError("Unexpected NASM config/config.h.in in the pinned Git snapshot.")
    record = {}
    for name, size, expected in NASM_CONFIGURATION_HEADERS:
        path = nasm / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Missing or nonregular pinned NASM configuration header: " + name)
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if len(data) != size or actual != expected:
            raise RuntimeError("Changed pinned NASM configuration header: " + name)
        record[name] = {"bytes": len(data), "sha256": actual}
    return record


TOOLS = ("git.exe", "cl.exe", "link.exe", "nmake.exe", "cmake.exe", "ninja.exe", "perl.exe", "dumpbin.exe")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def admission_errors(environ, platform: str) -> list:
    """Names of failed admission checks; empty means admitted."""
    mode = environ.get(SOURCE_MODE, "git")
    workflow = ARCHIVE_WORKFLOW if mode == "archives" else WORKFLOW
    expected = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Windows",
                "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_REF": "refs/heads/" + BRANCH, "GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": BRANCH,
                "GITHUB_WORKFLOW_REF": REPOSITORY + "/" + workflow + "@refs/heads/" + BRANCH}
    errors = [key for key, value in expected.items() if environ.get(key) != value]
    if mode not in ("git", "archives"):
        errors.append(SOURCE_MODE)
    if platform != "win32":
        errors.append("sys.platform")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        if not re.fullmatch(r"[1-9][0-9]{0,19}", environ.get(key, "")):
            errors.append(key)
    sha = environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha == "0" * 40:
        errors.append("GITHUB_SHA")
    for key in ("GITHUB_WORKSPACE", "RUNNER_TEMP"):
        if not environ.get(key):
            errors.append(key)
    return errors


def require_host() -> None:
    errors = admission_errors(os.environ, sys.platform)
    if errors:
        raise SystemExit("Only a manual dispatch on " + BRANCH + " of " + REPOSITORY +
                         " on a GitHub-hosted Windows runner is admitted; failed: " + ", ".join(errors))


def normalize_windows_env(mapping) -> dict:
    """One upper-case key per Windows variable; case-variant keys with different values are refused."""
    result = {}
    for key, value in mapping.items():
        upper = key.upper()
        if upper in result and result[upper] != value:
            raise ValueError("Ambiguous environment variable spelling: " + upper)
        result[upper] = value
    return result


def merge_windows_env(base, captured: str) -> dict:
    """Overlay cmd `set` output on base without leaving stale case variants such as PATH beside Path."""
    merged = normalize_windows_env(base)
    seen = set()
    for line in captured.splitlines():
        key, sep, value = line.partition("=")
        if not sep or not key or key.startswith("="):
            continue
        upper = key.upper()
        if upper in seen:
            raise ValueError("Duplicate variable in developer environment: " + upper)
        seen.add(upper)
        merged[upper] = value
    if "PATH" not in seen:
        raise ValueError("Developer environment did not report PATH.")
    return merged


def parse_symbol_file(text: str) -> list:
    """Every non-empty libass.sym line, as written after EXPORTS into the CMake .def file."""
    names = []
    for number, line in enumerate(text.splitlines(), 1):
        name = line.strip()
        if not name:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Unsupported libass.sym line {number}.")
        names.append(name)
    if not names or len(set(names)) != len(names):
        raise ValueError("libass.sym is empty or has duplicate names.")
    return names


_EXPORT_HEADER = re.compile(r"\s*ordinal\s+hint\s+RVA\s+name\s*")
_EXPORT_ROW = re.compile(r"\s+([0-9]+)\s+([0-9A-F]+)\s+([0-9A-F]{8})\s+([A-Za-z_][A-Za-z0-9_]*)")


def parse_dumpbin_exports(text: str) -> list:
    """Every named export row of `dumpbin /exports`; forwarded, ordinal-only or odd rows are refused."""
    lines = text.splitlines()
    headers = [i for i, line in enumerate(lines) if _EXPORT_HEADER.fullmatch(line)]
    if len(headers) != 1:
        raise ValueError("Expected exactly one export table.")
    counts = {}
    for line in lines[:headers[0]]:
        match = re.fullmatch(r"\s*([0-9]+) number of (functions|names)\s*", line)
        if match:
            if match[2] in counts:
                raise ValueError("Repeated export count.")
            counts[match[2]] = int(match[1])
    rows = []
    for line in lines[headers[0] + 1:]:
        stripped = line.strip()
        if stripped == "Summary":
            break
        if not stripped:
            continue
        if "forwarded to" in stripped:
            raise ValueError("Forwarded export: " + stripped)
        if "[NONAME]" in stripped:
            raise ValueError("Ordinal-only export: " + stripped)
        match = _EXPORT_ROW.fullmatch(line)
        if not match:
            raise ValueError("Unsupported export row: " + stripped)
        rows.append((int(match[1]), match[4]))
    else:
        raise ValueError("Export table has no Summary terminator.")
    names = [name for _, name in rows]
    if len(set(names)) != len(names) or len({o for o, _ in rows}) != len(rows):
        raise ValueError("Duplicate export name or ordinal.")
    if counts.get("functions") != len(rows) or counts.get("names") != len(rows):
        raise ValueError("Export counts do not match the parsed rows.")
    return names


def compare_exports(expected, actual) -> None:
    missing, extra = sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))
    if missing or extra or len(actual) != len(expected):
        raise RuntimeError(f"Export set differs from libass.sym; missing {missing[:10]}, extra {extra[:10]}.")


def _tokens(line: str) -> list:
    # Build-relative object and library paths contain no spaces; quotes only wrap absolute tool paths.
    return line.replace('"', " ").split()


def _norm(token: str) -> str:
    """Backslash path separators; a leading / is an MSVC option prefix (/out:, /Fo) and is kept."""
    return token[:1] + token[1:].replace("/", "\\")


def link_line(graph: str) -> str:
    lines = [line for line in graph.splitlines()
             if any(t.lower() == "/out:" + DLL.lower() for t in map(_norm, _tokens(line)))]
    if len(lines) != 1:
        raise RuntimeError("Expected exactly one libass.dll link command.")
    return lines[0]


def link_inputs(line: str, read_response) -> dict:
    tokens = []
    for token in _tokens(line):
        if token.startswith("@"):
            tokens += _tokens(read_response(token[1:]))  # kept by ninja -d keeprsp
        else:
            tokens.append(token)
    tokens = [_norm(t) for t in tokens]
    lower = [t.lower() for t in tokens]
    objects = [t for t in tokens if t.lower().endswith(".obj")]
    libraries = [t for t in tokens if t.lower().endswith(".lib") and not t.startswith("/")]
    implib = [t.split(":", 1)[1] for t in tokens if t.lower().startswith("/implib:")]
    return {"objects": objects, "project_libraries": [t for t in libraries if "\\" in t and not
                                                       re.match(r"[A-Za-z]:", t)],
            "absolute_libraries": [t for t in libraries if re.match(r"[A-Za-z]:", t)],
            "system_libraries": [t for t in libraries if "\\" not in t],
            "implib": implib, "ltcg": any(t.startswith("/ltcg") for t in lower), "machine_x64": "/machine:x64" in lower}


def check_link_graph(inputs: dict) -> None:
    problems = []
    if sorted(inputs["objects"]) != sorted(VENDOR_OBJECTS):
        problems.append("objects " + repr(sorted(set(inputs["objects"]) ^ set(VENDOR_OBJECTS))[:10]))
    # The pinned HarfBuzz target links FreeType too (CMakeLists.txt:611-612).
    # Hosted CMake 4.4.3 repeats that archive after HarfBuzz; permit exactly that
    # known extra occurrence, not arbitrary duplicates or a weaker set comparison.
    repeated_freetype = VENDOR_STATIC_LIBRARIES + ("src\\freetype\\freetype.lib",)
    if sorted(inputs["project_libraries"]) != sorted(VENDOR_STATIC_LIBRARIES) and \
            tuple(inputs["project_libraries"]) != repeated_freetype:
        problems.append("static libraries " + repr(inputs["project_libraries"]))
    if inputs["absolute_libraries"]:
        problems.append("absolute libraries " + repr(inputs["absolute_libraries"][:5]))
    if len(inputs["implib"]) != 1 or not inputs["ltcg"] or not inputs["machine_x64"]:
        problems.append("implib/LTCG/x64")
    if problems:
        raise RuntimeError("ass link graph differs from the vendor x64 link: " + "; ".join(problems))


def _writes(line: str, flag: str, path: str) -> bool:
    """True when the command names path as its output, as `-o path` or `/Fopath` (or -Fo)."""
    tokens, path = [_norm(t).lower() for t in _tokens(line)], path.lower()
    if flag == "-o":
        return any(a == "-o" and b == path for a, b in zip(tokens, tokens[1:]))
    return any(t in ("/fo" + path, "-fo" + path) for t in tokens)


def check_assembly(graph: str) -> dict:
    """Every vendor ass_asm object is assembled as win64 with the libass x86-64 definitions."""
    lines = graph.splitlines()
    for name in ASM_NAMES:
        obj = _OBJ.format("ass_asm", "x86\\" + name + ".asm")
        hits = [line for line in lines if _writes(line, "-o", obj) and
                re.search(r"[\\/]libass[\\/]x86[\\/]" + name + r"\.asm(?![.\w])", line)]
        if len(hits) != 1:
            raise RuntimeError("Missing or repeated assembly command: " + name)
        tokens = _tokens(hits[0])
        if not ("-fwin64" in tokens or any(a == "-f" and b == "win64" for a, b in zip(tokens, tokens[1:]))) or \
                not {"-DARCH_X86_64=1", "-Dprivate_prefix=ass", "-DHAVE_ALIGNED_STACK=1"} <= set(tokens):
            raise RuntimeError("Assembly command lacks win64 x86-64 options: " + name)
    compile_c = [line for line in lines if _writes(line, "/Fo", _OBJ.format("ass-objs", "ass.c"))]
    if len(compile_c) != 1 or "CONFIG_ASM=1" not in compile_c[0] or "ARCH_X86_64=1" not in compile_c[0]:
        raise RuntimeError("ass.c is not compiled with CONFIG_ASM=1 and ARCH_X86_64=1.")
    if "NO_ASM" in graph:
        raise RuntimeError("NO_ASM appears in the build graph.")
    version = re.search(r"CONFIG_SOURCEVERSION=(.*?)(?=\s+[-/][A-Za-z]|$)", compile_c[0])
    return {"config_sourceversion_hosted": version[1] if version else None,
            "config_sourceversion_note": "From git describe in a shallow tag-less checkout; the vendor value is "
                                         "not retained and no identical version metadata is claimed."}


def inventory(directory: Path) -> dict:
    if not directory.is_dir():
        return {}
    return {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(directory.iterdir())
            if p.is_file()}


def fribidi_proof(before: dict, after: dict, graph: str, build_log: str) -> list:
    """The exact seven generated outputs: absent before, new and non-empty after, with logged commands."""
    proof = []
    for name, generator in FRIBIDI_OUTPUTS.items():
        if name in before:
            raise RuntimeError("Generated FriBidi file existed before the build: " + name)
        if name not in after or after[name]["bytes"] <= 0:
            raise RuntimeError("Missing or empty generated FriBidi output: " + name)
        pattern = re.compile(re.escape(generator) + r"(\.exe)?\b[^\n]*?>\s*" + re.escape(name) + r"\b")
        if not pattern.search(graph) or not pattern.search(build_log):
            raise RuntimeError("Generator command not planned and logged for " + name)
        proof.append({"name": name, "generator": generator, **after[name]})
    other = sorted(set(after) - set(before) - set(FRIBIDI_OUTPUTS))
    if other:
        raise RuntimeError("Unexpected new gen.tab files: " + ", ".join(other[:10]))
    return proof


def check_text_evidence(directory: Path) -> None:
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() not in (".json", ".log"):
            raise RuntimeError("Non-text evidence file: " + path.name)


def inspect_source_archive(data: bytes, row: dict) -> None:
    """Preflight exact retained bytes before standard tarfile data-filter extraction."""
    if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError("Source archive size/hash mismatch: " + row["archive"])
    reserved = {"CON", "PRN", "AUX", "NUL"} | {prefix+str(i) for prefix in ("COM", "LPT") for i in range(1, 10)}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) != row["archive_members"]:
            raise ValueError("Source archive member count mismatch.")
        names, links, total = set(), [], 0
        for member in members:
            name = member.name.rstrip("/")
            parts = name.split("/")
            if not name or parts[0] != row["root"] or any(
                    p in ("", ".", "..") or "\\" in p or ":" in p or p.endswith((".", " ")) or
                    p.upper() == ".GIT" or p.split(".")[0].upper() in reserved for p in parts):
                raise ValueError("Unsafe source archive path.")
            if name.casefold() in names:
                raise ValueError("Repeated/colliding source archive path.")
            names.add(name.casefold())
            if member.issym():
                links.append({"name": member.name, "target": member.linkname})
            elif not (member.isfile() or member.isdir()):
                raise ValueError("Unsupported source archive member type.")
            if member.isfile():
                total += member.size
        if links != row["link_members"] or total != row["uncompressed_file_bytes"]:
            raise ValueError("Source archive links or uncompressed size mismatch.")


def extract_source_bundle(bundle: Path, work: Path, manifest: dict) -> list:
    """Read a hash-pinned ZIP of original archives; never execute source or use Git."""
    expected = manifest["source_bundle"]
    if bundle.is_symlink() or not bundle.is_file() or bundle.stat().st_size != expected["bytes"] or digest(bundle) != expected["sha256"]:
        raise ValueError("Retained source bundle size/hash mismatch.")
    rows = manifest["archives"]
    if [(r["location"], r["repository"], r["commit"]) for r in rows] != list(SOURCES):
        raise ValueError("Retained source archive pins differ from the build pins.")
    if not hasattr(tarfile, "data_filter"):
        raise RuntimeError("Source extraction requires tarfile.data_filter.")
    payloads = []
    with zipfile.ZipFile(bundle) as source_zip:
        infos = source_zip.infolist()
        if [i.filename for i in infos] != [r["archive"] for r in rows] or any(
                i.compress_type != zipfile.ZIP_STORED or i.file_size != r["bytes"]
                for i, r in zip(infos, rows)):
            raise ValueError("Unexpected source ZIP members or compression.")
        for row in rows:
            data = source_zip.read(row["archive"])
            inspect_source_archive(data, row)
            payloads.append(data)
    records = []
    # All twelve payloads pass before any source is written. Parents precede gitlink children.
    staging_root = work / "archive-staging"
    staging_root.mkdir(exist_ok=False)
    for index, (row, data) in enumerate(zip(rows, payloads)):
        destination = work / row["location"]
        if destination.is_symlink() or destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise ValueError("Archive source destination is not empty.")
        staging = staging_root / str(index)
        staging.mkdir()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            # Preserve original names so stdlib's Windows link-copy fallback can find its target.
            archive.extractall(staging, filter="data")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.rmdir()  # only the empty gitlink directory admitted above
        (staging / row["root"]).rename(destination)
        materialized_links = []
        for link in row["link_members"]:
            path = destination / link["name"][len(row["root"])+1:]
            if path.is_symlink():
                if os.readlink(path) != link["target"]:
                    raise ValueError("Extracted source symlink differs.")
                materialized_links.append({**link, "materialized_as": "symlink"})
            elif path.is_file() and path.read_bytes() == (path.parent / link["target"]).read_bytes():
                # tarfile may copy an in-archive link target on Windows without symlink privilege.
                materialized_links.append({**link, "materialized_as": "target-content copy", "sha256": digest(path)})
            else:
                raise ValueError("Extracted source link target missing or changed.")
        records.append({"path":row["location"], "repository":row["repository"], "commit":row["commit"],
                        "archive":row["archive"], "sha256":row["sha256"], "links":materialized_links})
    if any(p.name.casefold() == ".git" for p in work.rglob("*")):
        raise ValueError("Unexpected Git metadata in retained sources.")
    return records


class Run:
    def __init__(self, workspace: Path, environ=None, popen=None, run_tool=None, clock=time.monotonic,
                 sleep=time.sleep):
        environ = os.environ if environ is None else environ
        self.clock, self.sleep = clock, sleep
        self.popen = popen or subprocess.Popen
        self.run_tool = run_tool or subprocess.run
        self.start = clock()
        self.deadline = self.start + WHOLE_SECONDS
        self.evidence = workspace / "native-source-evidence"
        self.evidence.mkdir(exist_ok=False)
        self.work = Path(environ["RUNNER_TEMP"]) / (
            "gyroflowplus-libass-" + environ["GITHUB_RUN_ID"] + "-" + environ["GITHUB_RUN_ATTEMPT"])
        self.work.mkdir(exist_ok=False)
        self.private = self.work / "private"  # never uploaded
        self.private.mkdir()
        self.hooks = self.work / "empty-hooks"
        self.hooks.mkdir()
        self.env = normalize_windows_env(environ)
        self.env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
        self.tools = {}
        self.deferred_private = []  # (record, path) whose deletion Windows refused with a sharing violation
        self.commands = []
        self.sources = []
        self.archive_manifest = None
        self.log_total = 0

    def save(self, name, value):
        (self.evidence / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def stop_tree(self, process) -> list:
        """Stop only the process tree rooted at our own child; our open handle keeps its PID from reuse."""
        notes = []
        try:
            result = self.run_tool(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=15, check=False)
            notes.append({"step": "taskkill own PID tree", "exit_code": result.returncode})
        except Exception as exc:
            notes.append({"step": "taskkill own PID tree", "error": type(exc).__name__})
        for step in ("wait", "terminate own handle"):
            try:
                if step != "wait":
                    process.kill()
                process.wait(timeout=15)
                notes.append({"step": step, "exit_code": process.returncode})
                break
            except Exception as exc:
                notes.append({"step": step, "error": type(exc).__name__})
        return notes

    def dispose_private(self, log: Path) -> dict:
        """Delete a private capture. Only a Windows sharing violation is tolerated: a process outside our control
        can still hold an inherited handle after our child exits. The bytes are then truncated away and deletion is
        attempted once more at the end of the run. Every other error is reported, never hidden."""
        try:
            log.unlink()
            return {"state": "deleted"}
        except FileNotFoundError:
            return {"state": "absent"}
        except OSError as exc:
            if getattr(exc, "winerror", None) != ERROR_SHARING_VIOLATION:
                return {"state": "error", "error_type": type(exc).__name__,
                        "winerror": getattr(exc, "winerror", None)}
        disposition = {"state": "deletion deferred", "winerror": ERROR_SHARING_VIOLATION}
        try:
            with log.open("r+b") as handle:
                handle.truncate(0)
            disposition["contents"] = "truncated to 0 bytes"
        except OSError as exc:
            disposition["contents"] = "truncation refused"
            disposition["truncate_error"] = {"error_type": type(exc).__name__,
                                             "winerror": getattr(exc, "winerror", None)}
        return disposition

    def finish_private(self, strict=True) -> None:
        """One final deletion attempt for deferred private captures; no waiting and no process cleanup."""
        pending, self.deferred_private = self.deferred_private, []
        errors = []
        for record, log in pending:
            final = self.dispose_private(log)
            if final["state"] == "deletion deferred":
                final["state"] = "still held at end; left in RUNNER_TEMP, outside the uploaded evidence"
            record["private_disposition"]["final"] = final
            if final["state"] == "error":
                errors.append(record["number"])
        if pending:
            self.save("COMMANDS.json", self.commands)
        if errors and strict:
            raise RuntimeError("Private capture removal failed for command(s) " + ", ".join(map(str, errors)) + ".")

    def command(self, args, cwd=None, seconds=300, private=False, cmdline=None):
        """Run one bounded command and keep its receipt whatever happens; private output is never uploaded."""
        args = [str(x) for x in args]
        number = len(self.commands) + 1
        log = (self.private if private else self.evidence) / f"command-{number:03d}.log"
        began = self.clock()
        limit = min(self.deadline, began + seconds)
        cap = MAX_LOG_BYTES if private else min(MAX_LOG_BYTES, MAX_TOTAL_LOG_BYTES - self.log_total)
        if began >= limit or cap <= 0:
            raise RuntimeError("Whole-run deadline or aggregate log bound reached before command.")
        record = {"number": number, "argv": [cmdline] if cmdline else args, "cwd": str(cwd or self.work),
                  "log": None if private else log.name, "private_output": private, "status": "started",
                  "started_utc": utc(), "started_after_seconds": round(began - self.start, 3),
                  "seconds_allowed": round(limit - began, 3), "log_cap_bytes": cap}
        self.commands.append(record)
        self.save("COMMANDS.json", self.commands)
        process, stopped, cleanup, data = None, None, [], None
        try:
            with log.open("wb") as output:
                process = self.popen(cmdline or args, cwd=cwd or self.work, env=self.env,
                                     stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                record["pid"] = process.pid
                while process.poll() is None:
                    if self.clock() >= limit:
                        stopped = "deadline"
                    elif log.stat().st_size > cap:
                        stopped = "log bound"
                    if stopped:
                        cleanup = self.stop_tree(process)
                        break
                    self.sleep(POLL_SECONDS)
        except BaseException as exc:
            record["runner_error"] = type(exc).__name__ + ": " + str(exc)[:300]
            if process is not None and process.returncode is None and not cleanup:
                cleanup = self.stop_tree(process)
            raise
        finally:
            size = log.stat().st_size if log.exists() else 0
            if size > cap and not stopped:
                stopped = "log bound"  # exited between polls with more output than the cap
            record.update(status=stopped or ("runner error" if "runner_error" in record else "exited"),
                          exit_code=None if process is None else process.returncode, stopped=stopped,
                          cleanup=cleanup, ended_utc=utc(), seconds=round(self.clock() - began, 3), bytes=size)
            if not private and size:
                record["sha256"] = digest(log)
                if size > cap:
                    with log.open("r+b") as handle:
                        handle.truncate(cap)
                    record["retained_bytes"] = cap
            if not private:
                self.log_total += min(size, cap)
            else:
                if "runner_error" not in record and not stopped and process.returncode == 0:
                    try:
                        data = log.read_bytes()
                    except OSError as exc:
                        record["private_read_error"] = type(exc).__name__
                record["private_disposition"] = self.dispose_private(log)
                if record["private_disposition"]["state"] == "deletion deferred":
                    self.deferred_private.append((record, log))
            self.save("COMMANDS.json", self.commands)
        if stopped or process.returncode:
            raise RuntimeError(f"Command {number} failed ({stopped or 'exit ' + str(process.returncode)}).")
        if private:
            if data is None or record["private_disposition"]["state"] == "error":
                raise RuntimeError(f"Command {number}: private capture could not be read or removed.")
            return data
        return log.read_bytes().decode("utf-8", errors="replace")

    def git(self, args, cwd=None):
        return self.command([self.tools["git.exe"], "-c", "credential.helper=", "-c", "core.autocrlf=false",
                             "-c", "core.hooksPath="+str(self.hooks), "-c", "submodule.recurse=false",
                             "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", *args], cwd, 60)

    def acquire(self):
        if self.env.get(SOURCE_MODE, "git") == "archives":
            self.archive_manifest = json.loads(Path(__file__).with_name("libass-source-archives.json").read_text())
            bundle = Path(self.env["LIBASS_SOURCE_BUNDLE"])
            self.sources = extract_source_bundle(bundle, self.work, self.archive_manifest)
            for row in self.archive_manifest["unicode_data"]:
                path = self.work / "devpkgs/src/fribidi" / row["path"]
                if path.is_symlink() or not path.is_file() or path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
                    raise RuntimeError("FriBidi Unicode source input mismatch: " + row["path"])
            self.save("SOURCES.json", self.sources)
            self.save("ARCHIVE-ACQUISITION.json", {"mode":"retained archives", "bundle":self.archive_manifest["source_bundle"],
                      "unicode_inputs":self.archive_manifest["unicode_data"], "git_checkout_used":False,
                      "network_isolation_enforced":False, "public_release_approved":False})
            return
        git = shutil.which("git.exe", path=self.env.get("PATH"))
        if not git:
            raise RuntimeError("Missing required tool: git.exe")
        self.tools["git.exe"] = git
        for location, repository, commit in SOURCES:
            destination = self.work / location
            destination.mkdir(parents=True, exist_ok=True)
            # Parent checkouts contain empty gitlink directories. Never reuse an existing Git checkout.
            if (destination / ".git").exists():
                raise RuntimeError("Source checkout already exists.")
            self.git(["init", str(destination)])
            self.git(["remote", "add", "origin", "https://github.com/"+repository+".git"], destination)
            self.git(["fetch", "--no-tags", "--depth=1", "origin", commit], destination)
            self.git(["checkout", "--detach", "FETCH_HEAD"], destination)
            actual = self.git(["rev-parse", "HEAD"], destination).strip()
            if actual != commit:
                raise RuntimeError("Source commit mismatch.")
            self.git(["fsck", "--strict", "--no-reflogs", "--no-dangling"], destination)
            tree = self.git(["rev-parse", "HEAD^{tree}"], destination).strip()
            self.sources.append({"path":location, "repository":repository, "commit":actual, "tree":tree})
            self.save("SOURCES.json", self.sources)

    def developer_environment(self, developer: Path) -> None:
        text = str(developer)
        if any(c in text for c in '"%^&|<>!\r\n'):
            raise RuntimeError("Unsupported developer script path.")
        # Passed verbatim: a list would be re-quoted with \" which cmd.exe does not understand.
        cmdline = f'cmd.exe /d /s /c ""{text}" -no_logo -arch=x64 -host_arch=x64 >nul && set"'
        captured = self.command([], seconds=120, private=True, cmdline=cmdline)
        self.env = merge_windows_env(self.env, captured.decode("oem" if sys.platform == "win32" else "utf-8"))

    def toolchain(self):
        vswhere = Path(self.env["PROGRAMFILES(X86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
        install = self.command([vswhere, "-latest", "-products", "*", "-requires",
                                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"]).strip()
        developer = Path(install) / "Common7/Tools/VsDevCmd.bat"
        if not developer.is_file():
            raise RuntimeError("MSVC developer environment unavailable.")
        self.developer_environment(developer)
        # Identity of the hosted toolchain actually used (no new commands; the vswhere output is also logged).
        self.save("TOOLCHAIN.json", {"vswhere_installation_path": install,
                                     "developer_script": str(developer), "developer_script_sha256": digest(developer),
                                     "note": "Tool paths and hashes follow in <tool>.json; no version is inferred "
                                             "from the installation directory name."})
        # Child lookup on Windows uses this process's PATH, not env=; always call tools by resolved path.
        for tool in TOOLS:
            path = shutil.which(tool, path=self.env["PATH"])
            if not path:
                raise RuntimeError("Missing required tool: "+tool)
            self.tools[tool] = path
            self.save(tool+".json", {"tool":tool, "path":path, "sha256":digest(Path(path))})
        self.command([self.tools["cmake.exe"], "--version"])
        self.command([self.tools["ninja.exe"], "--version"])
        self.command([self.tools["perl.exe"], "-e", "print $^V"])

    def prepare_nasm_makefile(self, nasm: Path) -> dict:
        """Write the derived NASM recipe beside the untouched original and record both hashes and the diff."""
        original_path, derived_path = nasm / NASM_MAKEFILE, nasm / NASM_COMPAT_MAKEFILE.replace("\\", "/")
        original = original_path.read_bytes()
        derived, changes = derive_nasm_makefile(original)
        if hashlib.sha256(derived).hexdigest() != NASM_COMPAT_SHA256:
            raise RuntimeError("Derived NASM makefile differs from the reviewed transform.")
        configuration = nasm_configuration(nasm)
        with derived_path.open("xb") as output:  # fresh only; never reuse or overwrite
            output.write(derived)
        diff = "".join(difflib.unified_diff(original.decode("ascii").splitlines(True),
                                            derived.decode("ascii").splitlines(True),
                                            "a/" + NASM_MAKEFILE, "b/" + NASM_COMPAT_MAKEFILE.replace("\\", "/")))
        record = {"original": NASM_MAKEFILE, "original_sha256": hashlib.sha256(original).hexdigest(),
                  "original_bytes": len(original), "derived": NASM_COMPAT_MAKEFILE,
                  "derived_sha256": hashlib.sha256(derived).hexdigest(), "derived_bytes": len(derived),
                  "changes": changes, "unified_diff": diff,
                  "configuration_headers": configuration,
                  "note": "Build-recipe grammar/shell adaptation plus omission of the absent unconfig.h template "
                          "prerequisite only; exact official configuration headers preserved. No NASM source, version "
                          "or flag change; other prerequisites unchanged."}
        self.save("NASM-MAKEFILE.json", record)
        return record

    def check_nasm_makefiles(self, nasm: Path, record: dict) -> None:
        if digest(nasm / NASM_MAKEFILE) != record["original_sha256"] or \
                digest(nasm / NASM_COMPAT_MAKEFILE.replace("\\", "/")) != record["derived_sha256"]:
            raise RuntimeError("A NASM makefile changed during the NASM build.")
        if nasm_configuration(nasm) != record["configuration_headers"]:
            raise RuntimeError("NASM configuration header evidence changed during the build.")

    def build(self):
        nasm = self.work / "nasm"
        recipe = self.prepare_nasm_makefile(nasm)
        before = {p: (nasm / p).is_file() for p in NASM_PERLREQ}
        self.command([self.tools["nmake.exe"], "/f", NASM_COMPAT_MAKEFILE, "perlreq"], nasm, 300)
        missing = [p for p in NASM_PERLREQ if not (nasm / p).is_file() or not (nasm / p).stat().st_size]
        if missing:
            raise RuntimeError("NASM perlreq did not produce: " + ", ".join(missing[:10]))
        self.command([self.tools["nmake.exe"], "/f", NASM_COMPAT_MAKEFILE, "nasm.exe"], nasm, 300)
        self.check_nasm_makefiles(nasm, recipe)
        version = self.command([nasm / "nasm.exe", "-v"], nasm)
        if not version.startswith("NASM version 2.16.01 "):
            raise RuntimeError("Unexpected NASM version.")
        source = self.work / "devpkgs"
        build = self.work / "build"
        gen_tab = source / "src/fribidi/gen.tab"
        fribidi_before = inventory(gen_tab)
        ninja = [self.tools["ninja.exe"], "-C", build]
        self.command([self.tools["cmake.exe"], "-S", source, "-B", build, "-G", "Ninja",
                      "-DCMAKE_MAKE_PROGRAM="+self.tools["ninja.exe"],
                      "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_SYSTEM_PROCESSOR=x64",
                      "-DCMAKE_SYSTEM_VERSION=6.0", "-DMIN_SIZE=1", "-DUSE_ARC=0",
                      "-DWITH_LTO_STATIC=1", "-DCMAKE_VERBOSE_MAKEFILE=1", "-DFRIBIDI_GENTAB=1",
                      "-DBUILD_LIBASS=1", "-DBUILD_FT=1", "-DBUILD_HB=1", "-DBUILD_WOLFSSL=0",
                      "-DBUILD_DAV1D=0", "-DBUILD_VALD=0", "-DBUILD_LZ4=0", "-DBUILD_TESTING=0",
                      "-DFETCHCONTENT_FULLY_DISCONNECTED=ON", "-DFETCHCONTENT_UPDATES_DISCONNECTED=ON",
                      "-DCMAKE_ASM_NASM_COMPILER="+str(nasm / "nasm.exe"),
                      "-DCMAKE_INSTALL_PREFIX="+str(self.work / "unused-install")] +
                     (["-DCMAKE_DISABLE_FIND_PACKAGE_Git=TRUE"] if self.archive_manifest else []), seconds=300)
        graph = self.command(ninja + ["-t", "commands", "ass"])
        assembly = check_assembly(graph)
        if self.archive_manifest:
            if "commit: unknown." not in (assembly["config_sourceversion_hosted"] or ""):
                raise RuntimeError("Archive build did not use upstream unknown-version fallback.")
            assembly["config_sourceversion_note"] = "Retained source archives; Git discovery disabled. Upstream unknown-version fallback, not vendor metadata."
        line = link_line(graph)
        first_log = self.command(ninja + ["-j", "2", "-v", "-d", "keeprsp", "ass"], seconds=600)
        if line not in first_log:
            raise RuntimeError("Executed libass.dll link differs from the planned link command.")
        inputs = link_inputs(line, lambda p: (build / p).read_text(encoding="utf-8", errors="strict"))
        check_link_graph(inputs)
        dll = build / DLL.replace("\\", "/")
        binary = dll.read_bytes()
        pe = struct.unpack_from("<I", binary, 0x3c)[0]
        if binary[pe:pe+4] != b"PE\0\0" or struct.unpack_from("<H", binary, pe+4)[0] != 0x8664:
            raise RuntimeError("Rebuilt output is not an x64 PE DLL.")
        expected = parse_symbol_file((source / "src/libass/libass/libass.sym").read_text(encoding="utf-8"))
        first_exports = parse_dumpbin_exports(self.command([self.tools["dumpbin.exe"], "/exports", dll]))
        compare_exports(expected, first_exports)
        # The link step itself rewrites the DLL, its import library and .exp; everything else must not change.
        implib = build / inputs["implib"][0].replace("\\", "/")
        link_outputs = {implib.resolve(), implib.with_suffix(".exp").resolve()}
        products = {str(p.relative_to(build)):digest(p) for p in build.rglob("*")
                    if p.is_file() and p.suffix.lower() in (".obj", ".lib") and p.resolve() not in link_outputs}
        if not all(o.replace("\\", os.sep) in products for o in VENDOR_OBJECTS + VENDOR_STATIC_LIBRARIES):
            raise RuntimeError("Missing relink objects or static libraries.")
        first = digest(dll)
        # Only delete our fresh generated DLL. Retain every source/object/static library, then relink.
        dll.unlink()
        relink_log = self.command(ninja + ["-j", "2", "-v", "ass"], seconds=180)
        changed = sorted(p for p, h in products.items() if digest(build / p) != h)
        if changed:
            raise RuntimeError("Relink changed retained object/static-library bytes: " + ", ".join(changed[:5]))
        again = parse_dumpbin_exports(self.command([self.tools["dumpbin.exe"], "/exports", dll]))
        compare_exports(first_exports, again)
        fribidi = fribidi_proof(fribidi_before, inventory(gen_tab), graph, first_log)
        if self.archive_manifest and fribidi != self.archive_manifest["expected_fribidi_outputs"]:
            raise RuntimeError("Archive build FriBidi outputs differ from the qualified Git-source build.")
        self.save("BUILD-PROOF.json", {
            "assembly_enabled": True, **assembly, "link_graph": inputs, "link_command": line,
            "executed_link_command_matches_plan": True, "exports": expected,
            "nasm_perlreq_present_before": before, "first_dll_sha256": first,
            "relinked_dll_sha256": digest(dll), "relink_command_lines": len(relink_log.splitlines()),
            "link_outputs_excluded": sorted(str(p.name) for p in link_outputs),
            "object_and_static_library_sha256": products, "relink_objects_unchanged": True,
            "generated_fribidi_outputs": fribidi, "limits": NOT_RUN})


def main():
    require_host()
    run = Run(Path(os.environ["GITHUB_WORKSPACE"]))
    run.save("RESULT.json", {"status": "started", "started_utc": utc(), "public_release_approved": False})
    try:
        run.acquire()
        run.toolchain()
        run.build()
        run.finish_private()
    except BaseException as exc:
        run.finish_private(strict=False)
        run.save("RESULT.json", {"status":"failed", "error_type":type(exc).__name__,
                                 "error":str(exc)[:500], "seconds":run.clock()-run.start,
                                 "ended_utc": utc(), "public_release_approved":False})
        raise
    finally:
        check_text_evidence(run.evidence)
    run.save("RESULT.json", {"status":"source build and relink passed", "seconds":run.clock()-run.start,
                             "ended_utc": utc(), "public_release_approved":False,
                             "complete_corresponding_source":False,
                             "app_runtime_or_installed_files_changed":False, "limits": NOT_RUN})


if __name__ == "__main__":
    main()
