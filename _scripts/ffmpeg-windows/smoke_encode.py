#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise a Windows FFmpeg bundle's CLI the way Gyroflow+ exports use it.

Usage:
  smoke_encode.py <FFMPEG_DIR> --work <dir> [--arch arm64]  encode/decode smoke tests
  smoke_encode.py <FFMPEG_DIR> --dump <out.json> list the bundle's components
  smoke_encode.py --diff <full.json> <slim.json> report what a slim bundle drops

Standard library only. Uses only synthetic lavfi input; no media is read.
Hardware encoders need GPUs and are covered by check_windows_ffmpeg.py's
--app-coverage presence check instead.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

VIDEO = "testsrc2=size={size}:rate=25:duration=0.2"
AUDIO = "sine=frequency=440:sample_rate=48000:duration=0.2"
# (name, output file, extra encoder arguments, input size)
CASES = [
    ("libx264", "x264.mp4", ["-pix_fmt", "yuv420p"], "320x180"),
    ("libx265", "x265.mp4", ["-pix_fmt", "yuv420p10le", "-x265-params", "log-level=error"], "320x180"),
    ("librav1e", "rav1e.mkv", ["-speed", "10"], "320x180"),
    ("libaom-av1", "aom.mkv", ["-cpu-used", "8", "-usage", "realtime"], "320x180"),
    ("libsvtav1", "svtav1.mkv", ["-preset", "12"], "320x180"),
    ("prores_ks", "prores.mov", ["-profile:v", "3", "-pix_fmt", "yuv422p10le"], "320x180"),
    ("dnxhd", "dnxhr.mxf", ["-profile:v", "dnxhr_lb", "-pix_fmt", "yuv422p"], "1280x720"),
    ("cfhd", "cfhd.mov", ["-pix_fmt", "yuv422p10le"], "320x180"),
    ("ffv1", "ffv1.mkv", ["-pix_fmt", "yuv444p10le"], "320x180"),
    ("png", "png_%03d.png", ["-pix_fmt", "rgb48be"], "320x180"),
    ("exr", "exr_%03d.exr", ["-pix_fmt", "gbrpf32le"], "320x180"),
]
# BtbN does not build aom for Windows ARM64, in either bundle.
ARM64_ABSENT = {"libaom-av1"}
AUDIO_CASES = [("aac", "aac.mp4"), ("alac", "alac.mov"), ("pcm_s16le", "pcm16.mov"),
               ("pcm_s24be", "pcm24.mov")]
LISTS = ["encoders", "decoders", "muxers", "demuxers", "filters", "hwaccels",
         "protocols", "bsfs"]


def binary(bundle, name):
    root = Path(bundle)
    for path in (root / "bin" / f"{name}.exe", root / "bin" / name):
        if path.is_file():
            return str(path)
    raise RuntimeError(f"No {name} in {root / 'bin'}")


def run(command, cwd=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed:\n{result.stderr[-4000:]}")
    return result.stdout


def smoke(bundle, work, arch="x64"):
    ffmpeg = binary(bundle, "ffmpeg")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    base = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    results = {}
    for encoder, output, extra, size in CASES:
        if arch == "arm64" and encoder in ARM64_ABSENT:
            results[encoder] = "not built for arm64"
            continue
        run(base + ["-f", "lavfi", "-i", VIDEO.format(size=size), "-c:v", encoder]
            + extra + [output], cwd=work)
        decoded = output.replace("%03d", "001")
        run(base + ["-i", decoded, "-f", "null", "-"], cwd=work)
        results[encoder] = "encoded+decoded"
    for encoder, output in AUDIO_CASES:
        run(base + ["-f", "lavfi", "-i", AUDIO, "-c:a", encoder, output], cwd=work)
        run(base + ["-i", output, "-f", "null", "-"], cwd=work)
        results[encoder] = "encoded+decoded"
    # The export LUT path (lut3d, tetrahedral, float RGB) and the test oracle's geq.
    size = 2
    lines = ["LUT_3D_SIZE 2"] + [f"{r} {g} {b}" for b in range(size)
                                 for g in range(size) for r in range(size)]
    (work / "identity.cube").write_text("\n".join(lines) + "\n")
    graph = ("format=gbrpf32le,lut3d=file=identity.cube:interp=tetrahedral,"
             "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)',format=yuv420p")
    run(base + ["-f", "lavfi", "-i", VIDEO.format(size="320x180"), "-vf", graph,
                "-c:v", "libx264", "lut.mp4"], cwd=work)
    results["lut3d+geq"] = "filtered+encoded"
    return results


def dump(bundle):
    ffmpeg = binary(bundle, "ffmpeg")
    lists = {}
    for kind in LISTS:
        text = run([ffmpeg, "-hide_banner", f"-{kind}"])
        names = set()
        if kind in ("hwaccels", "protocols", "bsfs"):
            # One name per line under "...:" section headings.
            names = {line.strip() for line in text.splitlines()
                     if line.strip() and not line.strip().endswith(":")}
        else:
            # A flag legend, a "---" rule, then "<flags> <name> <description>".
            body = text.split("\n")
            start = next(i for i, line in enumerate(body) if line.strip().startswith("--"))
            for line in body[start + 1:]:
                parts = line.split()
                if len(parts) >= 2:
                    names.update(parts[1].split(",") if kind.endswith("muxers") else [parts[1]])
        lists[kind] = sorted(names)
    lists["buildconf"] = run([ffmpeg, "-hide_banner", "-buildconf"]).split()
    return lists


def diff(full_path, slim_path):
    full = json.loads(Path(full_path).read_text())
    slim = json.loads(Path(slim_path).read_text())
    report = {"dropped": {}, "added": {}}
    for kind in LISTS:
        report["dropped"][kind] = sorted(set(full[kind]) - set(slim[kind]))
        report["added"][kind] = sorted(set(slim[kind]) - set(full[kind]))
    report["configure_dropped"] = sorted(set(full["buildconf"]) - set(slim["buildconf"]))
    report["configure_added"] = sorted(set(slim["buildconf"]) - set(full["buildconf"]))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", nargs="?")
    parser.add_argument("--work")
    parser.add_argument("--arch", choices=["x64", "arm64"], default="x64")
    parser.add_argument("--dump")
    parser.add_argument("--diff", nargs=2, metavar=("FULL", "SLIM"))
    args = parser.parse_args()
    try:
        if args.diff:
            print(json.dumps(diff(*args.diff), indent=1, sort_keys=True))
        elif args.bundle and args.dump:
            Path(args.dump).write_text(json.dumps(dump(args.bundle), indent=1, sort_keys=True))
        elif args.bundle and args.work:
            print(json.dumps(smoke(args.bundle, args.work, args.arch), indent=1, sort_keys=True))
        else:
            parser.error("give a bundle with --work or --dump, or --diff FULL SLIM")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
