#!/usr/bin/env python3
"""Pure standard-library tests of our libass hosted-build glue. Everything external is mocked.

Run: python3 -I _scripts/notices/test_rebuild_libass_windows.py
V13_CANDIDATE_DIR and V13_WORKFLOW_PATH may name isolated reviewed candidate files.
V13_LIBASS_SYM may name the pinned libass.sym for the optional 50-export fixture.
V15_NASM_MAKEFILE may name the pinned NASM Mkfiles/msvc.mak for the recipe-adaptation fixture.
V16_NASM_CONFIG_DIR may name the pinned NASM config/ directory for configuration-header fixtures.
V17_HOSTED_GRAPH may name the complete command-094.log from hosted run 38013124997 (data only).

No Windows runner, source build, compiler, assembler, generator, Perl, DLL, network or real
subprocess is used: subprocess.Popen/run are replaced for the whole module and fail if reached.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
CANDIDATE = Path(os.environ.get("V13_CANDIDATE_DIR", HERE))
WORKFLOW_PATH = Path(os.environ.get("V13_WORKFLOW_PATH", HERE.parents[1] / ".github/workflows/native-libass-source.yml"))
STATEMENT = ("NO WINDOWS BUILD OR SOURCE BUILD HAS RUN: no compiler, assembler, generator, Perl, DLL, network "
             "or real subprocess was executed; every external call below is mocked.")


def load():
    spec = importlib.util.spec_from_file_location("rebuild_candidate", CANDIDATE / "rebuild_libass_windows.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # module body defines constants and functions only
    return module


m = load()
_guards = []


def _forbidden(*args, **kwargs):
    raise AssertionError("real subprocess reached: %r" % (args[:1],))


def setUpModule():
    print("\n" + STATEMENT, file=sys.stderr)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        patcher = mock.patch.object(m.subprocess, name, _forbidden)
        patcher.start()
        _guards.append(patcher)


def tearDownModule():
    for patcher in _guards:
        patcher.stop()
    print(STATEMENT, file=sys.stderr)


BRANCH = "codex/lut-preview-controls"
GOOD_ENV = {
    "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Windows",
    "GITHUB_REPOSITORY": "rsmith4321/gyrograde", "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/" + BRANCH, "GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": BRANCH,
    "GITHUB_WORKFLOW_REF": "rsmith4321/gyrograde/.github/workflows/native-libass-source.yml@refs/heads/" + BRANCH,
    "GITHUB_RUN_ID": "123456789", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40,
    "GITHUB_WORKSPACE": "D:\\a\\gyrograde\\gyrograde", "RUNNER_TEMP": "D:\\a\\_temp"}


class Admission(unittest.TestCase):
    def test_manual_dispatch_on_default_branch_is_admitted(self):
        self.assertEqual(m.admission_errors(GOOD_ENV, "win32"), [])

    def check(self, change, platform="win32", expect=None):
        env = dict(GOOD_ENV, **change)
        errors = m.admission_errors(env, platform)
        self.assertTrue(errors, change)
        if expect:
            self.assertIn(expect, errors)

    def test_wrong_repository_or_fork(self):
        self.check({"GITHUB_REPOSITORY": "someone/gyrograde"}, expect="GITHUB_REPOSITORY")
        self.check({"GITHUB_REPOSITORY": "rsmith4321/GyroGrade"}, expect="GITHUB_REPOSITORY")

    def test_wrong_event(self):
        for event in ("push", "pull_request", "pull_request_target", "schedule", "release", "repository_dispatch"):
            self.check({"GITHUB_EVENT_NAME": event}, expect="GITHUB_EVENT_NAME")

    def test_wrong_ref(self):
        for ref in ("refs/heads/main", "refs/heads/master", "refs/tags/" + BRANCH,
                    "refs/heads/" + BRANCH + "-x", "refs/pull/1/merge", "refs/heads/qualification/native-libass-source"):
            self.check({"GITHUB_REF": ref}, expect="GITHUB_REF")
        self.check({"GITHUB_REF_TYPE": "tag"}, expect="GITHUB_REF_TYPE")
        self.check({"GITHUB_REF_NAME": "main"}, expect="GITHUB_REF_NAME")
        self.check({"GITHUB_WORKFLOW_REF": GOOD_ENV["GITHUB_WORKFLOW_REF"].replace(BRANCH, "main")},
                   expect="GITHUB_WORKFLOW_REF")

    def test_wrong_runner(self):
        self.check({"RUNNER_ENVIRONMENT": "self-hosted"}, expect="RUNNER_ENVIRONMENT")
        self.check({"RUNNER_OS": "macOS"}, expect="RUNNER_OS")
        self.check({}, platform="darwin", expect="sys.platform")
        self.check({"GITHUB_ACTIONS": ""}, expect="GITHUB_ACTIONS")

    def test_bad_run_identity(self):
        self.check({"GITHUB_RUN_ID": "12a"}, expect="GITHUB_RUN_ID")
        self.check({"GITHUB_RUN_ATTEMPT": ""}, expect="GITHUB_RUN_ATTEMPT")
        self.check({"GITHUB_SHA": "0" * 40}, expect="GITHUB_SHA")
        self.check({"GITHUB_SHA": "A" * 40}, expect="GITHUB_SHA")

    def test_missing_keys(self):
        for key in GOOD_ENV:
            env = dict(GOOD_ENV)
            del env[key]
            self.assertTrue(m.admission_errors(env, "win32"), key)

    def test_require_host_exits_on_this_machine(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                m.require_host()


class WindowsEnvironment(unittest.TestCase):
    def test_mixed_case_path_leaves_one_current_value(self):
        merged = m.merge_windows_env({"PATH": "C:\\old", "SystemRoot": "C:\\Windows"},
                                     "Path=C:\\VC\\bin;C:\\old\r\nINCLUDE=C:\\VC\\include\r\n=C:=C:\\work\r\n")
        self.assertEqual(merged["PATH"], "C:\\VC\\bin;C:\\old")
        self.assertEqual([k for k in merged if k.upper() == "PATH"], ["PATH"])
        self.assertEqual(merged["SYSTEMROOT"], "C:\\Windows")
        self.assertNotIn("=C:", merged)

    def test_lower_case_base_is_replaced_too(self):
        merged = m.merge_windows_env({"Path": "C:\\stale"}, "PATH=C:\\new\n")
        self.assertEqual(merged, {"PATH": "C:\\new"})

    def test_ambiguous_base_is_refused(self):
        with self.assertRaises(ValueError):
            m.normalize_windows_env({"PATH": "a", "Path": "b"})
        self.assertEqual(m.normalize_windows_env({"PATH": "a", "Path": "a"}), {"PATH": "a"})

    def test_duplicate_or_missing_path_in_capture(self):
        with self.assertRaises(ValueError):
            m.merge_windows_env({}, "Path=a\nPATH=b\n")
        with self.assertRaises(ValueError):
            m.merge_windows_env({"PATH": "a"}, "INCLUDE=x\n")

    def test_value_with_equals_sign_kept(self):
        self.assertEqual(m.merge_windows_env({}, "PATH=a\nX=b=c\n")["X"], "b=c")


DUMPBIN = """Microsoft (R) COFF/PE Dumper Version 14.44.35211.0
Copyright (C) Microsoft Corporation.  All rights reserved.


Dump of file build\\projects\\libass\\libass.dll

File Type: DLL

  Section contains the following exports for libass.dll

    00000000 characteristics
    FFFFFFFF time date stamp
        0.00 version
           1 ordinal base
           {n} number of functions
           {n} number of names

    ordinal hint RVA      name

{rows}
  Summary

        1000 .data
       2D000 .text
"""


def dumpbin(names, extra_rows=(), functions=None, count=None):
    rows = ["%11d %4X %08X %s" % (i + 1, i, 0x1000 + 16 * i, n) for i, n in enumerate(names)]
    rows += list(extra_rows)
    n = len(rows) if count is None else count
    text = DUMPBIN.format(n=n, rows="\n".join(rows))
    if functions is not None:
        text = text.replace("%d number of functions" % n, "%d number of functions" % functions)
    return text


SYM = ["ass_library_init", "ass_library_done", "ass_render_frame", "ass_set_fonts"]


class Exports(unittest.TestCase):
    def test_representative_table_parses_all_names(self):
        self.assertEqual(m.parse_dumpbin_exports(dumpbin(SYM)), SYM)
        m.compare_exports(SYM, m.parse_dumpbin_exports(dumpbin(SYM)))

    def test_extra_export_not_named_ass_is_caught(self):
        names = m.parse_dumpbin_exports(dumpbin(SYM + ["hb_buffer_create"]))
        with self.assertRaises(RuntimeError):
            m.compare_exports(SYM, names)

    def test_missing_export(self):
        with self.assertRaises(RuntimeError):
            m.compare_exports(SYM, m.parse_dumpbin_exports(dumpbin(SYM[:-1])))

    def test_duplicate_name(self):
        with self.assertRaises(ValueError):
            m.parse_dumpbin_exports(dumpbin(SYM + ["ass_set_fonts"]))

    def test_forwarded_ordinal_only_and_decorated_rows(self):
        for row in ("          9    8          ass_x (forwarded to OTHER.ass_x)",
                    "          9      00001000 [NONAME]",
                    "          9    8 00001000 ass_x = ass_x",
                    "          9    8 00001000 ?ass@@YAXXZ",
                    "garbage"):
            with self.assertRaises(ValueError, msg=row):
                m.parse_dumpbin_exports(dumpbin(SYM, extra_rows=[row]))

    def test_count_mismatch_and_layout(self):
        with self.assertRaises(ValueError):
            m.parse_dumpbin_exports(dumpbin(SYM, count=5))
        with self.assertRaises(ValueError):
            m.parse_dumpbin_exports(dumpbin(SYM, functions=9))
        with self.assertRaises(ValueError):
            m.parse_dumpbin_exports("no table here")
        with self.assertRaises(ValueError):
            m.parse_dumpbin_exports(dumpbin(SYM).replace("  Summary", ""))
        text = dumpbin(SYM)
        with self.assertRaises(ValueError):
            m.parse_dumpbin_exports(text + text)

    def test_symbol_file(self):
        self.assertEqual(m.parse_symbol_file("ass_a\r\n\nass_b\n"), ["ass_a", "ass_b"])
        for bad in ("", "\n\n", "ass_a\nass_a\n", "ass_a\n# comment\n", "ass_a ass_b\n"):
            with self.assertRaises(ValueError, msg=bad):
                m.parse_symbol_file(bad)

    def test_real_libass_sym_if_available(self):
        path = os.environ.get("V13_LIBASS_SYM")
        if not path:
            self.skipTest("V13_LIBASS_SYM not set")
        names = m.parse_symbol_file(Path(path).read_text())
        self.assertEqual(len(names), 50)
        self.assertEqual(m.parse_dumpbin_exports(dumpbin(names)), names)


OUTPUTS = m.FRIBIDI_OUTPUTS


def fribidi_commands():
    return "\n".join(
        'cmd.exe /C "cd . && link.exe /out:projects\\fribidi\\%s.exe && cd /D D:\\a\\_temp\\r\\devpkgs\\src\\fribidi\\'
        'gen.tab && D:\\a\\_temp\\r\\build\\projects\\fribidi\\%s.exe 2 unidata/UnicodeData.txt >%s"' % (g, g, n)
        for n, g in OUTPUTS.items())


CHECKED_IN = {n: {"bytes": 10, "sha256": "0" * 64} for n in ("gen-bidi-type-tab.c", "packtab.c", "meson.build")}


def after_with(names, size=100):
    after = dict(CHECKED_IN)
    after.update({n: {"bytes": size, "sha256": hashlib.sha256(n.encode()).hexdigest()} for n in names})
    return after


class FriBidi(unittest.TestCase):
    def test_exact_seven_with_commands(self):
        proof = m.fribidi_proof(CHECKED_IN, after_with(OUTPUTS), fribidi_commands(), fribidi_commands())
        self.assertEqual(sorted(p["name"] for p in proof), sorted(OUTPUTS))
        self.assertEqual(len(proof), 7)
        self.assertTrue(all(p["bytes"] > 0 and len(p["sha256"]) == 64 for p in proof))

    def test_headers_only_is_rejected(self):
        with self.assertRaises(RuntimeError):
            m.fribidi_proof(CHECKED_IN, after_with(["fribidi-unicode-version.h"]), fribidi_commands(),
                            fribidi_commands())

    def test_each_missing_or_empty_output(self):
        for name in OUTPUTS:
            with self.assertRaises(RuntimeError, msg=name):
                m.fribidi_proof(CHECKED_IN, after_with([n for n in OUTPUTS if n != name]), fribidi_commands(),
                                fribidi_commands())
            after = after_with(OUTPUTS)
            after[name] = {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
            with self.assertRaises(RuntimeError, msg=name):
                m.fribidi_proof(CHECKED_IN, after, fribidi_commands(), fribidi_commands())

    def test_preexisting_file_does_not_prove_generation(self):
        before = dict(CHECKED_IN, **{"mirroring.tab.i": {"bytes": 5, "sha256": "1" * 64}})
        with self.assertRaises(RuntimeError):
            m.fribidi_proof(before, after_with(OUTPUTS), fribidi_commands(), fribidi_commands())

    def test_command_must_be_planned_and_logged(self):
        log = "\n".join(l for l in fribidi_commands().splitlines() if "brackets-type.tab.i" not in l)
        with self.assertRaises(RuntimeError):
            m.fribidi_proof(CHECKED_IN, after_with(OUTPUTS), fribidi_commands(), log)
        with self.assertRaises(RuntimeError):
            m.fribidi_proof(CHECKED_IN, after_with(OUTPUTS), log, fribidi_commands())

    def test_unexpected_new_file(self):
        with self.assertRaises(RuntimeError):
            m.fribidi_proof(CHECKED_IN, after_with(list(OUTPUTS) + ["derived_bidi-type.tab.i"]),
                            fribidi_commands(), fribidi_commands())

    def test_inventory_reads_regular_files(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "a.tab.i").write_bytes(b"x")
            Path(d, "sub").mkdir()
            self.assertEqual(m.inventory(Path(d)), {"a.tab.i": {"bytes": 1,
                             "sha256": hashlib.sha256(b"x").hexdigest()}})
            self.assertEqual(m.inventory(Path(d, "missing")), {})


def graph(objects=None, libs=None, rsp=True, asm_flags="-f win64 -DHAVE_ALIGNED_STACK=1 -DHAVE_CPUNOP=0 -Dprivate_prefix=ass",
          c_defs="-DCONFIG_ASM=1 -DARCH_X86=1 -DARCH_X86_64=1"):
    objects = list(m.VENDOR_OBJECTS if objects is None else objects)
    libs = list(m.VENDOR_STATIC_LIBRARIES if libs is None else libs)
    lines = []
    for name in m.ASM_NAMES:
        obj = m._OBJ.format("ass_asm", "x86\\" + name + ".asm")
        lines.append('"C:\\a\\_temp\\r\\nasm\\nasm.exe" -DARCH_X86_64=1 -DPIC=1 %s -f win64 -o %s '
                     'D:\\a\\_temp\\r\\devpkgs\\src\\libass\\libass\\x86\\%s.asm' % (asm_flags, obj, name))
    lines.append('"C:\\VC\\cl.exe" /nologo %s -DCONFIG_SOURCEVERSION="\\"commit: af5f116d\\"" /MD /Fo%s '
                 '/Fdprojects\\libass\\CMakeFiles\\ass-objs.dir\\ -c D:\\a\\_temp\\r\\devpkgs\\src\\libass\\libass\\ass.c'
                 % (c_defs, m._OBJ.format("ass-objs", "ass.c")))
    body = " ".join(objects + libs + ["gdi32.lib", "user32.lib", "kernel32.lib"])
    link = ('cmd.exe /C "cd . && "C:\\cmake\\bin\\cmake.exe" -E vs_link_dll --intdir=projects\\libass\\CMakeFiles\\ass.dir '
            '-- "C:\\VC\\link.exe" /nologo %s /out:projects\\libass\\libass.dll /implib:projects\\libass\\ass.lib '
            '/pdb:projects\\libass\\libass.pdb /dll /version:0.0 /machine:x64 /LTCG /INCREMENTAL:NO '
            '/DEF:projects\\libass\\ass.def && cd ."') % ("@CMakeFiles\\ass.rsp" if rsp else body)
    lines.append(link)
    return "\n".join(lines), body


class BuildGraph(unittest.TestCase):
    def test_known_transitive_freetype_repeat(self):
        libraries = m.VENDOR_STATIC_LIBRARIES + ("src\\freetype\\freetype.lib",)
        for response in (False, True):
            with self.subTest(response=response):
                text, body = graph(libs=libraries, rsp=response)
                inputs = m.link_inputs(m.link_line(text), lambda path: body)
                m.check_link_graph(inputs)
                self.assertEqual(inputs["project_libraries"], list(libraries))

    def test_other_archive_repeat_counts_are_refused(self):
        base = m.VENDOR_STATIC_LIBRARIES
        cases = [base + (library,) for library in base if library != "src\\freetype\\freetype.lib"]
        cases += [base + ("src\\freetype\\freetype.lib",) * 2,
                  base + ("src\\freetype\\freetype.lib", "src\\harfbuzz\\harfbuzz.lib"),
                  base[:2] + ("src\\freetype\\freetype.lib",),
                  base[:2] + ("src\\freetype\\freetype.lib", base[2]),
                  (base[1], base[0], base[2], base[1])]
        for libraries in cases:
            with self.subTest(libraries=libraries):
                text, _ = graph(libs=libraries, rsp=False)
                with self.assertRaisesRegex(RuntimeError, "static libraries"):
                    m.check_link_graph(m.link_inputs(m.link_line(text), None))

    def test_actual_hosted_graph(self):
        path = os.environ.get("V17_HOSTED_GRAPH")
        if not path:
            self.skipTest("V17_HOSTED_GRAPH not set")
        data = Path(path).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "228e75ce7d77a1bf9dc1f42c153c4c6691b2a525f6482ac54161603513e24477")
        text = data.decode()
        m.check_assembly(text)
        inputs = m.link_inputs(m.link_line(text), lambda path: self.fail("Unexpected response file"))
        m.check_link_graph(inputs)
        self.assertEqual(sorted(inputs["objects"]), sorted(m.VENDOR_OBJECTS))
        self.assertEqual(inputs["project_libraries"],
                         list(m.VENDOR_STATIC_LIBRARIES) + ["src\\freetype\\freetype.lib"])

    def test_vendor_graph_with_response_file(self):
        text, body = graph()
        info = m.check_assembly(text)
        self.assertIn("af5f116d", info["config_sourceversion_hosted"])
        inputs = m.link_inputs(m.link_line(text), lambda p: body if p == "CMakeFiles\\ass.rsp" else 1 / 0)
        m.check_link_graph(inputs)
        self.assertEqual(inputs["implib"], ["projects\\libass\\ass.lib"])

    def test_vendor_graph_inline(self):
        text, body = graph(rsp=False)
        m.check_assembly(text)
        m.check_link_graph(m.link_inputs(m.link_line(text), lambda p: 1 / 0))

    def test_missing_assembly_object(self):
        objects = [o for o in m.VENDOR_OBJECTS if "cpuid" not in o]
        text, body = graph(objects=objects, rsp=False)
        with self.assertRaises(RuntimeError):
            m.check_link_graph(m.link_inputs(m.link_line(text), None))

    def test_unrelated_or_missing_static_library(self):
        for libs in (list(m.VENDOR_STATIC_LIBRARIES) + ["src\\lz4\\lz4.lib"], list(m.VENDOR_STATIC_LIBRARIES)[:2],
                     list(m.VENDOR_STATIC_LIBRARIES) + ["C:\\vcpkg\\installed\\x64\\lib\\freetype.lib"]):
            text, body = graph(libs=libs, rsp=False)
            with self.assertRaises(RuntimeError, msg=libs):
                m.check_link_graph(m.link_inputs(m.link_line(text), None))

    def test_assembly_options_required(self):
        with self.assertRaises(RuntimeError):
            m.check_assembly(graph(asm_flags="-DHAVE_CPUNOP=0 -Dprivate_prefix=ass")[0])
        with self.assertRaises(RuntimeError):
            m.check_assembly(graph(c_defs="-DCONFIG_ASM=0 -DARCH_X86_64=0")[0])
        with self.assertRaises(RuntimeError):
            m.check_assembly(graph()[0] + "\nNO_ASM=1")
        text = graph()[0].splitlines()
        with self.assertRaises(RuntimeError):
            m.check_assembly("\n".join(l for l in text if "x86inc.asm.obj" not in l or "link.exe" in l))

    def test_link_line_must_be_unique(self):
        text = graph()[0]
        with self.assertRaises(RuntimeError):
            m.link_line(text + "\n" + text.splitlines()[-1])
        with self.assertRaises(RuntimeError):
            m.link_line(text.replace("/out:projects\\libass\\libass.dll", "/out:projects\\libass\\other.dll"))


class FakeProcess:
    def __init__(self, stdout, pid=4242, exits_after=None, returncode=0, write=b"", wait_errors=0):
        self.pid, self.returncode, self.polls = pid, None, 0
        self.exits_after, self.code, self.wait_errors, self.killed = exits_after, returncode, wait_errors, False
        stdout.write(write)
        stdout.flush()

    def poll(self):
        self.polls += 1
        if self.exits_after is not None and self.polls >= self.exits_after:
            self.returncode = self.code
        return self.returncode

    def wait(self, timeout=None):
        if self.wait_errors:
            self.wait_errors -= 1
            raise subprocess.TimeoutExpired("fake", timeout)
        if self.returncode is None:
            self.returncode = 1
        return self.returncode

    def kill(self):
        self.killed = True


class Clock:
    def __init__(self, step=1.0):
        self.now, self.step = 1000.0, step

    def __call__(self):
        self.now += self.step
        return self.now


class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "ws").mkdir()
        (root / "temp").mkdir()
        self.environ = {"RUNNER_TEMP": str(root / "temp"), "GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "1",
                        "PATH": "C:\\runner", "Path": "C:\\runner"}
        self.killed = []
        self.popen_args = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, process_factory, taskkill=None, clock=None):
        def popen(args, **kwargs):
            commands = json.loads((run.evidence / "COMMANDS.json").read_text())
            self.assertEqual(commands[-1]["status"], "started")  # start diagnostics written first
            self.popen_args.append(args)
            return process_factory(kwargs["stdout"])

        def run_tool(argv, **kwargs):
            self.killed.append(argv)
            if taskkill:
                raise taskkill
            return subprocess.CompletedProcess(argv, 0)

        run = m.Run(Path(self.tmp.name, "ws"), environ=self.environ, popen=popen, run_tool=run_tool,
                    clock=clock or Clock(0.01), sleep=lambda s: None)
        return run

    def receipt(self, run):
        return json.loads((run.evidence / "COMMANDS.json").read_text())[-1]

    def test_success_returns_log_and_receipt(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=b"cmake version 3.31\n"))
        self.assertIn("cmake version", run.command(["cmake", "--version"]))
        r = self.receipt(run)
        self.assertEqual((r["status"], r["exit_code"], r["bytes"]), ("exited", 0, 19))
        self.assertEqual(r["sha256"], hashlib.sha256(b"cmake version 3.31\n").hexdigest())
        self.assertTrue(r["started_utc"] and r["ended_utc"])
        self.assertEqual(self.killed, [])

    def test_nonzero_exit_fails_with_receipt(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, returncode=3))
        with self.assertRaises(RuntimeError):
            run.command(["ninja"])
        self.assertEqual(self.receipt(run)["exit_code"], 3)

    def test_deadline_kills_only_own_pid_tree_and_keeps_receipt_when_cleanup_fails(self):
        processes = []
        run = self.make(lambda out: processes.append(FakeProcess(out, pid=31337, wait_errors=2)) or processes[-1],
                        taskkill=subprocess.TimeoutExpired("taskkill", 15), clock=Clock(100.0))
        with self.assertRaises(RuntimeError):
            run.command(["ninja"], seconds=300)
        r = self.receipt(run)
        self.assertEqual(r["status"], "deadline")
        self.assertEqual(self.killed, [["taskkill.exe", "/PID", "31337", "/T", "/F"]])
        self.assertTrue(processes[0].killed)  # TerminateProcess on our own handle after taskkill/wait failed
        self.assertEqual([c["step"] for c in r["cleanup"]], ["taskkill own PID tree", "wait", "terminate own handle"])
        self.assertTrue(all("error" in c for c in r["cleanup"]))
        (run.evidence / "RESULT.json").write_text("{}")
        m.check_text_evidence(run.evidence)

    def test_no_name_based_or_global_kill_in_source(self):
        source = (CANDIDATE / "rebuild_libass_windows.py").read_text()
        self.assertNotRegex(source, r'"/IM"|/IM |taskkill[^\n]*\*|pkill|killall|os\.kill|shell=True')

    def test_per_command_log_bound_truncates_retained_log(self):
        self.environ = dict(self.environ)
        with mock.patch.object(m, "MAX_LOG_BYTES", 64):
            run = self.make(lambda out: FakeProcess(out, write=b"x" * 200))
            with self.assertRaises(RuntimeError):
                run.command(["ninja", "-v"])
        r = self.receipt(run)
        self.assertEqual((r["status"], r["bytes"], r["retained_bytes"]), ("log bound", 200, 64))
        self.assertEqual(r["sha256"], hashlib.sha256(b"x" * 200).hexdigest())
        self.assertEqual((run.evidence / r["log"]).stat().st_size, 64)

    def test_aggregate_log_bound(self):
        with mock.patch.object(m, "MAX_TOTAL_LOG_BYTES", 150), mock.patch.object(m, "MAX_LOG_BYTES", 100):
            run = self.make(lambda out: FakeProcess(out, exits_after=1, write=b"y" * 90))
            run.command(["a"])
            with self.assertRaises(RuntimeError):
                run.command(["b"])  # only 60 bytes of the aggregate remain
            self.assertEqual(self.receipt(run)["status"], "log bound")
            self.assertEqual(run.log_total, 150)
            calls = len(self.popen_args)
            with self.assertRaises(RuntimeError):
                run.command(["c"])  # nothing left: refused before start
            self.assertEqual(len(self.popen_args), calls)

    def test_launch_failure_keeps_receipt(self):
        def boom(out):
            raise FileNotFoundError("nmake.exe")
        run = self.make(boom)
        with self.assertRaises(FileNotFoundError):
            run.command(["nmake"])
        r = self.receipt(run)
        self.assertEqual(r["status"], "runner error")
        self.assertIn("FileNotFoundError", r["runner_error"])

    def test_whole_deadline_refuses_new_command(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1))
        run.deadline = run.clock() - 1
        with self.assertRaises(RuntimeError):
            run.command(["git"])
        self.assertEqual(self.popen_args, [])

    def test_mixed_case_runner_environment_is_normalized(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1))
        self.assertEqual([k for k in run.env if k.upper() == "PATH"], ["PATH"])


class Toolchain(unittest.TestCase):
    """Developer environment bootstrap through the bounded runner, private capture, resolved tool paths."""

    def test_bootstrap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for sub in ("ws", "temp", "tools", "VS/Common7/Tools"):
                (root / sub).mkdir(parents=True)
            (root / "VS/Common7/Tools/VsDevCmd.bat").write_text("@rem fake\n")
            for tool in m.TOOLS:
                (root / "tools" / tool).write_bytes(tool.encode())
            new_path = "C:\\VC\\bin\\HostX64\\x64;C:\\runner"
            secret = "ghs_notarealtoken0000"
            environ = {"RUNNER_TEMP": str(root / "temp"), "GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "1",
                       "Path": "C:\\runner", "ProgramFiles(x86)": "C:\\Program Files (x86)",
                       "ACTIONS_RUNTIME_TOKEN": secret}
            seen = []

            def popen(args, **kwargs):
                seen.append((args, kwargs["env"]))
                out = kwargs["stdout"]
                if isinstance(args, str):
                    data = ("Path=%s\r\nINCLUDE=C:\\VC\\include\r\nACTIONS_RUNTIME_TOKEN=%s\r\n" % (new_path, secret))
                elif args[0].endswith("vswhere.exe"):
                    data = str(root / "VS") + "\r\n"
                else:
                    data = "ok\n"
                return FakeProcess(out, exits_after=1, write=data.encode())

            def which(tool, path=None):
                return str(root / "tools" / tool) if path == new_path else None

            run = m.Run(root / "ws", environ=environ, popen=popen, run_tool=None, clock=Clock(0.01),
                        sleep=lambda s: None)
            with mock.patch.object(m.shutil, "which", which):
                run.toolchain()
            cmdline = seen[1][0]
            self.assertEqual(cmdline, 'cmd.exe /d /s /c ""%s" -no_logo -arch=x64 -host_arch=x64 >nul && set"'
                             % (root / "VS/Common7/Tools/VsDevCmd.bat"))
            self.assertEqual(run.env["PATH"], new_path)
            self.assertEqual([k for k in run.env if k.upper() == "PATH"], ["PATH"])
            self.assertEqual(seen[2][0][0], str(root / "tools/cmake.exe"))  # resolved path, not a bare name
            self.assertEqual(seen[2][1]["PATH"], new_path)
            evidence = "".join(p.read_text() for p in run.evidence.iterdir())
            self.assertNotIn(secret, evidence)
            self.assertNotIn("INCLUDE=", evidence)
            self.assertEqual(list((run.work / "private").iterdir()), [])
            capture = json.loads((run.evidence / "COMMANDS.json").read_text())[1]
            self.assertEqual((capture["private_output"], capture["log"], capture["status"]), (True, None, "exited"))
            self.assertNotIn("sha256", capture)
            toolchain = json.loads((run.evidence / "TOOLCHAIN.json").read_text())
            self.assertEqual(toolchain["vswhere_installation_path"], str(root / "VS"))  # reported, not assumed
            self.assertEqual(toolchain["developer_script_sha256"],
                             hashlib.sha256(b"@rem fake\n").hexdigest())
            self.assertFalse(any("2022" in str(v) or "2026" in str(v) for v in toolchain.values()))

    def test_unsafe_developer_path_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "ws").mkdir()
            (root / "temp").mkdir()
            run = m.Run(root / "ws", environ={"RUNNER_TEMP": str(root / "temp"), "GITHUB_RUN_ID": "7",
                        "GITHUB_RUN_ATTEMPT": "1"}, popen=_forbidden, run_tool=_forbidden)
            for bad in ('C:\\a"b\\VsDevCmd.bat', "C:\\%x%\\VsDevCmd.bat", "C:\\a&b\\VsDevCmd.bat"):
                with self.assertRaises(RuntimeError):
                    run.developer_environment(Path(bad))

SECRET = b"Path=C:\\VC\\bin\r\nACTIONS_RUNTIME_TOKEN=ghs_notarealtoken0000\r\n"
_REAL_UNLINK = Path.unlink
_REAL_OPEN = Path.open


def winerror(code, path):
    exc = PermissionError(13, "mocked Windows refusal", str(path))
    exc.winerror = code  # what Windows sets; WinError 32 is ERROR_SHARING_VIOLATION
    return exc


class PrivateCapture(unittest.TestCase):
    """Regression for hosted run 38008920591: deleting the private VsDevCmd capture raised WinError 32."""

    setUp, tearDown, make, receipt = Runner.setUp, Runner.tearDown, Runner.make, Runner.receipt

    def private_unlink(self, refusals):
        """Refuse deletion of files in the private directory with the given winerror codes, then allow it."""
        codes = list(refusals)

        def unlink(path, *args, **kwargs):
            if path.parent.name == "private" and codes:
                raise winerror(codes.pop(0), path)
            return _REAL_UNLINK(path, *args, **kwargs)
        return mock.patch.object(m.Path, "unlink", autospec=True, side_effect=unlink)

    def private_files(self, run):
        return {p.name: p.read_bytes() for p in (run.work / "private").iterdir()}

    def assert_private_kept_out(self, run):
        for path in run.evidence.rglob("*"):
            text = path.read_bytes()
            self.assertNotIn(b"ghs_notarealtoken0000", text, path.name)
            self.assertNotIn(b"C:\\VC", text, path.name)
            self.assertNotIn(b"C:\\\\VC", text, path.name)
        self.assertNotIn("sha256", self.receipt(run))
        self.assertIsNone(self.receipt(run)["log"])

    def capture(self, run, **kwargs):
        return run.command([], seconds=120, private=True, cmdline="cmd.exe /d /s /c \"...\"", **kwargs)

    def test_sharing_violation_is_tolerated_truncated_and_deleted_at_end(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))
        with self.private_unlink([32]):
            self.assertEqual(self.capture(run), SECRET)  # the run continues with the captured environment
        disposition = self.receipt(run)["private_disposition"]
        self.assertEqual(disposition, {"state": "deletion deferred", "winerror": 32,
                                       "contents": "truncated to 0 bytes"})
        self.assertEqual(self.private_files(run), {"command-001.log": b""})
        self.assert_private_kept_out(run)
        run.finish_private()
        self.assertEqual(self.receipt(run)["private_disposition"]["final"], {"state": "deleted"})
        self.assertEqual(self.private_files(run), {})

    def test_still_held_at_end_is_reported_not_fatal(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))
        with self.private_unlink([32, 32]):
            self.capture(run)
            run.finish_private()
        final = self.receipt(run)["private_disposition"]["final"]
        self.assertTrue(final["state"].startswith("still held at end"))
        self.assertEqual(self.private_files(run), {"command-001.log": b""})
        self.assert_private_kept_out(run)

    def test_truncation_also_refused(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))

        def open_(path, mode="r", *args, **kwargs):
            if path.parent.name == "private" and mode == "r+b":
                raise winerror(32, path)
            return _REAL_OPEN(path, mode, *args, **kwargs)
        with self.private_unlink([32]), mock.patch.object(m.Path, "open", autospec=True, side_effect=open_):
            self.assertEqual(self.capture(run), SECRET)
        disposition = self.receipt(run)["private_disposition"]
        self.assertEqual((disposition["contents"], disposition["truncate_error"]),
                         ("truncation refused", {"error_type": "PermissionError", "winerror": 32}))
        self.assert_private_kept_out(run)

    def test_normal_deletion(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))
        self.assertEqual(self.capture(run), SECRET)
        self.assertEqual(self.receipt(run)["private_disposition"], {"state": "deleted"})
        self.assertEqual(self.private_files(run), {})
        self.assertEqual(run.deferred_private, [])
        self.assert_private_kept_out(run)

    def test_other_deletion_errors_stay_errors(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))
        with self.private_unlink([5]):  # access denied is not a sharing violation
            with self.assertRaises(RuntimeError):
                self.capture(run)
        self.assertEqual(self.receipt(run)["private_disposition"],
                         {"state": "error", "error_type": "PermissionError", "winerror": 5})
        self.assertEqual(run.deferred_private, [])
        self.assert_private_kept_out(run)

    def test_error_at_final_attempt_fails_strict_only(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))
        with self.private_unlink([32, 5]):
            self.capture(run)
            with self.assertRaises(RuntimeError):
                run.finish_private()
        self.assertEqual(self.receipt(run)["private_disposition"]["final"]["state"], "error")

    def test_error_at_final_attempt_after_failure_does_not_mask_it(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))
        with self.private_unlink([32, 5]):
            self.capture(run)
            run.finish_private(strict=False)  # main() uses this on the failure path; the original error is kept
        self.assertEqual(self.receipt(run)["private_disposition"]["final"]["state"], "error")
        self.assertEqual(run.deferred_private, [])

    def test_command_failure_stays_failure_with_sharing_violation(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, returncode=1, write=SECRET))
        with self.private_unlink([32]):
            with self.assertRaisesRegex(RuntimeError, r"failed \(exit 1\)"):
                self.capture(run)
        r = self.receipt(run)
        self.assertEqual((r["exit_code"], r["private_disposition"]["state"]), (1, "deletion deferred"))
        self.assertEqual(self.private_files(run), {"command-001.log": b""})
        self.assert_private_kept_out(run)

    def test_deadline_with_cleanup_exceptions_and_sharing_violation(self):
        run = self.make(lambda out: FakeProcess(out, pid=4040, wait_errors=2, write=SECRET),
                        taskkill=subprocess.TimeoutExpired("taskkill", 15), clock=Clock(100.0))
        with self.private_unlink([32]):
            with self.assertRaisesRegex(RuntimeError, "deadline"):
                self.capture(run)
        r = self.receipt(run)
        self.assertEqual(r["status"], "deadline")
        self.assertEqual(self.killed, [["taskkill.exe", "/PID", "4040", "/T", "/F"]])
        self.assertEqual(r["private_disposition"]["state"], "deletion deferred")
        self.assert_private_kept_out(run)

    def test_launch_failure_disposes_empty_capture(self):
        def boom(out):
            raise FileNotFoundError("cmd.exe")
        run = self.make(boom)
        with self.assertRaises(FileNotFoundError):
            self.capture(run)
        r = self.receipt(run)
        self.assertEqual((r["status"], r["private_disposition"]), ("runner error", {"state": "deleted"}))
        self.assertEqual(self.private_files(run), {})

    def test_private_read_failure_is_an_error(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=SECRET))
        real = m.Path.read_bytes

        def read_bytes(path):
            if path.parent.name == "private":
                raise winerror(32, path)
            return real(path)
        with mock.patch.object(m.Path, "read_bytes", autospec=True, side_effect=read_bytes):
            with self.assertRaises(RuntimeError):
                self.capture(run)
        r = self.receipt(run)
        self.assertEqual((r["private_read_error"], r["private_disposition"]), ("PermissionError", {"state": "deleted"}))

    def test_public_logs_unaffected(self):
        run = self.make(lambda out: FakeProcess(out, exits_after=1, write=b"ok\n"))
        with self.private_unlink([32]):
            self.assertEqual(run.command(["cmake", "--version"]), "ok\n")
        self.assertNotIn("private_disposition", self.receipt(run))
        self.assertEqual(run.deferred_private, [])


class NasmRecipe(unittest.TestCase):
    """The guarded derived NASM recipe: exact transform of the pinned file only, used by both nmake calls."""

    def original(self):
        path = os.environ.get("V15_NASM_MAKEFILE")
        if not path:
            self.skipTest("V15_NASM_MAKEFILE not set")
        data = Path(path).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), m.NASM_MAKEFILE_SHA256)
        return data

    def mutated(self, old, new):
        data = self.original().replace(old, new, 1)
        return data, hashlib.sha256(data).hexdigest()

    def headers(self, nasm):
        directory = os.environ.get("V16_NASM_CONFIG_DIR")
        if not directory:
            self.skipTest("V16_NASM_CONFIG_DIR not set")
        for name, size, expected in m.NASM_CONFIGURATION_HEADERS:
            data = (Path(directory) / Path(name).name).read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (size, expected))
            path = nasm / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def test_exact_derived_file_and_changes(self):
        original = self.original()
        derived, changes = m.derive_nasm_makefile(original)
        self.assertEqual(hashlib.sha256(derived).hexdigest(), m.NASM_COMPAT_SHA256)
        self.assertEqual([c["line"] for c in changes], [162, 238, 239, 241, 242, 243, 247, 250, 254, 257, 261, 264, 302, 392])
        old, new = original.decode("ascii").split("\n"), derived.decode("ascii").split("\n")
        self.assertEqual(len(old), len(new))
        differing = [i + 1 for i, (a, b) in enumerate(zip(old, new)) if a != b]
        self.assertEqual(differing, [c["line"] for c in changes])
        for c in changes:
            self.assertEqual((old[c["line"] - 1], new[c["line"] - 1]), (c["original"], c["derived"]))
            self.assertTrue(c["reason"])
        self.assertEqual(m.derive_nasm_makefile(original), (derived, changes))  # deterministic

    def test_unrelated_bytes_dependencies_and_flags_preserved(self):
        original = self.original()
        derived, changes = m.derive_nasm_makefile(original)
        edited = {c["line"] for c in changes}
        old, new = original.decode("ascii").split("\n"), derived.decode("ascii").split("\n")
        for number, line in enumerate(old, 1):
            if number not in edited:
                self.assertEqual(new[number - 1], line, number)
        spelled = lambda lines: [l.replace("$(ALLOBJ_NW:.$(O)=.c)", "$(ALLOBJ_NW:.obj=.c)") for l in lines]
        for kept in ("CFLAGS", "LDFLAGS", "PERLREQ", "nasm$(X):", "ALLOBJ", "NASMLIB", "!INCLUDE msvc.dep"):
            self.assertEqual(spelled([l for l in old if kept in l]), [l for l in new if kept in l], kept)
        dependency = lambda lines: [l for l in lines if l and not l.startswith(("\t", "#", " ")) and ":" in l]
        self.assertEqual([l.replace("$(ALLOBJ_NW:.$(O)=.c)", "$(ALLOBJ_NW:.obj=.c)")
                          .replace("config\\unconfig.h: config\\config.h.in", "config\\unconfig.h:")
                          for l in dependency(old)], dependency(new))
        # Only the absent template prerequisite is omitted; line 241 merely spells O out.
        self.assertEqual(new[161:164], ["config\\unconfig.h:", old[162], old[163]])
        self.assertIn("O               = obj", new)
        self.assertEqual(new[381], "\t$(RUNPERL) tools\\mkdep.pl -M Mkfiles\\msvc.mak -- $(DEPDIRS)")

    def test_every_recursion_names_the_derived_file(self):
        derived, _ = m.derive_nasm_makefile(self.original())
        lines = derived.decode("ascii").split("\n")
        recursions = [(n, l) for n, l in enumerate(lines, 1) if "$(MAKE)" in l and "rem " not in l and "cd doc" not in l]
        self.assertEqual([n for n, _ in recursions], [239, 243, 392])
        for _, line in recursions:
            self.assertIn("/f " + m.NASM_COMPAT_MAKEFILE + " ", line)
        self.assertNotIn("/f Mkfiles\\msvc.mak", derived.decode("ascii"))

    def test_wrong_hash_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            m.derive_nasm_makefile(b"all:\n")
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            m.derive_nasm_makefile(b"")

    def test_changed_original_is_refused_even_with_matching_hash(self):
        for old, new, message in (
                (b"config\\unconfig.h: config\\config.h.in", b"config\\unconfig.h: config\\other.h.in", "text at line 162"),
                (b"\t: > asm\\warnings.time", b"\t: > asm\\warnings.stamp", "text at line 242"),
                (b"O               = obj", b"O               = o", "context at line 53"),
                (b"\t$(RUNPERL) $< $@", b"\t$(RUNPERL) $< $< $@", "count"),
                (b"\t@: Side effect\n", b"\t@: Side effect\n\t@: Side effect\n", "count"),
                (b"msvc.dep: $(PERLREQ)", b"msvc.dep: $(PERLREQ) $(WARNFILES:=.x)", "unsupported construct"),
                (b"\n", b"\r\n", "line endings")):
            data, sha = self.mutated(old, new)
            with self.assertRaisesRegex(ValueError, message):
                m.derive_nasm_makefile(data, sha)

    def test_moved_line_is_refused(self):
        data, sha = self.mutated(b"# -*- makefile -*-\n", b"")
        with self.assertRaisesRegex(ValueError, "line"):
            m.derive_nasm_makefile(data, sha)

    def test_repeated_or_foreign_input_is_refused(self):
        derived, _ = m.derive_nasm_makefile(self.original())
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            m.derive_nasm_makefile(derived)
        with self.assertRaises(ValueError):
            m.derive_nasm_makefile(derived, hashlib.sha256(derived).hexdigest())  # already adapted
        foreign = b"# Makefile.in\nall:\n\t$(MAKE) $(X:=.y)\n"
        with self.assertRaises(ValueError):
            m.derive_nasm_makefile(foreign, hashlib.sha256(foreign).hexdigest())
        for bad in (b"\xff" * 4, "\u00e9\n".encode()):
            with self.assertRaises(ValueError):
                m.derive_nasm_makefile(bad, hashlib.sha256(bad).hexdigest())

    def runner(self, root):
        for sub in ("ws", "temp"):
            (root / sub).mkdir()
        environ = {"RUNNER_TEMP": str(root / "temp"), "GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "1",
                   "PATH": "C:\\runner"}
        run = m.Run(root / "ws", environ=environ, popen=_forbidden, run_tool=_forbidden,
                    clock=Clock(0.01), sleep=lambda s: None)
        (run.work / "nasm/Mkfiles").mkdir(parents=True)
        return run

    def test_prepare_writes_fresh_copy_and_records_evidence(self):
        original = self.original()
        with tempfile.TemporaryDirectory() as d:
            run = self.runner(Path(d))
            nasm = run.work / "nasm"
            (nasm / "Mkfiles/msvc.mak").write_bytes(original)
            self.headers(nasm)
            headers_before = {name: (nasm / name).read_bytes() for name, _, _ in m.NASM_CONFIGURATION_HEADERS}
            record = run.prepare_nasm_makefile(nasm)
            derived = (nasm / "Mkfiles/msvc.gyroflowplus-compat.mak").read_bytes()
            self.assertEqual((nasm / "Mkfiles/msvc.mak").read_bytes(), original)
            saved = json.loads((run.evidence / "NASM-MAKEFILE.json").read_text())
            self.assertEqual(saved, record)
            self.assertEqual((saved["original_sha256"], saved["original_bytes"]), (m.NASM_MAKEFILE_SHA256, len(original)))
            self.assertEqual((saved["derived_sha256"], saved["derived_bytes"]), (m.NASM_COMPAT_SHA256, len(derived)))
            self.assertEqual(len(saved["changes"]), 14)
            self.assertEqual(saved["configuration_headers"], m.nasm_configuration(nasm))
            self.assertEqual(headers_before, {name: (nasm / name).read_bytes() for name in headers_before})
            diff = saved["unified_diff"]
            self.assertTrue(diff.startswith("--- a/Mkfiles/msvc.mak\n+++ b/Mkfiles/msvc.gyroflowplus-compat.mak\n"))
            body = diff.splitlines()[2:]  # difflib may also show the blank line 240 as removed and re-added
            self.assertEqual([l[1:] for l in body if l.startswith("-") and l != "-"], [c["original"] for c in saved["changes"]])
            self.assertEqual([l[1:] for l in body if l.startswith("+") and l != "+"], [c["derived"] for c in saved["changes"]])
            self.assertEqual(sum(l == "-" for l in body), sum(l == "+" for l in body))
            run.check_nasm_makefiles(nasm, record)
            with self.assertRaises(FileExistsError):  # a second derivation never overwrites
                run.prepare_nasm_makefile(nasm)
            (nasm / "Mkfiles/msvc.gyroflowplus-compat.mak").write_bytes(derived + b"#\n")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                run.check_nasm_makefiles(nasm, record)
            (nasm / "Mkfiles/msvc.gyroflowplus-compat.mak").write_bytes(derived)
            (nasm / "Mkfiles/msvc.mak").write_bytes(original + b"#\n")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                run.check_nasm_makefiles(nasm, record)

    def test_prepare_refuses_unpinned_original_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            run = self.runner(Path(d))
            nasm = run.work / "nasm"
            (nasm / "Mkfiles/msvc.mak").write_bytes(b"all:\n")
            with self.assertRaisesRegex(ValueError, "not the pinned"):
                run.prepare_nasm_makefile(nasm)
            self.assertFalse((nasm / "Mkfiles/msvc.gyroflowplus-compat.mak").exists())
            self.assertFalse((run.evidence / "NASM-MAKEFILE.json").exists())

    def test_prepare_refuses_unreviewed_result(self):
        original = self.original()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(m, "NASM_COMPAT_SHA256", "0" * 64):
            run = self.runner(Path(d))
            nasm = run.work / "nasm"
            (nasm / "Mkfiles/msvc.mak").write_bytes(original)
            with self.assertRaisesRegex(RuntimeError, "reviewed transform"):
                run.prepare_nasm_makefile(nasm)
            self.assertFalse((nasm / "Mkfiles/msvc.gyroflowplus-compat.mak").exists())

    def test_both_nmake_calls_use_the_derived_file(self):
        """Fixture-free: command selection with the recipe helpers mocked."""
        class Stop(Exception):
            pass

        with tempfile.TemporaryDirectory() as d:
            run = self.runner(Path(d))
            nasm = run.work / "nasm"
            run.tools = {tool: "C:\\Program Files\\VS\\" + tool for tool in m.TOOLS}
            calls, order = [], []

            def command(argv, cwd=None, *rest, **kw):
                calls.append(([str(a) for a in argv], cwd))
                order.append("command")
                if argv[-1] == "perlreq":
                    for name in m.NASM_PERLREQ:
                        (nasm / name).parent.mkdir(parents=True, exist_ok=True)
                        (nasm / name).write_bytes(b"x")
                if argv[-1] == "-v":
                    raise Stop()
                return ""

            record = {"original_sha256": "o", "derived_sha256": "d"}
            with mock.patch.object(run, "command", command), \
                    mock.patch.object(run, "prepare_nasm_makefile", lambda n: order.append("prepare") or record), \
                    mock.patch.object(run, "check_nasm_makefiles",
                                      lambda n, r: order.append("check") or self.assertIs(r, record)):
                with self.assertRaises(Stop):
                    run.build()
            nmake = [(argv, cwd) for argv, cwd in calls if argv[0].endswith("nmake.exe")]
            self.assertEqual([argv[1:] for argv, _ in nmake],
                             [["/f", m.NASM_COMPAT_MAKEFILE, "perlreq"], ["/f", m.NASM_COMPAT_MAKEFILE, "nasm.exe"]])
            self.assertTrue(all(cwd == nasm for _, cwd in nmake))
            self.assertEqual(order, ["prepare", "command", "command", "check", "command"])
            self.assertFalse(any("Mkfiles/msvc.mak" in a or "Mkfiles\\msvc.mak" in a for argv, _ in calls for a in argv))

    def test_derived_file_stays_beside_the_original(self):
        self.assertEqual(m.NASM_MAKEFILE, "Mkfiles/msvc.mak")
        self.assertEqual(m.NASM_COMPAT_MAKEFILE, "Mkfiles\\msvc.gyroflowplus-compat.mak")
        self.assertRegex(m.NASM_COMPAT_SHA256, r"^[0-9a-f]{64}$")
        self.assertEqual(m.NASM_MAKEFILE_SHA256, "a1404ea2617c0d0b06e3b064e11a9fbce8f3d6d5d77a79a33e03ec896f4e1f39")

    def test_exact_configuration_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            nasm = Path(directory)
            self.headers(nasm)
            self.assertEqual(m.nasm_configuration(nasm),
                             {name: {"bytes": size, "sha256": sha} for name, size, sha in m.NASM_CONFIGURATION_HEADERS})

    def test_each_missing_or_changed_header_is_refused(self):
        for name, _, _ in m.NASM_CONFIGURATION_HEADERS:
            for mutation in ("absent", "same-size change", "truncated"):
                with self.subTest(name=name, mutation=mutation), tempfile.TemporaryDirectory() as directory:
                    nasm = Path(directory)
                    self.headers(nasm)
                    path = nasm / name
                    data = path.read_bytes()
                    if mutation == "absent":
                        path.unlink()
                    else:
                        path.write_bytes(bytes([data[0] ^ 1]) + data[1:] if mutation == "same-size change" else data[:-1])
                    with self.assertRaisesRegex(RuntimeError, "configuration header"):
                        m.nasm_configuration(nasm)

    def test_symlink_configuration_header_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            nasm = Path(directory)
            self.headers(nasm)
            path = nasm / "config/unconfig.h"
            original = nasm / "original.h"
            path.rename(original)
            path.symlink_to(original)
            with self.assertRaisesRegex(RuntimeError, "nonregular"):
                m.nasm_configuration(nasm)

    def test_unexpected_template_file_directory_or_dangling_link_is_refused(self):
        for kind in ("file", "directory", "dangling link"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                nasm = Path(directory)
                self.headers(nasm)
                template = nasm / "config/config.h.in"
                if kind == "file":
                    template.write_bytes(b"unexpected")
                elif kind == "directory":
                    template.mkdir()
                else:
                    template.symlink_to(nasm / "absent-template")
                with self.assertRaisesRegex(RuntimeError, "Unexpected NASM"):
                    m.nasm_configuration(nasm)

    def test_missing_header_refuses_build_before_copy_or_command(self):
        original = self.original()
        with tempfile.TemporaryDirectory() as directory:
            run = self.runner(Path(directory))
            nasm = run.work / "nasm"
            (nasm / "Mkfiles/msvc.mak").write_bytes(original)
            self.headers(nasm)
            (nasm / "config/unconfig.h").unlink()
            with mock.patch.object(run, "command", side_effect=AssertionError("command must not start")) as command:
                with self.assertRaisesRegex(RuntimeError, "configuration header"):
                    run.build()
            command.assert_not_called()
            self.assertFalse((nasm / "Mkfiles/msvc.gyroflowplus-compat.mak").exists())
            self.assertFalse((run.evidence / "NASM-MAKEFILE.json").exists())

    def test_post_build_header_changes_are_refused(self):
        original = self.original()
        for name, _, _ in m.NASM_CONFIGURATION_HEADERS:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                run = self.runner(Path(directory))
                nasm = run.work / "nasm"
                (nasm / "Mkfiles/msvc.mak").write_bytes(original)
                self.headers(nasm)
                record = run.prepare_nasm_makefile(nasm)
                (nasm / name).write_bytes(b"changed")
                with self.assertRaisesRegex(RuntimeError, "configuration header"):
                    run.check_nasm_makefiles(nasm, record)

    def test_post_build_template_appearance_is_refused(self):
        original = self.original()
        with tempfile.TemporaryDirectory() as directory:
            run = self.runner(Path(directory))
            nasm = run.work / "nasm"
            (nasm / "Mkfiles/msvc.mak").write_bytes(original)
            self.headers(nasm)
            record = run.prepare_nasm_makefile(nasm)
            (nasm / "config/config.h.in").write_bytes(b"unexpected")
            with self.assertRaisesRegex(RuntimeError, "Unexpected NASM"):
                run.check_nasm_makefiles(nasm, record)


class Static(unittest.TestCase):
    def test_python_ast(self):
        tree = ast.parse((CANDIDATE / "rebuild_libass_windows.py").read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.keyword) and n.arg == "shell"]
        self.assertEqual(calls, [])
        strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertIn("workflow_dispatch", strings)
        self.assertNotIn("push", strings)
        self.assertFalse(any("NO_ASM=1" in s or "-DNO_ASM" in s for s in strings))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertNotIn("eval", names)
        self.assertNotIn("exec", names)

    def test_workflow_text(self):
        text = WORKFLOW_PATH.read_text()
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        on = re.search(r"^on:\n((?:  .*\n)+)", body + "\n", re.M)[1]
        self.assertEqual(on, "  workflow_dispatch:\n")  # manual only, no inputs
        self.assertNotRegex(body, r"\bpush\b|pull_request|schedule|branches|tags:|contents: write|release|"
                                  r"secrets\.|\*\*|default_branch")
        self.assertIn("github.repository == '%s'" % m.REPOSITORY, body)
        self.assertIn("github.event_name == 'workflow_dispatch'", body)
        self.assertIn("github.ref == 'refs/heads/%s'" % m.BRANCH, body)
        self.assertRegex(body, r"(?m)^    timeout-minutes: 20$")
        self.assertRegex(body, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("run: python -I _scripts/notices/rebuild_libass_windows.py", body)
        uploads = re.findall(r"(?m)^            (native-source-evidence/\S+)$", body)
        self.assertEqual(uploads, ["native-source-evidence/*.json", "native-source-evidence/*.log"])
        for line in body.splitlines():
            self.assertNotIn("\t", line)
            if "uses:" in line:
                self.assertRegex(line, r"@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
