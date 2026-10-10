#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regenerate the bounded video-tone prototype. Requires opencolorio==2.4.2, numpy.

These are numerical samples of OCIO master Highlights/Shadows, not a color-space
conversion. No config, LUT, exposure normalization or footage is inferred.
Layout: highlights then shadows; -50..50 in integer percent; 4097 float32 LE
samples spanning [0,1]. The runtime composes highlights then shadows, like OCIO.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import PyOpenColorIO as ocio

SAMPLES = 4097
ROOT = Path(__file__).resolve().parents[2]


def processor(shadows=0, highlights=0):
    value = ocio.GradingTone(ocio.GRADING_VIDEO)
    for name, amount in (("shadows", shadows), ("highlights", highlights)):
        control = getattr(value, name)
        control.master = 1 + amount
        setattr(value, name, control)
    transform = ocio.GradingToneTransform(ocio.GRADING_VIDEO)
    transform.setValue(value)
    return ocio.Config.CreateRaw().getProcessor(transform).getDefaultCPUProcessor()


def main():
    if ocio.__version__ != "2.4.2":
        raise RuntimeError("Use the pinned OCIO 2.4.2 reference")
    ramp = np.linspace(0, 1, SAMPLES, dtype=np.float32)
    curves = []
    for name in ("highlights", "shadows"):
        for percent in range(-50, 51):
            rgb = np.repeat(ramp[:, None], 3, axis=1)
            processor(**{name: percent / 100}).applyRGB(rgb)
            curve = rgb[:, 0]
            if not np.isfinite(curve).all() or np.any(np.diff(curve) < 0):
                raise RuntimeError("Nonfinite or nonmonotonic OCIO curve")
            if abs(curve[0]) > 1e-6 or abs(curve[-1] - 1) > 1e-6:
                raise RuntimeError("OCIO changed the video endpoints")
            curves.append(curve)
    data = np.array(curves, dtype="<f4").tobytes()
    output = ROOT / "resources/color/ocio-video-tone-v1.bin"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    report = dict(ocio_version=ocio.__version__, style="GRADING_VIDEO",
                  samples=SAMPLES, parameter_percent=[-50, 50],
                  order=["highlights", "shadows"], bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest())
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
