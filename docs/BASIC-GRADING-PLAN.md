# Basic drone grading

Expanded implementation accepted on the local Mac, 2026-10-07. Public portable
binaries and Windows runtime acceptance remain separate release gates.

## Controls and reversible workflow

Color settings contains manual `.cube` LUT selection, exposure (−2 to +2
display stops), relative temperature and tint (−100% to +100%), brightness,
contrast, highlights and shadows (−50% to +50%), and saturation
(−100% to +100%). Temperature
provides warmer/cooler RGB balance, not measured Kelvin or RAW white balance.
All controls default to zero, support double-click reset, and are included in
project, preset and queue data. Reset adjustments retains the selected LUT.

The original recording and its embedded gyro data remain untouched. The
project saves instructions, so reopening it lets you refine the grade and
export again from the original. DJI O4 Pro D-Log M is 10-bit log video, not
camera RAW. Reversible project editing does not promise Lightroom RAW recovery,
unclipped HDR processing, or recovery of values the camera or LUT discarded.

## Defined processing order

1. Stabilization using the existing Gyroflow pipeline.
2. User-selected viewing LUT, with existing tetrahedral interpolation.
3. Relative RGB balance and exposure in **gamma-2.4 display-linear light**.
4. Existing brightness/contrast and its [0,1] clip, unchanged.
5. Cached sampled OpenColorIO video Highlights/Shadows curve.
6. OpenColorIO-equivalent video saturation and [0,1] clip.
7. Conversion back to the encoder's original pixel format, matrix and range.

Exposure is display-referred after the LUT, not multiplication of camera log
codes or an assumed DJI scene-linear transform. For encoded gamma-2.4 RGB,
decode → channel exposure → encode reduces to a constant multiplier. Powers
are computed once when parameters change; there is no per-pixel power,
expression parser, full OCIO interpreter, or extra encode pass.

Relative balance uses linear channel-stop offsets
`[0.75*warmth+0.25*tint, -0.5*tint, -0.75*warmth+0.25*tint]`, normalized so
neutral white's Rec.709 linear luminance is unchanged. Exposure multiplies
linear display light by `2^stops`. Saturation mixes each channel around video
luminance using `[0.2126, 0.7152, 0.0722]`. It is a simple video grade rather
than a configurable color-management system.

Floating-point RGB stays in use between stages, avoiding needless intermediate
8-bit quantization. Bounded processing and LUT mapping may still clip working
values. Reducing exposure after a LUT cannot restore detail already clipped by
that LUT. Neutral new controls preserve the older rendering paths; the original
ungraded fast path also remains available.

## Reference and frame evidence

- 21 production parser/frame/curve/grade tests passed. Checks include parameter
  bounds, repeated shared odd-width frames, unchanged input padding and alpha,
  ten-bit formats, timestamps, color properties, and neutral compatibility.
- **40** synthetic float-frame cases, with and without the DJI viewing LUT,
  matched independent **OpenColorIO 2.4.2** CPU transforms within
  **4.77e−7**. Exposure reference uses separate exponent/linear GradingPrimary/
  inverse-exponent transforms with `OPTIMIZATION_NONE` to avoid OCIO fast-power
  approximation; saturation uses GRADING_VIDEO GradingPrimary.
- **12** production QSB shader cases on **Metal**, including combined/extreme
  controls and LUT/no-LUT, stayed within **one RGB8 code** of that independent
  reference. QSB contains GLSL 330 / ES 300, HLSL SM5 and MSL 1.2 variants,
  baked in the Qt 6.4-compatible container format. This is not Windows execution.
- Real stabilized eight-second 720p, ten-bit lossless export: all **481 frames**
  fully decoded; timestamps and stream properties equal to the neutral export;
  independent FFmpeg LUT plus OCIO grading reference differs by at most
  **one ten-bit code**. This checks stabilization/color composition for this
  clip, not every codec, camera profile or color space.
- A partial basic-grade preset through the full application CLI saves all four
  new fields while retaining the older brightness/contrast/tone fields.

The full OCIO runtime is only a pinned development reference. Production uses
small native math and the existing sampled tone asset; no new runtime library
or automatic camera/color-space detection is added.

## Matched 4K timing

Three repeats of the same 1-second section (62 frames), 3840×2160 ten-bit HEVC
using VideoToolbox encoding. Wall time includes app startup and pipeline setup;
no other test renderer/reference process ran during this set:

| Case | Median wall time | Range |
| --- | ---: | ---: |
| No LUT or grade | 2.124 s | 1.980–2.127 s |
| DJI LUT + brightness/contrast + highlights/shadows | 3.616 s | 3.504–3.662 s |
| Same plus exposure, temperature, tint, saturation | 3.581 s | 3.492–3.722 s |

The additional four controls were within run-to-run variation of the existing
color path in this short sample. LUT/color conversion still costs time compared
with the ungraded fast path. This is not a full-flight performance guarantee or
proof that the hardware encoder itself applies the color grade.

## Native Mac acceptance and installation

Source implementation `31158acfaa124bc1f6e3fa5c7249e0858355b95b`, with native
preview refresh fix `434cebc3aeca542bb28bcfb4476c63ed82b17ef2`. The actual
Mac UI loaded the original DJI recording and detected embedded motion data.
Four new double-click reset gestures and reset-all were checked; reset-all
retained the LUT. All eight nonzero values survived GUI saving and app restart.
Preview comparison and playback worked. Full preview visibly processed
3840×2160; the initial 32×32 placeholder issue was fixed by explicitly
synchronizing the scene-graph texture after a surface-size change.

A native queue job completed the same eight-second section at 720p ten-bit
HEVC. All 481 fully decoded frame hashes and timestamps exactly match the
command-line export with the same saved settings. The export comment records
the selected LUT and all eight values. This is actual native queue acceptance,
not only a filter or shader test.

Installed separately at `/Applications/Gyroflow Plus.app`. The previous local
Plus app was preserved before replacement. The signed executable SHA-256 is
`d7e1a366a98bb44a1e41a9c4ae1c2374a96c82d3be6323fad2d95b537c1e8982`;
the staged and installed executable match and deep/strict signature validation
passes. This uses the Mac's Homebrew development libraries and is not a
portable public package. Original recordings, official Gyroflow, and private
verification inputs are not part of the published source.
