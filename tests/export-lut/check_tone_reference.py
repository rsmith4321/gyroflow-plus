#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent OCIO 2.4.2 CPU versus production float export and Metal preview.

Usage: python check_tone_reference.py tone_fixture qml output_directory [lut.cube]
Requires numpy, pillow, opencolorio==2.4.2. Uses disposable synthetic fixtures.
Tests dense ramps, fractional controls, extremes, out-of-range samples, shared
odd-width/padded frames, alpha ownership, timestamps, and production QSB.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image
from generate_tone_tables import processor


def main():
    fixture, qml, output = (Path(x).resolve() for x in sys.argv[1:4])
    lut = Path(sys.argv[4]).resolve() if len(sys.argv) > 4 else None
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    rng = np.random.default_rng(7102026)
    w, h = 1025, 65
    rgba = rng.uniform(-0.1, 1.1, (h, w, 4)).astype("<f4")
    rgba[0, :, :3] = np.linspace(0, 1, w)[:, None]
    rgba[:, :, 3] = rng.uniform(0, 1, (h, w))
    rgba.tofile(output / "input.f32")
    results = []
    cases = [(0, 0, s, hi) for s in (-.5, -.217, 0, .319, .5)
             for hi in (-.5, -.237, 0, .413, .5)]
    cases += [(.12, .18, .3, -.4), (-.5, .5, .5, -.5), (.5, -.5, -.5, .5)]
    for i, (b, c, s, hi) in enumerate(cases):
        run = subprocess.run([str(fixture), str(output / "input.f32"), str(output / "actual.f32"),
                              str(output / "tone.rgb"), str(w), str(h), str(b), str(c),
                              str(s), str(hi), "3"], capture_output=True, timeout=30)
        if run.returncode: raise RuntimeError(run.stderr.decode())
        actual = np.fromfile(output / "actual.f32", "<f4").reshape(h, w, 4)
        # The LUT-free neutral path leaves out-of-range RGB untouched.
        if b == c == s == hi == 0:
            expected = rgba[:, :, :3].copy()
        else:
            expected = np.clip((rgba[:, :, :3].astype(np.float64) - .5) * (1 + c) + .5 + b, 0, 1).astype(np.float32)
            processor(s, hi).applyRGB(expected)
        error = float(np.max(np.abs(expected - actual[:, :, :3])))
        if error > 1e-5: raise RuntimeError(f"OCIO reference mismatch {b,c,s,hi}: {error}")
        if not np.array_equal(actual[:, :, 3], rgba[:, :, 3]): raise RuntimeError("Alpha changed")
        results.append(dict(controls=[b,c,s,hi], float_max_error=error))

    # Render the actual compiled shader on Qt's Metal backend. RGB8 display
    # precision permits a single code-value rounding difference.
    rgb = rng.integers(0, 256, (128, 128, 3), dtype=np.uint8)
    Image.fromarray(rgb).save(output / "input.png")
    rgb_float = np.ones((128,128,4), dtype="<f4")
    rgb_float[:,:,:3] = rgb / 255
    rgb_float.tofile(output / "preview-input.f32")
    template = (root / "tests/export-lut/preview-shader-check.qml").read_text()
    Image.new("RGB", (2,2)).save(output / "atlas.png")
    tone_cases = [(.5, -.5), (-.5,.5), (.319,-.237), (0,0)]
    gpu_cases = [(s,hi,False) for s,hi in tone_cases]
    if lut: gpu_cases += [(s,hi,True) for s,hi in tone_cases]
    for s, hi, with_lut in gpu_cases:
        subprocess.run([str(fixture), str(output / "preview-input.f32"), str(output / "preview-output.f32"),
                        str(output / "tone.rgb"), "128", "128", ".12", ".18", str(s),str(hi),"1"] + ([str(lut)] if with_lut else []), check=True)
        size = 0
        if with_lut:
            aw, ah, size = map(int, (output / "atlas-size.txt").read_text().split())
            Image.frombytes("RGB", (aw,ah), (output / "atlas.rgb").read_bytes()).save(output / "atlas.png")
        if s or hi: Image.frombytes("RGB", (256,33), (output / "tone.rgb").read_bytes()).save(output / "tone.png")
        harness = template.replace("../../src/qt_gpu/compiled/color_preview.frag.qsb", (root / "src/qt_gpu/compiled/color_preview.frag.qsb").as_uri())
        harness = harness.replace("brightness: 0.1", "brightness: 0.12").replace("contrast: 0.2", "contrast: 0.18")
        harness = harness.replace("lutSize: 33", f"lutSize: {size}").replace("toneEnabled: 0", f"toneEnabled: {int(bool(s or hi))}")
        (output / "check.qml").write_text(harness)
        env = dict(os.environ, QSG_RHI_BACKEND="metal", QSG_INFO="1")
        run = subprocess.run([str(qml), str(output / "check.qml")],cwd=output,env=env,capture_output=True,timeout=30)
        log = (run.stdout + run.stderr).decode(errors="replace")
        (output / f"gpu-{s}-{hi}-{with_lut}.log").write_text(log)
        if run.returncode or "Failed to" in log or "compilation failed" in log: raise RuntimeError(log)
        actual = np.array(Image.open(output / "actual.png").convert("RGB").resize((128,128),Image.Resampling.NEAREST))
        expected = np.clip((rgb.astype(np.float64) / 255 - .5) * 1.18 + .62,0,1).astype(np.float32)
        if with_lut:
            geq = ':'.join(f"{ch}=\'clip(({ch}(X,Y)-0.5)*1.18+0.62,0,1)\'" for ch in ('r','g','b'))
            import shutil
            shutil.copyfile(lut, output / "reference.cube")
            # Start the independent graph with the same normalized float RGB
            # as Qt. FFmpeg's RGB8->float scaler has different input rounding.
            planar_input = np.stack([rgb_float[:,:,1],rgb_float[:,:,2],rgb_float[:,:,0]]).astype('<f4')
            raw = subprocess.check_output(['ffmpeg','-v','error','-xerror','-f','rawvideo',
                '-pixel_format','gbrpf32le','-video_size','128x128','-i','pipe:0',
                '-vf',f'lut3d=file=reference.cube:interp=tetrahedral,geq={geq}:interpolation=nearest',
                '-pix_fmt','gbrpf32le','-f','rawvideo','-'],input=planar_input.tobytes(),cwd=output)
            planar = np.frombuffer(raw,'<f4').reshape(3,128,128)
            expected = np.stack([planar[2],planar[0],planar[1]],axis=2)
        processor(s,hi).applyRGB(expected)
        expected = np.rint(expected * 255).astype(np.uint8)
        error = int(np.max(np.abs(actual.astype(int) - expected.astype(int))))
        if error > 1: raise RuntimeError(f"GPU versus OCIO mismatch {s,hi}: {error}")
        Image.open(output / "actual.png").save(output / f"gpu-{s}-{hi}-{with_lut}.png")
        results.append(dict(gpu_controls=[s,hi], lut=with_lut, rgb8_max_error=error, backend="Metal"))
    (output / "reference-results.json").write_text(json.dumps(results,indent=2)+"\n")
    print(json.dumps(dict(cpu_cases=len(cases), cpu_max_error=max(x['float_max_error'] for x in results if 'float_max_error' in x),gpu_cases=len(gpu_cases),gpu_max_error=max(x['rgb8_max_error'] for x in results if 'rgb8_max_error' in x))))


if __name__ == "__main__": main()
