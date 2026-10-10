# Post-LUT video tone prototype

Gyroflow Plus adds neutral-by-default Highlights/Shadows (-50% to +50%) after
the selected LUT and existing brightness/contrast. Positive values lift the
named range; negative values darken it. This is a bounded video curve operating
on each RGB channel. It is not RAW highlight recovery, an exposure-in-stops
control, HDR mastering, or automatic color management. Select a LUT that turns
the recording into viewing-ready video when appropriate; arbitrary LUTs carry
no inferred transfer-function/working-space guarantees. No per-frame analysis
or automatic normalization is used.

## Architecture decision

[OpenColorIO 2.4.2 grading transforms](https://opencolorio.readthedocs.io/en/v2.4.2/api/grading_transforms.html)
offer tone-range controls with video, linear and log styles. Primary grading
also supplies style-specific exposure, contrast, gain/gamma/lift and saturation.
Those controls are not interchangeable across encodings, so this prototype uses
only the explicit video-style master Highlights/Shadows with default ranges.

| Approach | Tradeoff / decision |
| --- | --- |
| Native OCIO CPU and generated GPU processors | Most extensible and suitable for a future explicit color-managed pipeline. Requires a new C++ ABI bridge, pinned library and platform dependency packaging, plus a Qt integration for generated shaders/textures. Deferred for the bounded two-control prototype. |
| Shared cached OCIO-derived curve | Chosen prototype: generate reference curves with pinned OCIO, interpolate settings once, compose in OCIO order, and share the exact float curve with native export and Qt. Adds no production dependency or per-pixel interpreter. |
| New hand-designed curve or FFmpeg geq expression | Would invent different control semantics or reintroduce the known interpreter bottleneck. Not chosen. |

`generate_tone_tables.py` samples the independently installed OCIO 2.4.2 CPU
processor at 4097 inputs, for each integer percent -50..50 and each control.
The table provenance, layout and SHA256 are checked in beside the binary data.
Fractional percentages interpolate adjacent parameter curves. Each change
composes **Highlights then Shadows**, matching OCIO, into a 4097-entry float
curve; each sample uses one linear lookup. Preview packs exact IEEE float bytes
into RGB8 texels to avoid half-float quantization and Qt alpha premultiplication.
Both paths use the same table. The bounded table is an approximation of OCIO,
not its full runtime or configurable color-management system.

Processing order: stabilization → float RGB → selected tetrahedral LUT →
existing brightness/contrast and [0,1] clipping → video tone curve → original
encoder pixel format/matrix/range. Both new settings zero bypass the tone stage
completely and keep the previous fast paths. Original recordings are unchanged.
Projects, selected presets and render queues store normalized `shadows` and
`highlights` fields under `output`; absent fields default to zero. Existing LUT
and adjustment export markers are retained; a new explicit video-tone marker
records the applied controls. Older Gyroflow builds can ignore these new fields
and therefore cannot be expected to reproduce nonzero tone settings.

## Current Mac evidence (2026-10-07)

- 16 production parser/filter/curve tests pass, retaining all 13 native/geq
  tests and adding curve bounds, monotonicity, endpoints, neutral bypass and
  invalid settings. No production dependency added.
- Independent OCIO CPU comparison: 28 control combinations, dense ramps,
  fractional parameters, extremes, out-of-range clipping and random RGB;
  maximum float error `1.4901161193847656e-6`. Odd-width/padded shared input,
  alpha, dimensions and timestamps are preserved across repeated filtering.
- Production Qt QSB rendered on Metal matches independent OCIO reference
  within one RGB8 code in eight display cases (with and without the
  DJI LUT, including tone extremes and fractional settings). QSB includes GLSL, HLSL SM5 and Metal outputs, serialization v6.
  Baking HLSL is not Windows runtime proof.
- Newly rendered stabilized eight-second 720p moving-flight exports: all 481
  frames fully decode, timestamps and stream/color properties agree. Against
  independent FFmpeg tetrahedral LUT/geq + OCIO CPU, max error is one ten-bit
  code; 11,771 of 664,934,400 samples differ. This is expected approximation and
  quantization, not bit-identical tone equivalence.
- Three one-second 4K HEVC GPU-option exports fully decode to 62 ten-bit BT.709
  frames. Individual startup-inclusive elapsed times: neutral 1.874s, existing
  LUT/brightness/contrast 3.272s, plus tone 3.392s. Concurrent system work and
  short duration limit these measurements; no full-flight speed claim.

Private source footage, LUTs, generated exports and logs are outside Git under
`_dev/color-tone-prototype/`. Test harnesses and table generator are public.
The neutral old project renders identically to the earlier saved neutral export
for all 481 decoded frames/timestamps. Fresh SHA256 checks confirm the original
recording and official Gyroflow binary are unchanged. A tone-only preset applied
through the full app CLI preserves the previous LUT/brightness/contrast and
saves/reimports the new tone fields successfully. This verifies CLI project and
preset persistence, not native queue editing or restart acceptance.

## Native Mac acceptance (2026-10-07)

The initial OS file-open stall cleared during resumed testing; its cause remains
unconfirmed. No security or permission bypass was used. Native playback of the
DJI O4 Pro moving recording now works, with embedded motion data detected.
Double-click resets each of the four sliders, Reset adjustments leaves the LUT
selected, and the preview comparison switch changes the displayed colors.
The GUI saves the LUT and normalized tone fields; reopening the saved project
after restarting preserves Highlights −25% and Shadows +25%.

A separate local development app is installed at `/Applications/Gyroflow Plus.app`.
Its compiled UI source is `2ddd7dbb5271f9faa6438ab917f5800e6a35f695`, including
Plus beneath the original logo and the Community fork label. The input build
hash is `48216f2cf9fdf9b1f236b992c3e06c96920021821f9fc4b3af5e882a75af6ec3`;
the installed, ad-hoc signed binary hash is
`3f7e0e33c7659833faa0c34967accbe7591424626b11a888bf510fb4ee4cf848`.
Signing changes the binary bytes. The official app and earlier LUT Preview app
remain separate and intact. The runtime has Homebrew dependencies and is not a
portable public release.

The native render queue completed an eight-second 1280×720 HEVC export to a new
filename, preserving the earlier test outputs. ffprobe fully decoded all **481**
frames, reporting `yuv420p10le`, BT.709 and limited range. The comment identifies
the selected DJI LUT, Shadows +25% and Highlights −25%. The displayed queue
counter was 480/480; decoded file count is authoritative. This native acceptance
extends the earlier independent reference evidence; it does not imply every
codec/recording or a new Windows runtime has been tested. Private screenshots,
project copies, queue probe and logs remain under `_dev/color-tone-prototype`.

Windows runtime and portable public-release gates remain in
[the distribution plan](PLUS-DISTRIBUTION.md).
