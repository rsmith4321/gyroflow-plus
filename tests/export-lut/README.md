# Export color regression tests

This standalone crate imports the application color modules directly.
It does not compile or run the native app.

```sh
cargo test --locked --manifest-path tests/export-lut/Cargo.toml
OCIO_ROOT=/path/to/pinned/ocio-2.4.2 cargo test --locked \
  --manifest-path tests/export-lut/Cargo.toml --features ocio-runtime
```

The `camera_format_matrix` tests use synthetic, uniform frames and independent
BT.601/709/2020 YCbCr equations. They cover limited/full range, 8/10-bit planar
and NV12/P010 formats, YUV/RGB output, alpha, out-of-range luma, single LUT
application, neutral controls, and accepted/rejected cube syntax. These
fixtures exercise the production `ExportLut`, `CubeLut`, and
`ffmpeg_encoder_color` modules.

The unspecified-matrix cases characterize the existing FFmpeg BT.601 default;
they do not establish the correct matrix for any particular camera.

The encoder-target tests now invoke the same converter configuration helper
as `ffmpeg_video.rs`, followed by real FFmpeg scaling and LUT processing. They
compare 144 tagged-SDR combinations: BT.601/709/2020 nonconstant-luminance,
limited/full range, six YUV storage formats, and RGB24/RGB48BE/GBRPF32LE targets.
The expected values use independent equations and a non-idempotent LUT; the
suite also checks reused converters, unchanged neutral output, unchanged
unknown-tag behavior, and unchanged YUV converter configuration.

These tests do not run the complete `VideoTranscoder`, MDK preview, hardware
encoding, the actual app's queue restart or real camera clips. Unknown matrix tags
retain the previous policies: the YUV filter path defaults to BT.601, while
the encoder-target RGB path defaults to BT.709. A deliberate product policy
for untagged footage remains open.

The reference tolerance is 1.5 codes at 8 bits and 4 codes at 10 bits to allow
conversion rounding. Alpha and P010 storage checks have separate exact
invariants. The encoder-target RGB comparisons allow 2/255 against the
independent reference and 2.5/219 between quantized RGB and YUV results.
Passing synthetic fixtures is not a general HDR/RAW or camera compatibility
claim.

## Local acceptance, 2026-10-08

The 10 new tests passed on arm64 macOS with FFmpeg 9.0.1 in both the default
path and the pinned official OpenColorIO 2.4.2 feature path. They ran against
production color source from `39b092a7`; no rendering algorithm was changed
by this test addition.

A separate proposed FFmpeg float-input NaN guard is still a candidate pending
x86 and ownership/stride review; it is not included here.

## Encoder-target regression acceptance, 2026-10-08

The production-helper tests reproduced the forced-BT.709 defect for explicitly
tagged BT.601/2020 RGB export, and a full-range YUVJ format with a conflicting
range tag. Color-active RGB delivery now uses FFmpeg's source-tag coefficients
and YUVJ full-range convention. Neutral and ordinary YUV converter policies
remain unchanged. Unsupported matrix tags retain the existing BT.709 fallback.

The complete standalone suites passed on arm64 macOS with FFmpeg 9.0.1:
**35 default tests** and **43 tests with OpenColorIO 2.4.2**, zero failed or
ignored. Both application feature configurations also passed an isolated
`cargo check --locked --offline`; this verifies the full Rust wiring and
build-script C++ compilation, not a new linked binary or app runtime.
Current Windows acceptance remains open. A later scoped Mac candidate-app
observation completed three-frame neutral PNG, LUT PNG and LUT EXR exports
against independent tagged-SDR equations; see
[the integration notes](../../docs/OPENCOLORIO-INTEGRATION.md). It uses a private
Qt binding candidate, private settings and bilinear stabilization. It does
not establish unchanged-dependency release, debug Lanczos4 or Windows
acceptance.

## Queued color snapshots, 2026-10-09

Seven regressions import the production `queued_color` helper and exercise
independent jobs referencing the same project, all nine color fields, explicit
neutral values, older queues, partial or damaged records, JSON round trips and
per-job LUT bookmark resolution. They also assert that non-color output fields
are retained. The bookmark callbacks are fixtures; they do not prove sandbox
access to real moved files.

The full arm64 Mac suites passed **42 default tests** and **50 with official
OpenColorIO 2.4.2**, with zero failures, ignored tests or filtered tests.
The app's actual Rust/C++ wiring passed `cargo check --profile deploy --locked
--offline` with both feature configurations, including the Apple bookmark
branch. This is compile and helper coverage; app restart/UI and Windows
acceptance remain separate checks.
