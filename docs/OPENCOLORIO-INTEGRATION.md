# OpenColorIO basis and direct library integration

Current status, 2026-10-09: the optional `ocio-runtime` feature integrates pinned
official OCIO 2.4.2 for CPU export and generated GPU preview. It is used by the
installed development Mac build and the private Windows validation build.
Cargo's default features still select the earlier lightweight path; no public
packaged release has switched to the official runtime. A general OCIO
configuration/color-space workflow is not implemented.

[Mac development acceptance](OCIO-MAC-ACCEPTANCE.md) records matched hardware
timings and full-app preview/save/export checks. The
[Windows testing notes](WINDOWS-LUT-TESTING.md) distinguish component tests,
native builds and CLI exports from outstanding interactive preview and project
persistence checks. Native dependency-notice integration and distribution
acceptance also remain open. Sections below retain dated implementation and
test history; their original candidate identities are not current release claims.

## Earlier lightweight implementation (Cargo default)

Gyroflow Plus has a lightweight color implementation based on OpenColorIO.
Highlights/Shadows use sampled curves generated with pinned OCIO 2.4.2.
Exposure, relative RGB balance and saturation use native math independently
tested against OCIO processors. Brightness/contrast retain the existing fork
implementation. Export applies the selected `.cube` LUT with FFmpeg `lut3d`;
preview uses the fork's matching tetrahedral LUT shader.

The [basic grading report](BASIC-GRADING-PLAN.md) records the order, clipping,
precision, performance and platform acceptance. This is a bounded video grade,
not the full OCIO runtime, an OCIO configuration workflow or camera RAW processing.

## Can we directly reuse the upstream code?

Yes. [OpenColorIO's BSD 3-clause license](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.4.2/LICENSE)
permits redistribution and modification subject to its conditions. Retain
copyright, license and disclaimer text for reused source and binary distributions;
do not imply upstream endorsement. Existing attribution is in
[`resources/color/OCIO-LICENSE.txt`](../resources/color/OCIO-LICENSE.txt).

However, its internal processing files are not standalone drop-in modules:

- [`GradingPrimaryOpCPU.cpp`](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.4.2/src/OpenColorIO/ops/gradingprimary/GradingPrimaryOpCPU.cpp)
  uses OCIO operation data, dynamic properties, computed parameters and internal
  math/SIMD helpers.
- [`GradingToneOpCPU.cpp`](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.4.2/src/OpenColorIO/ops/gradingtone/GradingToneOpCPU.cpp)
  also depends on OCIO tone parameter preparation and processor state.

Copying these files and replacing their dependencies would create another
maintained fork of the algorithms. To reduce our custom algorithm code, prefer
a pinned official library and its
[supported CPU/GPU processor API](https://opencolorio.readthedocs.io/en/v2.4.2/api/processors.html).

## Integration boundaries

The CPU API can process float images with explicit layout and stride. The GPU
API can generate shader code, uniforms and textures; Gyroflow Plus must still
bind those resources through Qt's preview renderer. The integration must provide:

1. A small C++/Rust bridge using the public API, with exceptions contained on
   the C++ side and validated frame layouts at the boundary.
2. A cached processor for the selected LUT and adjustment values. Avoid creating
   a processor per pixel or frame; each render worker needs appropriate processor
   ownership when dynamic values can change.
3. Matching processing order and slider semantics in CPU export and generated
   GPU preview, using Qt-compatible shaders on Metal, Direct3D and OpenGL.
4. Explicit conversion between decoded YUV formats and the processor's RGB
   working image, preserving color matrix/range, bit depth, alpha and timestamps.
5. Pinned builds and dependency packaging for Mac and Windows, retaining notices
   and source/build provenance.

Official OCIO processors reduce custom color algorithms. They do not decode
video, read gyro metadata, choose the correct camera log profile automatically,
or eliminate application integration work. Broader file support still depends
on the existing decoder and on correctly handling pixel formats and color
metadata. An OCIO configuration would be a separate feature with explicit
input/working/output color-space choices.

## Acceptance before changing the default or public release

Keep the official processor behind the separate development option. Compare
it with the accepted path using neutral/no-LUT, LUT-only and combined grades;
8/10-bit, full/limited range and supported RGB/YUV formats; odd widths/strides;
malformed or unsupported LUTs; and actual Mac/Windows preview and hardware
encoded exports. Measure matched real-clip timings and preview/export agreement.
Do not replace the working path based solely on library maturity or synthetic
CPU results. The dated evidence below records completed checks and their limits;
remaining platform and package gates must pass before changing the default or
publishing a release.

## Initial standalone runtime prototype: 2026-10-07

The [standalone probe](../tests/ocio-runtime/README.md) now builds against the
official OCIO 2.4.2 library and generates both CPU processors and Qt preview
shaders from one transform definition. No upstream processing source was edited.

- **144 CPU cases** cover the exact and cached-tone processors in packed and
  padded planar RGBA layouts. Maximum deviation from the independent reference
  was **4.77e-7**; alpha and planar padding were unchanged.
- **12 actual Metal cases** using generated Qt QSB shaders agree with the CPU
  result within **one RGB8 code**. HLSL SM5 compilation also passed; Windows
  execution has not been tested.
- On this Apple M4 Max, three repeats of five applications to a 3840x2160
  float image gave a median **0.514 s/frame** for the exact combined grade in
  planar layout. The same grade with a 4097-sample official tone curve evaluated
  by OCIO's `Lut1DTransform` took **0.0647 s/frame**, about eight times faster.
  These are single-threaded processor-only timings; file I/O, frame conversion,
  stabilization, encoding, and app scheduling are excluded. They are not a
  comparison with the complete existing export pipeline.
- The local OCIO dylib is about **6 MB**. It still links the development Mac's
  Imath library; this is not a portable package.

The cached path has no custom per-pixel curve or interpolation evaluator. OCIO
generates the curve from the exact parameters and evaluates it through its
own LUT processor; the GPU preview uses direct generated grading code. This
reduces maintained algorithm code while retaining a bounded approximation.
These measurements describe the initial standalone probe. The application bridge,
row concurrency, generated preview resource lifecycle and matched real-clip
checks were subsequently implemented and accepted on the development Mac as
recorded below. The tested official-runtime development build is installed on
that Mac; the Cargo default and public release still use the accepted lightweight
implementation pending Windows and portable package acceptance.

## Experimental app integration

The `ocio-runtime` Cargo feature links official OCIO 2.4.2 through a contained
C ABI. Export prepares one immutable LUT-first processor per grade snapshot,
then applies it to validated writable float RGB frames in disjoint row bands.
Decoded RGB/YUV conversion, stabilization and encoding continue through the
existing application and FFmpeg code. The feature no longer uses our custom
per-pixel adjustment loops or FFmpeg's LUT evaluator. The default build is
unchanged pending native preview and platform acceptance.

The bridge checks signed dimensions/strides, alignment, actual FFmpeg buffer
ownership/extents and RGB/alpha nonoverlap before creating descriptors, and
checks again after copy-on-write. Unsupported negative strides return an error.
It preserves alpha, padding, source buffers and frame metadata. C++ exceptions
never cross the ABI. A fresh OCIO configuration is used for every snapshot:
reusing one configuration across different sampled same-size tone LUTs can
reuse an earlier processor in OCIO 2.4.2; the dense fixture guards this lifecycle.
OCIO also retains parsed files globally by filename. Each canonical LUT snapshot
uses a private temporary path, so the bridge calls public `ClearAllCaches()` after
constructing its immutable exact/CPU processors, and on failed reads. This bounds
otherwise retained parsed LUT data during slider updates. The public API preserves
instance-specific processor data; native pixel/resource checks and retained-processor
concurrency exercise that lifetime separately.

Development build requires `OCIO_ROOT` pointing to the pinned install prefix;
`OCIO_LINK_NAME` may select a differently named Windows import library. Desktop
only. A compile-time and runtime version check both require 2.4.2. Qt ShaderTools
is an additional preview dependency when the feature is selected. The existing
[probe recipe](../tests/ocio-runtime/README.md) records source provenance and
local dependency limitations. This is not yet a portable release recipe.

Windows MSVC builds explicitly enable `/EHsc` for both the OCIO C ABI bridge
and the feature's Qt preview adapter, so their caught C++ errors unwind owned
objects and preview locks. Use a shared OCIO prefix with matching import
libraries and runtime DLLs. Existing Qt installs need ShaderTools checked
separately; the inherited default Windows deploy recipe does not enable this
experimental feature or stage its additional DLLs.

Current CPU acceptance:

- 29 Rust tests cover normal export, negative/malformed planes, allocation
  ownership, copy-on-write, alpha, odd widths/unequal strides, shared processor
  concurrency and GPU resource extraction.
- Fourteen sequential 8/10-bit full/limited YUV, matrix and size transitions
  match independent FFmpeg LUT-plus-affine references exactly in the measured
  cases; the test requires at most one output code.
- Forty independent randomized/ramp grade cases with and without the DJI O4
  LUT differ by at most 5.37e-7 in float RGB. Alpha remains exact.
- The independent C ABI fixture covers 800 concurrent calls, errors, resource
  bounds and LUT-first composition. Dense direct-versus-cached tone checks
  cover 98 settings and 65,577 RGB samples per setting, max error 5.37e-7.
- Actual stabilized DJI O4 footage passes all 481 frames at 1280x720 in deliberate
  lossless HEVC Main 10 exports. Neutral decoded frame hashes, every timestamp
  and stream properties match the accepted renderer exactly. Combined DJI LUT
  plus all eight adjustments matches an independent FFmpeg/OCIO reference within
  one ten-bit code across 664,934,400 samples. These lossless software-encoder
  exports prove pixel and stabilization preservation, not hardware speed.

Native preview resource acceptance:

- The exact production bridge and Qt 3D texture provider pass 82 float32 rendered
  cases on Metal / Apple M4 Max, max CPU/GPU RGB difference 2.39e-7. Cases include
  neutral, grading alone, identity/invert/nonlinear and DJI O4 LUTs with and
  without all eight adjustments, and out-of-range input values.
- Seventy native resource swaps cross the 64-source cache purge threshold.
  Public `QQuickWindow::releaseResources()` and hard scenegraph recreation retain
  the active source/LUT/grade result. Live asset leases retain needed files;
  each regenerated pack has a unique path to prevent stale-owner deletion.
- Native stale/current error delivery, unclaimed-token disposal, invalid texture
  size and a separate actual software-renderer rejection process pass.

OCIO's default GPU optimizer can remove a Range before a LUT because it assumes
every sampler axis clamps. Qt's ShaderEffect sampler exposes U/V clamp but uses
Repeat for W. The bridge disables only `OPTIMIZATION_COMP_RANGE` for GPU shader
generation to retain OCIO's explicit 0..1 input Range. CPU optimization is
unchanged; LUT sampling and grading code remain entirely generated by OCIO.
The tests caught a self-callback during QQuickItem base destruction; the adapter
now disconnects it before member teardown. QML clears prior errors before new
shader adoption so a synchronous shader failure remains visible.

Matched end-to-end timings and full-app Mac paused-video/slider/save/export checks
have passed on the development Mac; see [the acceptance report](OCIO-MAC-ACCEPTANCE.md).
Windows execution and portable dependency packaging remain gates. Shader compilation,
synthetic pixel acceptance or these CPU checks alone do not switch the default
engine or establish a public portable release.

The current development dependencies also need rebuilding for portable Mac
distribution: the local Imath and FFmpeg avcodec/avfilter/x265 libraries have a
macOS 26 minimum and QtShaderTools has a macOS 27 minimum, despite OCIO's macOS
11 and QtCore's macOS 14 minima. Merely
copying those Homebrew dependencies into a bundle does not establish support for
older systems. Use a matching Qt distribution and an explicit common deployment
target; audit each Mach-O slice, resolved dependency and runtime search path.

A separately built [private OCIO dependency candidate](OCIO-DEPENDENCY-ACCEPTANCE.md)
now removes the Homebrew Imath dependency and passes the production CPU and Metal
fixtures. Its compiled arm64 deployment metadata is macOS 11.0. This resolves
the OCIO dependency check; it does not yet establish a portable app or execution
on the declared minimum OS.

## Windows standalone runtime checks: 2026-10-08

Isolated laptop fixtures at source `26c5d828` passed with **OCIO 2.4.2** from the
Windows-owned private prefix and **MSVC 19.51**:

- The production C ABI bridge passed 800 concurrent CPU calls, 400 concurrent
  first-access GPU resource extractions, unequal-stride/guard/error contracts,
  and retained-processor checks across failed and repaired LUT reads.
- The Qt fixture executed on **D3D11 / NVIDIA GeForce RTX 5070 Ti Laptop GPU**.
  All **80** synthetic float32 comparisons passed; maximum component error was
  **2.384185791015625e-7**, below the existing `1e-5` gate. Cache swaps, resource
  recreation, ownership/error tokens and software-renderer rejection passed.
  The optional two DJI O4 LUT cases were not supplied in this run.

The Windows-owned evidence is under
`C:\Users\rsmit\.codex\GyroflowBuildTools\OcioWindowsNative-20261008`.
These standalone compiler commands explicitly use `/EHsc`; they do not establish
the application Cargo build's effective flags, real-video preview/exports, or a
portable DLL closure. Those checks remain pending, and the feature default and
installed/public app are unchanged.

### Supplied-LUT Windows follow-through

A separately brokered run on 2026-10-08 reused the retained `26c5d828` fixture
with the selected, transfer-verified cube. All **82 unique** float32 cases passed
on actual **D3D11 / NVIDIA GeForce RTX 5070 Ti Laptop GPU**, including:

| Case | Maximum absolute RGBA error |
| --- | --- |
| `o4_lut` | `5.960464477539063e-8` |
| `o4_lut_grade` | `1.7881393432617188e-7` |
| Entire suite | `2.384185791015625e-7` |

The existing strict `<1e-5` limit, finite checks and cache/recreation/ownership/error
checks were unchanged. The fixture compares every RGBA component but its original
inputs have alpha one; this adds no non-unit-alpha guarantee. One fixture process
ran, exited zero naturally in **13.672 seconds**, and its owned job had zero active
processes afterward. The protected stage, dependency prefix, prior evidence,
settings and retained Easy Eject preview remained unchanged.

Evidence is under
`C:\Users\rsmit\Documents\Codex\2026-10-08\gyroflow-plus-windows-validation\outputs\native-lut-run-20261008T230213`.
The result SHA256 is
`a82321b1742c4dc0c152f1e4635739dac289c39b772368cd235685b7977eb5e6`;
fixture executable SHA256 is
`7931907492847dbcc41e67cbec8aeed41345331370ac6dfea360cc2eb4855c4a`.
The supplied 33³ cube SHA256 is
`b18162854ab47702068410c33afa98a8cb6eef159fc5a04ce0e65fad0fd8947e`.
Its O4 filename and transfer identity identify the selected test input; its internal
Mavic 3 Pro D-Log M comment does not independently establish manufacturer provenance.

The five production color/adapter files are unchanged Git blobs from `26c5d828`
through `956d357b` (Windows archive bytes use CRLF). The current test source also
has the separately tested exception branch, which this retained fixture predates.
This run proves the standalone adapter and selected LUT comparison; it does not
prove a current-head application build, native MDK video preview/export parity,
encoded-video identity, clean-machine portability or a public runtime switch.

Reviewed source `e4db0995` adds the bounded shader-compilation exception recovery
case described in [the preview fixture](../tests/ocio-preview/README.md). The
case passed separately on the Mac with pinned Qt **6.7.3** and OCIO **2.4.2**:
after the caught failure while the cache mutex was owned, valid same-process
shader preparation and pending-token cleanup succeeded. Source and app settings
identities remained exact. The same committed case subsequently passed Windows
CTest in its own 30-second-bounded process. This validates recovery in the
standalone adapter fixture; application Cargo compiler flags and native app
acceptance remain separate checks.

## Windows application build: 2026-10-08

An immutable archive of reviewed source `9fab4b5860762634767aacef2a487d7021f01497`
built the complete x64 MSVC application using `cargo build --release --features
ocio-runtime --locked --offline --jobs 2`. Cargo completed successfully in
**8m 22s**, and the lockfile stayed unchanged. The executable is **46,889,984
bytes**, with SHA-256
`af3fda5e7e4dc11b9fcf43dd8246ceefe9cf182f9415ef9774837204d910d592`.

The Windows-owned packet is
`C:\Users\rsmit\.codex\GyroflowBuildTools\OcioApplication9fab-20261008`.
A private stage reuses the installed test app's dependencies and adds the
matching OCIO and Qt ShaderTools DLLs. This establishes full feature-app
compilation and staging, not real-video/native acceptance, clean-machine DLL
closure, complete distribution notices or a public package. Those checks remain
open; the feature default and installed/public app are unchanged.

The pristine feature executable subsequently completed three private CLI exports
of the same DJI clip: neutral, LUT only, and LUT with all eight adjustments.
Each output contained **857 frames** at **1280×720**, **HEVC Main 10** with
`yuv420p10le`, and **60000/1001** average frame rate, and passed a complete
error-checked decode. Read-only NVIDIA encoder-session observations matched the
owned application PID and output dimensions, with **9 / 15 / 16 samples** for
the three respective cases. The runner completed with exit zero; exact output
identities are retained in the packet's `cli-export-result.json`.

These checks establish completed real CLI exports and observed hardware encoder
sessions. They do not establish numerical preview/export color agreement, native
GUI acceptance, CPU-stabilization fallback absence or whole-export GPU execution.
Later saved-file checks confirmed **H.265 / GPU 0 / 1280×720** for every matching
application-PID encoder-session row. Each output has **857 six-decimal timestamps**;
maximum frame-grid error is **0.333334 µs** and maximum spacing error is
**0.666667 µs**, within the retained decimal-rounding bounds for **60000/1001**.
No stream time-base field was saved, so these readings do not establish an exact
rational timestamp contract. All three probes report limited range (`tv`) and
BT.709 matrix, transfer and primaries. The earlier Windows OCIO export-fixture
log in `OcioE4ExceptionExport-20261008` reports **29 passed / 0 failed**.

The required loaded DLL subset matches the private stage for all three exports.
An **81-image** exact-set/current-hash check belongs to a separate hidden dependency
probe; it does not establish full-app closure. Independent parsing of the complete
quoted compiler commands for the OCIO bridge and generated Qt preview C++ found
exactly one `/EHsc` argument in each, no conflicting exception option and no
response-file argument. Their command hashes match the retained build records.
Compiler environment variables such as `CL` and `_CL_` were not captured; this
establishes the recorded argument lists, not environment-wide effective flags.
The actual logged settings path is
`AppData/Local/Ryan Smith/Gyroflow Plus/settings.json`. No before baseline was
captured for that namespace, so preservation remains unverified. The Windows-owned
saved-read receipt is `Windows-OCIO-final-read-handoff-20261008.json`, SHA-256
`d7493e21bd3d667cae4489ac51add2b6a198e61205b1e5a407bc820196641da2`.
Native preview/control acceptance, numerical color agreement, full-app DLL closure
and the original old/new decoded-output hold remain open.

The subsequent native pass has its own prospective baseline: the actual Plus
settings file was absent before launch at **2026-10-08T16:31:29.3140902Z**. The
full **2,165,305,347-byte** DJI flight, chosen DJI LUT and authored Mac project
were copied directly over the existing authenticated file share, then copied
locally on Windows and independently hash-verified. A separate Windows-derived
project adapts paths and clears the Mac-only `-allow_sw 0` encoder option; the
authored project and source media stay unchanged. This baseline does not
retroactively establish preservation during the earlier CLI tests.

After the laptop restart and a fresh supported desktop-helper session, the native
observer reported reopening the LUT and all eight saved values, then completing
one GUI export. The retained file is **67,820,243 bytes**, SHA-256
`2fb159b29cf0f22f4ac29e9b7256b59e6bc7513ef8f53a20968b916cb24f9ac5`.
Its probe reports **3840×2160 HEVC Main 10**, `yuv420p10le`, limited range and
BT.709 matrix, transfer and primaries. A full decode exited zero. All **242**
integer best-effort timestamps equal `ordinal × 1001` in a `1/60000` time base;
duration is **242242 ticks / 4.037367 seconds**. NVIDIA recorded **11** matching
H.265 / 3840×2160 rows for the owned app PID, ten with positive FPS. The native
observer reported a success dialog; the owned app and temporary awake process
were subsequently reported absent. This establishes a completed native export
and hardware encoder activity, not numerical native preview/export parity.

Two verification commands remain failed and their receipts are retained. The
output check expected 240 frames, matching the duration-based progress estimate,
but the file contains 242. Source review traces the inclusive-start test,
end-after-submission test and final decoder drain to pre-color commit `77b49409`.
Both retained Mac reference and candidate exports also have 240 estimated versus
242 decoded frames. This is agreement with inherited behavior, not acceptance of
an exact four-second cutoff or proof for other clip/decoder boundary alignments.
The separate preservation check failed because the private derived project's
byte hash changed after native saving. Its LUT, eight controls, trim and export
fields remain present, but the complete semantic delta has not been established.
The test created the previously absent Plus settings file, and `windowWidth`
changed between the saved-project and completed-export reads. That file was left
present; exact settings equality/restoration is not established. Recorded checks
found no mismatches in 579 stage files, 577 stable files, three original fixtures
or the old settings file. These are recorded-file checks, not exact directory-set
or full-runtime-closure checks. The native packet is
`C:\Users\rsmit\.codex\GyroflowBuildTools\Native9fab-20261008`.

## Windows retained-stage static audit: 2026-10-08

A later read-only audit checks the retained `9fab4b58` application stage using
the corrected audit module from clean, pushed source
`7b099bfd8d9e557e1890755f02c05b184fe5fc1f`. The module SHA-256 is
`66ab0afb1e123ec462e2285b7149e1edabbadde61bca7ee45384e60a8ac6f26c`.
The actual pinned `pefile` parser and native Windows version API inspect all
**117 x64 PE images**; every parsed/native FileVersion comparison agrees and
the audit reports **zero errors**. The executable's OCIO and ShaderTools imports
are present. This checks import metadata and bundled symbol resolution; it does
not load the application or verify symbols provided by Windows system DLLs.

The original eight-error report remains unchanged. Seven rejections concern
five exact Windows in-box library names, now separately classified without
accepting staged system copies or missing VC140 redistributables. The remaining
failure used `14.51.36260.0` as its declared runtime floor, inferred from the
compiler's version. Read-only provenance collection establishes instead:

| Selected build input | Observed version |
| --- | --- |
| VS toolset directory and default redistributable directory | `14.51.36231` |
| `cl.exe` FileVersion, matching the retained compiler hash | `19.51.36260.0` |
| Selected `crtversion.h` version macros | `14.51.36244.0` |
| Selected official non-debug x64 CRT DLL FileVersions | `14.51.36247.0` |

All six staged CRT DLLs match the corresponding selected Visual Studio
`Microsoft.VC145.CRT` redistributable **byte for byte**, as well as by native
version. The new invocation declares `14.51.36247.0` from that selected official
redistributable evidence. It retains the same full four-component comparison;
the failed report's floor is not edited or silently waived. This evidence applies
to the selected recorded build inputs, not arbitrary toolsets or dependencies.

The bounded audit child completes naturally with exit zero in **4.344 seconds**.
Before/after checks preserve all 581 stage files, 13 OCIO-prefix files, the Plus
settings file, selected redist provenance and 92 prior evidence files. The owned
collection, fetch and audit processes are terminal; the separate Easy Eject
preview process is unchanged. This duration is an audit time, not an export
benchmark.

The private packet is
`C:\Users\rsmit\Documents\Codex\2026-10-08\gyroflow-plus-windows-validation\outputs\corrected-audit-7b099bfd-20261008`.
Its complete `audit-full.json` is 6,345,106 bytes, SHA-256
`8ecdfc57ad26b721e59e59f47c6a08c1b7cafc5458ec91c5bcb60e561d8ed2cb`;
`audit-handback.md` has SHA-256
`a2318989247ce27d5d7d5a435aa636b215957b8afb5bee5d057322a4d59e27c5`.

No application, runtime or settings were replaced. The audited executable
remains the recorded `9fab4b58` build, not a new build of the audit source commit.
Color/encoder/stabilization runtime files are unchanged between those source
commits; two update URLs and a build-time shared-OCIO-prefix check changed.
Current-head compilation, numerical Windows preview/export agreement, native
loading on a clean computer, complete package notices/source provenance and
public distribution remain separate gates. The feature default remains unchanged.

## Complete restored-input diagnostic: 2026-10-08

An isolated LUT-only diagnostic captured all 242 restored P010 inputs from each
of the retained Homebrew and portable/static dependency families. Both use the
official OCIO feature path. Each capture contains **6,021,734,400 bytes**; all
recorded active Y/UV plane identities match the respective retained v3 export.
The complete comparator verified raw-file and plane hashes before and after
comparison, zero low P010 bits, fixed LUT/parameter identities and every active
10-bit sample. Of **2,007,244,800 Y** and **1,003,622,400 UV** codes, **7,120 Y**
and **5,494 UV** differ, with maximum **one code**. The unchanged one-code gate
passed; source, original media, LUT and settings snapshots stayed equal.

The conditional replay then submitted the first family's captured inputs to one
fixed Homebrew HEVC hardware-required encoder. It reproduced the first coded
picture, but **241 of 242** coded pictures differed from that family's historical
export. Configuration (`hvcC`), timestamps, durations and keyframe ordinals
matched. The replay therefore stopped with a failed receipt before the second
family; protected snapshots remained equal and output bounds passed. The direct
P010 replay does not independently certify the historical app upload branch.
It has not established the cause of the compressed-output differences. No repeat,
grade replay, new decoded comparison, tolerance change or release/default switch
was performed. The original exact old/new decoded-output hold remains open.
The private diagnostic is retained under
`_dev/ocio-runtime/portable-app-build/full-restored-input-capture-v1`.

A subsequent comparison of existing files found that the fresh native old-family
capture export matches **all 242 historical VCL payload lists**, hvcC, timing and
key positions. Whole-file hashes differ, with non-VCL differences only at ordinal
zero; no SEI interpretation was made. All consumed input identities matched
before and after this bounded parser-only check. This distinguishes the matching
application output from the failed standalone replay and narrows the unresolved
gap to the consumer/application execution or session contract. It does not
establish encoder nondeterminism or close the old/new decoded-output hold.

## Actual application downstream sufficiency: 2026-10-08

The next isolated diagnostic used the actual old application consumer, with
captured pixels injected only after its ordinary color processing. The natural
old restored pixels and retained frame properties were checked before each
injection; writability, metadata preservation, exact active-plane hashes and
explicit completion of all 242 frames were required. Color, stabilization,
encoder and queue logic remained otherwise unchanged. A failed first build
(a diagnostic `usize`/`u64` comparison) is retained separately; the repaired
private build completed successfully before either native case ran.

The old-pixel control reproduced **242/242 historical old VCL payload lists**,
codec configuration, timing and key positions. Only after that control passed,
the same binary consumed the captured new pixels and reproduced **242/242
historical new VCL payload lists**, with the same configuration/timing/key gates.
Both cases completed the hardware-required HEVC/P010 path, with all protected
source, settings, project, LUT and input snapshots preserved. Non-VCL differences
were confined to ordinal zero; no SEI interpretation was made. Native execution
took 68.58 s for the control and 55.13 s for the new-pixel case; these diagnostic
runs include validation and injection and are not performance benchmarks.

For this LUT-only clip, the captured new restored pixels alone are sufficient
to explain the historical new coded-picture family through the old application
consumer. Together with the full restored-input one-code result above, this
narrows the changed export to the small input-pixel differences rather than
requiring a different downstream application or encoder to reproduce it. It
does not establish general encoder determinism, exact old/new decoded equality,
native preview agreement, Windows parity or release readiness. The original
exact decoded-output hold remains open; no acceptance tolerance, default or
public release was changed.

The private packet is
`_dev/ocio-runtime/portable-app-build/application-restored-input-replay-v2`.
Terminal control receipt SHA-256:
`4e023fc332ce275c18b9f7521486e472685cdc9746c4193c9d1a24394f1b4f20`;
terminal new-pixel receipt SHA-256:
`bcfa7d55449f8583b15680349c50375864d00c2876aa804b25c8ff6615d9401a`.

## Native effect one-frame agreement: 2026-10-08

A private full application build from `479419e9` tested the existing OCIO
ShaderEffect on Qt 6.7.3 / Metal. The diagnostic driver initially waited on a
QML-added `loaded` property unavailable through the native MDKVideoItem
metaobject. A separate private revision uses the native video metadata to
position the declared frame. This repair changes only the diagnostic driver;
the application color processor, shader, stabilization and encoder remain
unchanged.

The metadata preflight settled at frame **2777**, timestamp **46329.616 ms**,
with the selected DJI O4 LUT and all eight controls matching their frozen
processor values. One bounded capture then read the actual native video layer
before and after Qt's offscreen grab of the existing effect. Both inputs were
byte-identical, the refresh probe returned false, and the synchronous bracket
recorded zero notifications. The output and input dimensions were **836×471**;
the observed image was RGBA8, with opaque alpha and no image color space.

The unchanged production OCIO CPU bridge evaluated the captured input once,
using the same LUT and controls. Row mapping, rounding and the fixed outer
one-pixel border were declared before capture. The comparison passed the
unchanged one-code gate: all **1,173,438 interior RGB components** differ by at
most **one code**, with zero larger differences. The full image has the same
one-code maximum; its **7,830 border components** match exactly. CPU output is
finite, with no clipped components in this case. Original media, LUT, retained
project fixture, settings and installed application binaries passed the retained
preservation checks.

This establishes one-frame agreement between the actual native layer input,
the existing effect's offscreen output and the official CPU processor. The
original visible-window numerical and exact old/new decoded-output holds
remain open, as do Windows runtime closure and public packaging gates. It
does not change the installed/default runtime or establish release readiness.

The private packet is
`_dev/ocio-runtime/portable-app-build/mdk-native-effect-capture-v6-native-readiness`.
Capture receipt SHA-256:
`2ebffefc727f24bdbc1b712a8a28b83516b15fb8b36dcd5e5df8ba75f17e0bb1`;
comparison statistics SHA-256:
`a46633a2527de0746b40a01b22d46f62ec056d3455e83b7b5047099679744efb`.

## Windows retained app evidence reconciliation: 2026-10-08

A later bounded, read-only collection inspects the original logs and receipts;
no app, export, build or GPU test is rerun. The final `e4db0995` Cargo log records
**29 tests passed**, zero failed or ignored, with the explicit `ocio-runtime`
feature. The retained `9fab4b58` complete application build exited zero after
8 minutes 22 seconds. Both recorded C++ compilation units contain `/EHsc`,
including the generated `rust_cpp/cpp_closures.cpp`; its retained source includes
the preview implementation. This closes the earlier missing final test-count
and full-app exception-flag observations for those source identities.

The dependency probe's raw `modules` field is an array of **81 path strings**,
not an array of objects with a `Path` property. Projecting that nonexistent
property explains the earlier null-path summary. Separate actual application
CLI-export records contain `Images` objects with real paths, hashes and lengths;
the retained validation reports matching staged bytes for the selected Qt,
ShaderTools, OCIO, FFmpeg and MDK dependencies in neutral, LUT and combined
exports. Some native DLL version-resource fields are genuinely absent; that is
separate from the probe's recorded runtime versions (Qt 6.7.3 and OCIO 2.4.2).
These retained observations do not establish a complete clean-machine loader
closure or a new current-head build.

The source/project qualifications remain explicit: the Windows test project
was a derived copy and was rewritten when saved; the whole pre-save semantic
identity is not established. The Plus settings file was originally absent,
then created by the test app. Recorded post-save/export settings differ only
in `windowWidth`, and the current settings still match the retained post-export
values. Original settings and source fixtures remain preserved. This is not
unchanged-existing-Plus-settings proof. The native export still has 242 decoded
frames against the initial 240-frame progress assumption; the earlier failed
checks remain retained.

The metadata child exits zero naturally in **13.703 seconds**, within its
60-second/16-MiB bounds. Its owned job has zero active processes afterward;
1,395 preservation entries and 943 separately protected Easy Eject pins match.
The dedicated Windows chat is terminal/idle and its resource slot was returned.
The evidence packet is `outputs/final-metadata-20261008T232812` in the dedicated
Windows validation workspace. `handback.json` SHA-256 is
`e7004f3cec16a2be189396d2497420e26b6d9eccf0ee7d0e30c725bd25df7536`;
`facts.json` is 891,439 bytes with SHA-256
`3bd2f39d15316b5cb091339e38dd043691bb4f9e25209e42efd42d918d97fda1`.
Current-head compilation, numerical native Windows MDK preview/export agreement
and public packaging remain open. Passing earlier source tests is not a
current-head application acceptance claim.

## Tagged SDR encoder-target consistency: 2026-10-08

A source review found that the encoder-target converter always selected
BT.709 coefficients. Explicitly tagged BT.601 or BT.2020 nonconstant-luminance
footage could therefore reach the color processor differently when exported
to RGB formats such as PNG/EXR instead of YUV video. The configuration now
uses FFmpeg's matching coefficients for those color-active RGB targets and
retains FFmpeg's full-range convention for YUVJ storage formats. Conversion
math remains in FFmpeg. Neutral exports and ordinary YUV converter setup
retain their existing policy; unknown/unsupported RGB matrix tags still use
the previous BT.709 fallback. Untagged YUV/RGB policy remains a separate item.

The regression tests import the actual production configuration helper and
then run real FFmpeg scaling and LUT processing. Independent YCbCr reference
values cover **144 tagged-SDR combinations**, including six source formats,
limited/full ranges and three RGB targets. Additional checks exercise reused
RGB contexts, unchanged neutral RGB bytes, unchanged unknown-tag behavior and
unchanged active-YUV converter configuration. The pre-fix mismatches were
retained; existing reference tolerances were not widened to accept the fix.

On arm64 macOS with FFmpeg 9.0.1, **35 default tests** and **43 OpenColorIO
2.4.2 feature tests** pass with zero failures or ignored tests. Both full
application feature configurations pass isolated, locked/offline `cargo check`
using Qt 6.7.3 and the pinned v41 lens database, without a private FFmpeg crate
overlay or lockfile change. This checks the Rust call sites and native
build-script compilation; it does not link/run a new app or prove native
PNG/EXR exports, Windows acceptance or hardware-export performance. The
installed/default runtime and release gates remain unchanged.

The retained root evidence is
`_dev/root-encoder-color-review-20261008/ACCEPTANCE.json`.

## Mac application RGB observation: 2026-10-09 UTC

The exact application source at `3788024f` links with `ocio-runtime`, Qt
6.7.3, OCIO 2.4.2 and Homebrew FFmpeg 9.0.1. This development configuration
needs the existing x264/x265 static archive search paths explicitly supplied
through `EXTRA_LINK_PATHS`; the earlier failed link is retained. No canonical
source or dependency lock was changed to obtain that link.

Running the debug application exposed a preexisting pinned Qt-binding
signal-offset pattern that forms a reference through null. A standalone
one-signal reproducer aborts without any video or color libraries. A private
candidate replacing that calculation with Rust's standard field-offset macro
passes the same connect/deliver/disconnect test. This is a **candidate dependency
fix**, not an integrated or Windows-accepted change. The manual reproducer and
proposed patch are in `tests/qobject-signal-offset/`.

For the following observation, the app has that candidate binding override
and a private settings-directory seam. Its production rendering and color
sources match `3788024f` exactly. The synthetic 64×64, three-frame lossless
MP4 has verified SMPTE170M/limited-range tags, a one-second stream duration,
and decoded YUV bytes identical to the supplied fixture. A two-point LUT
copies input red to all three output channels; controls are zero. CPU
stabilization uses **bilinear** interpolation. No real-camera or native-preview
compatibility is inferred from this fixture.

| Application export | Expected interior value | Observed value | Maximum error | Preselected tolerance |
| --- | --- | --- | --- | --- |
| Neutral PNG, red | 0.71398843, legacy BT.709 | 0.71372549 | 0.00026294 | 2/255 |
| LUT PNG, all RGB | 0.67773129, tagged BT.601 | 0.67843137 | 0.00070009 | 2/255 |
| LUT EXR, all RGB | 0.67773129, tagged BT.601 | 0.67512017 | 0.00261112 | 3/255 |

All nine images decode and satisfy the independent YCbCr reference over the
48×48 interior. All 15 bounded commands exit zero and their owned groups are
terminal. Existing authored Plus settings hashes remain exact. This supplies
actual app-path evidence for the tagged RGB fix under the stated candidate
configuration; it does not replace direct acceptance of an unchanged-dependency
release build.

The debug Lanczos4 run separately aborts at the existing CPU undistortion
edge-index calculation with integer overflow. At that observation the failure was retained and
unfixed. Choosing bilinear for this color observation does not establish
Lanczos4 acceptance. A prior MKV fixture also lacked a usable stream duration
and was rejected before rendering; its bounded failed run remains retained.
The dynamic Homebrew FFmpeg/MDK combination emits duplicate Objective-C class
warnings, whose causal effect is unproved.

Evidence: `_dev/root-current-rgb-app-20261009/ACCEPTANCE.json` and
`exports-v4-bilinear/RESULT.json`. The observed candidate binary SHA-256 is
`b36f5cde9033298f82adcf2e460f681fa0baa0182cd1eb0e8d1cf9487112f8e2`.
No installed app, default feature, public package or release gate changed.
Current Windows acceptance remains open and is paused at Ryan's request.


### Deploy-profile follow-through with the pinned dependency

A fresh Mac application build at `d23695a9` uses the normal **deploy** profile
(`inherits = "release"`, LTO, one codegen unit), `ocio-runtime`, and the original
pinned qmetaobject dependency. It does **not** use the candidate binding patch.
The canonical and private root lockfiles are byte-identical and unchanged.
All 453 compared source/resource/configuration files match that checkout
except `src/core/settings.rs`, whose private seam changes only the settings
location. The OCIO processor and GPU preview source files also match the earlier
Mac acceptance source at `479419e9`.

The build exits zero in **286.195 seconds**, with its owned process group terminal.
Using the same verified, three-frame tagged MP4 and red-to-gray LUT, the app
completes neutral PNG, LUT PNG and LUT EXR exports. The test omits the interpolation
parameter, so the ordinary mapping selects **Lanczos4**. All nine decoded images
match the reference values and preselected tolerances in the table above; their
observed interior values and maximum errors are unchanged. All 15 bounded fixture,
app and decode commands exit zero with terminal owned groups. Existing authored
Plus settings hashes remain exact.

This adds actual optimized application-path evidence without a dependency
override or a bilinear substitution. It is still a synthetic 64×64 interior-color
observation, not real-camera motion, native-preview, hardware-export or portable
package acceptance. The sequence logs retain an encoder PTS warning and an
unsuccessful attempt to update the sequence pattern's file times; all individual
images were created and decoded. No timing or file-time guarantee is inferred.

An optimized run that finishes does not make the Qt null-reference offset pattern
valid, and it does not fix the separate debug Lanczos integer overflow. At that run, both
findings were unfixed; the earlier failed runs remain retained. No installed app, default
feature or public release changed; current Windows acceptance remains held at
Ryan's request.

Evidence: `_dev/root-current-rgb-app-20261009/deploy-pinned-binding-v5/ACCEPTANCE.json`,
`SOURCE-VERIFICATION.json`, `RESULT.json`, and
`exports-v5-deploy-default/RESULT.json`. The deploy binary SHA-256 is
`918148aca654990cf352cfc5d37779dfef02c4e08450d884fe9b37d7e07e82df`.


### Debug edge-index correction and dependency review follow-through

The CPU interpolation loop now sums its signed footprint base and signed
pixel offset **before** converting the guarded, in-bounds pixel index to
`usize`. Previously, a footprint beginning left of the image cast its negative
base to an unsigned integer before adding the offset, which could overflow in
debug builds even when the final pixel was in bounds. The correction changes
only integer addressing inside the existing bounds checks; coordinates,
interpolation coefficients and color processing are unchanged.

Before adopting that exact source change, a private debug app at `a8f249fc`
with the index correction, the already described binding candidate and private
settings location completed all three default-Lanczos export cases. All nine
**full decoded images**, including their edges, are byte-identical to the
retained deploy-profile reference. All 15 bounded commands exit zero with
terminal owned groups, and authored Plus settings hashes remain exact. The
adopted CPU source SHA-256 is
`ec3d76ff45b54c5031ca33bb2fc4a232845079c395cc8410cb39f7daa1cab906`.
This resolves the observed debug indexing failure in the tested synthetic cases;
it does not establish every stabilization configuration or real-camera motion.

The separate binding candidate also passes three exact pinned upstream test
functions: typed Rust signals, C++ signals, and lifetime/generic derive
compilation. The original dependency passes the C++ test but aborts in the
Rust typed-signal test. The generic compilation test does not instantiate its
objects. At that observation the dependency correction was still **unintegrated**, and
the canonical app's dependency lock was unchanged. The CPU index correction
alone did not make a canonical debug app start successfully.

Evidence is in `private-lanczos-index-v6/`, `exports-v6-debug-index/`, and
`binding-upstream-signals-v3/` under
`_dev/root-current-rgb-app-20261009/`. The debug candidate app SHA-256 is
`da031892cb7d7d74c56c8d882e8af4aea296b3d595754d1b4d91f654dcd5e2d5`.
The exact upstream test functions and their license header are retained in
`tests/qobject-signal-offset/tests/upstream_signals.rs` for manual reproduction.
Installed apps, the engine default and public releases are unchanged. Windows and Claude work remain held
until renewed direct human go-ahead.


### Pinned Qt derive source integration

The root application now retains `qmetaobject_impl` under
`vendor/qmetaobject-rs/`, from the exact upstream revision
`ff1e23dcdd722a0c335bbd51f7dcfdb722384db2`. Of the eight retained upstream files,
only `qmetaobject_impl/src/qobject_impl.rs` changes: the tested standard
`std::mem::offset_of!` expression replaces the null-reference calculation.
The original README, MIT license and source headers remain intact. The pin
record contains both original and retained file hashes.

The root Cargo patch replaces only this proc-macro's source identity.
`qmetaobject`, `qttypes`, all other versions, sources and package dependencies
remain unchanged. The standalone manual diagnostic intentionally still uses
the unpatched Git baseline, independently of the root app's patch.

An isolated debug application built from `226eeefd` plus these source changes
exits zero in **22.886 seconds**. Its manifest, lock and retained dependency
match the root source; only the settings location is a test seam. There is no
private binding override. All three default-Lanczos OCIO export cases pass;
all nine full decoded images remain byte-identical to the earlier deploy
reference, all 15 bounded commands exit zero with terminal owned groups, and
the complete protected settings/log tree remains unchanged.

The ordinary default build also compiles and completes a neutral PNG export.
Its three decoded images are byte-identical to the reference, all seven bounded
commands exit zero with terminal owned groups, and the protected tree is exact.
That run adds startup/neutral-path evidence for the default build, not new
acceptance of the legacy color algorithms. The 46 packaging/build-receipt tests
pass, including license/pin/patch copying and refusal to overwrite an existing
notice packet. Both platform stages copy these notices; the committed source
archive retains the full crate. Windows execution remains unrun for this source.

An earlier default-build runner omitted `--manifest-path`, so Cargo searched
upward and built from the canonical checkout. That failed isolation check
replaced `gyroflow.log`; `settings.json` and other protected files were
unchanged. The exact prior log preimage was recovered from retained evidence,
verified against its pre-test SHA-256, and restored with its original inode and
mtime. The full directory hash tree then matched the before snapshot. That
failed run and recovery remain recorded; the corrected run explicitly names
the isolated manifest and checks the logged settings path.

Evidence: `vendor-integration-v7/`, `exports-v7-root-vendor/`,
`exports-v7-default-neutral/RECOVERY.json`, and
`exports-v7-default-neutral-v2/` under
`_dev/root-current-rgb-app-20261009/`. The retained OCIO debug binary SHA-256 is
`15c710116452a4d4b89e4519047d4cb76238c28a2103725e4c1b7b378f5a2dcd`;
the corrected isolated default binary SHA-256 is
`eafd1cf3026bc79f9cbe7a66c15125a55976ae4db72e5c3f75f28140445a7413`.
This integrates the targeted source fix; installed apps, the engine default,
public releases and platform/package acceptance gates are unchanged. Windows
and Claude work remain held until renewed direct human go-ahead.


### Public FFmpeg binding build correction

The root now retains published `ffmpeg-sys-next` 9.0.0, pinned by package SHA-256
`9b939bf79dd5949412a4b81cfe21a07f48ea21b47fcbb5f57816c8c2de5ae30b` and upstream
revision `80b7dd8327c3539159f37d8ca5423c75d6cd2e57`. Only two unconditional macOS
static framework requests are removed: QTKit and VideoDecodeAcceleration. The
retained source matches the published package plus the recorded patch byte for
byte; it differs from the original private overlay only in explanatory comments.
All other root lock package records are unchanged. Notices and corresponding
binding source are now part of the tracked source and staging paths.

A real arm64 Rust consumer links the unchanged accepted official-source static
FFmpeg prefix and executes with both the registry and retained binding crate.
Both report 228 codecs and identical complete filter names; VideoToolbox,
x264/x265, PNG/EXR, scale, eq and buffer registrations are checked directly.
The retained binding emits no obsolete framework requests, its linked executable
imports neither framework, dynamic FFmpeg nor Homebrew libraries, and the 482
prefix files, vendor bytes and canonical lock stay unchanged. All eight bounded
build/run/inspection commands exit zero with terminal owned groups. This is a
binding/link consumer check; it does not execute hardware-encoded frames, an app
preview, stabilization or color export.

The current SDK still contains legacy stubs: the unpatched consumer links zero
with an incompatible-arm64 QTKit warning. An earlier probe expected a hard link
failure and therefore failed its assertion; that result is retained. Another
probe assumed the accepted prefix had `lut3d`; it does not, consistently with
its inherited selected-filter configuration. A runner retry then rejected a
duplicate output name before the corrected run. These failed runs are preserved,
not counted as acceptance. The OCIO path does not use the legacy `lut3d` filter;
a static default-engine LUT build would need separate filter capability work.

The 54 packaging/build-receipt tests pass, including the real published package
identity, byte comparison, modified/extra-file refusal, unsafe archive member
refusal, exact notice copying, existing-packet preservation and obsolete Mac
framework load rejection. No installed app, engine default or public release
changes. Current full-app and Windows acceptance remain separate gates.

Evidence: `_dev/root-ffmpeg-sys-integration-20261009/`, including
`STATIC-PROBE-ACCEPTANCE.json`, `static-probe-v4/`,
`PRIVATE-OVERLAY-COMPARISON.json`, `LOCK-DELTA.json`,
`CLAUDE-MANIFEST-VERIFICATION.json` and `package-tests-final.log`.
The scoped consumer executable SHA-256 is
`58193ee24686cebb933588a609297e9d964bfd188fbae1918bc5afb859664096`.
Windows and Claude work remain held until renewed direct human go-ahead.


### Current app with public binding dependencies and static FFmpeg

A fresh private application built from public source
`80dad105a5312e24a151985cf0ec66fc140eadb2` completes the normal `deploy` profile
with `ocio-runtime,ffmpeg-next/static`, a locked/offline arm64 build, two jobs,
and no private dependency override. Build time is **291.524 seconds**, exit zero,
with the owned process group terminal. All **670 source files** were compared
to the committed archive: only the required private settings-location seam
changes. Manifest, lock, both retained binding crates and all runtime/color code
match public source. The private and canonical lock files remain exact.

The executable links official OCIO 2.4.2, the retained Qt/MDK runtime and static
FFmpeg/OpenCV. Its actual binding output requests neither obsolete framework;
its direct imports contain neither framework, dynamic FFmpeg/OpenCV nor Homebrew
paths. Absolute development runtime paths remain; it is not a portable package.

The current app passes the unchanged three RGB export cases with default
Lanczos: neutral PNG, LUT PNG and LUT EXR. All **nine full decoded frames** are
byte-identical to the earlier deploy reference, including edges. The original
2/255 PNG and 3/255 EXR matrix tolerances remain unchanged. All **15 bounded
commands** exit zero with terminal owned groups, and the complete protected
settings/log tree is unchanged. This is actual startup and fixture-export proof
for the current static OCIO app; it does not establish native preview parity,
real-camera stabilization, hardware-frame export, Windows behavior, package
relocation, older-OS execution or public-release acceptance.

Evidence: `app-build-v1/` and `exports-current-static-v1/` under
`_dev/root-ffmpeg-sys-integration-20261009/`, including the input/result,
670-file source comparison, linkage verification and protected-tree receipts.
The executable SHA-256 is
`ab1c0314b77fcdcff6cf2ee3d004da08106c9ceebf4cf1ea01f2434eba4da479`
(**65,212,160 bytes**). No installed app, engine-default or release change;
Windows and Claude remain held until renewed direct human go-ahead.


### Current real-drone hardware export checks and reference hold

On 2026-10-09 UTC the same private `80dad105` executable completed three
saved-stabilization DJI O4 checks: neutral, LUT only, and LUT plus all eight
controls. Each uses the retained 45–49 second range, 3840×2160 HEVC 10-bit,
`-allow_sw 0`, and one render job. Each output decodes to 242 frames with
limited-range BT.709 metadata and 60000/1001 fps. The render logs initialize
OpenCL stabilization; these checks do not establish a Metal preview path.
Copied source media, original saved project, selected LUT and the complete
user settings/log tree retain their original bytes and file identities.

These exports pass completion and format checks, **not reference parity**.
Against the older isolated OCIO-family application outputs, timestamps and
frame sizes match, but 241 of 242 decoded frame hashes differ in every case.
Full-sequence PSNR averages are 44.971443 dB neutral, 43.460890 dB LUT, and
40.083949 dB grade. No acceptance tolerance has been relaxed. A single repeat
with the current executable produces all 242 decoded frames and timestamps
exactly matching its first neutral run, despite a different container hash.
This control does not establish universal encoder determinism.

The current private development runtime is a material comparison difference:
its MDK runtime loads Homebrew FFmpeg shared libraries even though the main
executable's direct imports contain no Homebrew or dynamic FFmpeg dependency.
A system-only `PATH` control still observes those loaded libraries. The older
packaged reference's retained library samples contain no Homebrew images.
Thus direct-import inspection alone does not establish runtime closure, and
these observations do not yet attribute the image differences to color code,
stabilization, settings, or library resolution. The comparison remains open.
Single-run durations are not a matched performance benchmark.

The system-PATH control's initial postprocessing failed because library-load
diagnostics also contaminated the FFprobe JSON stream. Its original failure
receipt is retained; export completion must not be reported as a whole-run
pass. Decode-only follow-up uses a clean diagnostic environment.

Evidence under `_dev/root-ffmpeg-sys-integration-20261009/`:
`hardware-current-v1/`, `hardware-current-compare-v1/`,
`hardware-repeat-neutral-v1/`, and `hardware-system-path-neutral-v1/`.
The prior real-output, native preview, Windows, relocation, older-OS and
public-release gates remain open. No installed application, default engine,
user settings or published binary changed.

Ryan has renewed Windows and Claude work. The Windows laptop
`LAPTOP-OQ24VVBH` is the only Windows machine in scope; no gaming desktop was
used. Easy Eject's existing generated-fixture test has the next laptop slot,
followed by separately reviewed current-source Gyroflow CPU checks. Historical
pause text above records earlier state and is superseded by this go-ahead.


### Neutral export discrimination controls

Two further bounded neutral checks narrow the current-versus-historical
comparison without changing any acceptance threshold. Copying the user's
saved preferences byte-for-byte into the private settings directory produces
all 242 decoded frames and timestamps exactly matching the first current run.
Thus the empty-versus-saved preferences difference does not explain this case.

A separate private copy of the older runtime bundle uses the current
`80dad105` executable. Only its copied Mach-O development rpaths and local
ad-hoc signature change; source code, the original bundle, dependency prefixes
and installed app are untouched. Its hardware-required export completes, with
all eighteen observed non-Apple images inside that private bundle and no
Homebrew images. This run also produces all 242 decoded frames and timestamps
exactly matching the current development-runtime output. Removing those
external runtime loads therefore does not explain the neutral reference
difference in this control. Neither result establishes general encoder
repeatability or old/new decoded parity.

The four current neutral sequences have the same canonical decoded-row SHA-256
`18bf2f3bcae7e5bf17e6ae3f704d0b26e1c46a119b4665e6602a53d8cd17a4bb`;
each still differs from the historical reference in 241 frames. The complete
original media/project/LUT/settings-log and runtime-template identities remain
unchanged. Every owned command is terminal. Evidence under the same root packet:
`hardware-saved-preferences-neutral-v1/`, `hardware-matched-runtime-neutral-v1/`
and `NEUTRAL-DISCRIMINATION.json`. The runtime-copy test is an isolated
comparison artifact, not a new portable-package or native-preview acceptance.


### Human visual comparison of current neutral export

Ryan compared the hash-verified older-reference and current neutral exports
from Desktop copies in QuickTime and reported that they look exactly the same
as judged by his professional photography experience. This accepts the visual
comparison of that four-second stabilized segment. The earlier border flicker
was observed in the Codex preview; its cause was not independently confirmed.
The recorded numerical differences remain diagnostic evidence and are not
proof of a visible defect. This human check does not replace current native
preview/processor agreement, Windows tests, other-camera checks or portable
package validation. Retained report: `HUMAN-VISUAL-CHECK.json` in the root packet.

### Graded visual acceptance and queued color repair

Ryan also compared the older and current four-second exports with the selected
DJI LUT and all eight controls. He reported no visible difference and could see
matching shadow detail in the trees. Both test grades looked overexposed;
positive exposure, brightness and highlights were intentional stress settings,
not a recommended grade. This accepts that segment's visual comparison only.
Additional human testing is not a continuation gate.

A requested darker pair uses the same stabilization and LUT, exposure -0.75
and neutral other controls. Both hardware-required 4K HEVC ten-bit exports
completed with 242 frames. Its human comparison is not confirmed. The legacy
CLI replaced the application's diagnostic `gyroflow.log`; authored settings,
media, LUT, projects and binaries remained unchanged. The failed broad
preservation assertion is retained rather than reported as a whole-run pass.
Reports: `HUMAN-GRADED-VISUAL-CHECK.json` and
`human-shadow-pair-v1/RESULT.json` in the root packet.

Review found that saved project-backed queue entries held only a project URL,
so a later save could replace earlier jobs' LUT and adjustments after restart.
They now also store a color-only snapshot, with explicit neutral values and
an Apple LUT bookmark where available. Restore overlays those nine fields
before constructing the job's render options. Older queue records and other
output fields retain their existing behavior. A missing/non-object project
output still follows the old queue behavior; the queue Edit UI continues to
load the project's last-saved settings. Neither is claimed fixed here.

Root verified Claude's versioned candidate, then ran the actual production
helper tests on arm64 Mac: 42 default and 50 OCIO tests pass with no failures,
ignored or filtered tests. Both actual app feature configurations pass the
deploy-profile Rust/C++ compile check, including Apple bookmark calls. Test
locks and production source hashes remain unchanged through execution.
Evidence: `_dev/root-queue-color-review-20261009/`. This is not a native app
restart, Windows or portable-release acceptance.

### Clean Mac export and matched-runtime control

The clean committed `9ea94fb1` Mac deploy build has no private settings or
dependency override. Its hardware-required four-second DJI O4 export with the
LUT and all eight stress controls completes in 9.932 seconds: 3840×2160 HEVC
10-bit, limited-range BT.709, 60000/1001 fps, 242 decoded frames. A read-only
home sandbox preserves the complete application settings/log tree and source
media, project, LUT and executable bytes. Repeating this clean build produces
identical decoded pixels and timestamps for every frame.

A control using the retained private `80dad105` executable in the same closed
runtime, with saved settings and lens data copied byte-for-byte from the current
inputs, also matches all 242 decoded frames and timestamps exactly. That private
binary requires its test settings-path override; an initial attempt without it
panicked before export and is retained as a failed attempt. The corrected control
is not a clean public build of `80dad105`.

This establishes cross-version agreement for the tested graded segment under
comparable runtime and preference inputs. The earlier differently configured
reference still has its recorded numerical differences; this result does not
attribute those differences to a particular library or establish parity for all
clips. Ryan reports matching tree shadow detail, and further human visual testing
is not a continuation gate.

The current packaging auditor separately passes the prepared Mac bundle's
required-library and contained-path checks. Missing optional weak loads and absent
contained search directories are recorded as diagnostics; present weak libraries
still undergo architecture, minimum-OS and transitive dependency checks. This is a
technical audit of a prepared stage, not a completed signed package or public
release. Current-source native preview, Windows execution, complete redistribution
inputs and final packaging remain separate acceptance checks.

Evidence: `_dev/root-relocatable-mac-release-20261009/clean-graded-export/`,
`clean-graded-repeat/`, `matched80-graded-control-v2/` and
`package-audit/MAC-AUDIT-V10C-ROOT.json` under the same packet.

The later clean source `5a400b6b` completes the actual Mac deploy build in
291.814 seconds and the actual package helper in 7.067 seconds. Its completed
private stage includes the exact committed source archive, pinned lens data,
retained dependency notices, zero required-library/path audit errors, and an
ad-hoc signature verified with `codesign --verify --deep --strict`. The signed
stage passes native CLI startup and the same hardware-required graded export;
all 242 decoded frames and timestamps match the accepted clean `9ea94fb1`
reference exactly. Original user data and media remain byte-identical.

This closes the technical staging and current-source export checks for that
Mac candidate. Complete dependency redistribution inputs, current native GUI
preview, Windows execution, older-OS execution, and public release acceptance
remain open. Evidence: `_dev/root-release-mac-5a400b6b-20261009/`.

A subsequent packaging-only repair preserves the audit report when resolving
an optional weak dependency raises `RuntimeError` or `OSError`, including
Python 3.11/3.12 symlink loops. A regression reproduces both uncaught failures
against the previous production auditor and passes after the correction.
The packaging suite runs 63 tests: 62 pass and one platform test is skipped.
The already signed candidate retains its exact `5a400b6b` source identity;
the diagnostic repair changes no application or color-processing source.

The same signed `5a400b6b` candidate also passes a bounded native GUI visual
smoke check using the production `--open` path and Metal on Apple M4 Max.
The saved DJI O4 LUT and all eight controls load correctly. At frame 2793
(approximately 46 seconds, within the saved 45–49 second trim), toggling
preview color visibly switches between flat log and graded output while
retaining the settings. Double-clicking Exposure resets it from 0.37 to 0.00
without changing the other controls. The owned process group closes at its
90-second observation bound; all protected application data and original
media/project/LUT bytes remain identical, and the installed app is untouched.

The initial zero-second viewport showed a blank/tiny-triangle image before
seeking into the saved trim; this observation is retained without attributing
a cause. This smoke check does not replace numerical GPU/CPU parity or Windows
acceptance. Evidence: `native-gui-smoke/RESULT.json`, `OBSERVATION.json` and
`native.log` within the same candidate packet.


### Local crash diagnostics and build opt-out

The inherited startup routine scanned the current working directory for `.dmp`
files and automatically sent readable dumps to the upstream Gyroflow service.
Gyroflow+ removes that upload loop. It no longer reads or deletes working-directory
dumps at startup; the existing local crash-dump handler remains enabled by default.

Breakpad is now an optional, default-on `crash-reporting` Cargo feature. An explicit
`--no-default-features --features opencv,ocio-runtime` build omits it. The Mac build
receipt helper accepts `--no-default-features` and records whether Cargo defaults
were enabled. Actual locked/offline Mac arm64 and Windows x64 dependency graphs
show that this opt-out removes only `breakpad-sys`; `Cargo.lock` is unchanged.
The build-helper suite passes 14 tests, including opt-out command and receipt
checks. These graph/helper checks are not a new application compile or runtime
acceptance. Existing signed candidates retain their original source identities.

This supported opt-out avoids vendoring or rewriting an inherited crash reporter.
It does not establish a legal conclusion about the default-enabled reporter's
compiled units or replace full redistribution review. The color processor,
stabilization and encoding algorithms are unchanged by this correction.

### Clean crash-reporter opt-out candidate

The clean `0b5ba007bfad303f88c143615a9d2baf384de4cb` source now also has an
actual Mac arm64 deploy build using `--no-default-features` and explicit
`opencv,ocio-runtime,ffmpeg-next/static` features. The production build-receipt
helper completed in 293.57 seconds with two compiler jobs. Its receipt records
defaults disabled; the normal dependency graph excludes `breakpad-sys`, and an
actual `nm` check found no named Breakpad symbols in the resulting executable.

The production packaging helper completed in 7.19 seconds. The runtime audit
reported no external dependencies or errors, and the ad-hoc signature passed
`codesign --verify --deep --strict`. The signed executable SHA-256 is
`babfd6a79ab69cd11682fb970db12ebe0b1d5b488b00d41b6c32bef231353585`.

That exact staged executable passed native CLI startup and a saved stabilization
export with the DJI O4 LUT and all eight nonzero controls. Hardware VideoToolbox
encoding was required (`allow_sw=0`). The export completed in 9.89 seconds and
produced 242 frames of 3840x2160 HEVC, 10-bit 4:2:0, BT.709 limited range at
60000/1001 fps. All decoded frames and timestamps match the accepted clean
`9ea94fb1` reference exactly. These timings describe correctness runs, not a new
performance benchmark. Original media, LUT, projects and complete application
settings remain unchanged; the installed application was not replaced.

Evidence: `_dev/root-release-mac-0b5ba007-20261009/`, including the build receipt,
`NO-BREAKPAD.json`, `package-audit/RESULT.json`, and
`clean-graded-export/RESULT.json`. This is technical candidate acceptance on the
tested Mac, separate from the earlier `5a400b6b` GUI smoke. Complete dependency
notices/source distribution, current Windows native behavior, signing and
notarization for distribution, and clean-machine acceptance remain open. No
public release or default color-runtime switch is implied.

### Windows CPU component check

On the Windows laptop, exact `9ea94fb15575219133a5f2777b5a3c6f6687ef81`
source passed 42 default tests and 50 `ocio-runtime` tests. Both Cargo commands
and the worker exited successfully. The supervisor subsequently failed its
three-second natural job-drain check. The failure remains recorded; cleanup
confirmed zero active owned processes, all 39,970 protected files matched, and
the final process census passed. The retained evidence does not identify the
process that delayed natural drain. This accepts the test results as component
evidence, not the whole supervisor run or current Windows app/package behavior.

### Current Windows native preview component check

On 2026-10-09, the exact seven-source fixture from `0b5ba007` configured,
built and passed all three native CTest cases on the Windows laptop:
`native-float32-preview`, `software-renderer-rejection` and
`shader-exception-lock-recovery`. The actual backend was D3D11 on the NVIDIA
GeForce RTX 5070 Ti Laptop GPU. All 82 GPU/CPU comparisons passed; the maximum
absolute error was `2.384185791015625e-7`, below the `1e-5` gate. Resource/cache
assertions passed, the fetched source stayed unchanged, and the observer
captured the expected OCIO/Qt runtime module paths inside the owned test job.
The single CTest invocation took 12.31 seconds; this is a correctness fixture,
not a video playback or export throughput measurement.

The supervisor still failed its original three-second natural-drain gate.
This time its diagnostic identified two remaining processes in the exact owned
job: MSVC `vctip.exe` and `mspdbsrv.exe`. Cleanup terminated that job and confirmed
zero active owned processes. All 23,092 protected files matched afterward and
the final process census passed. The whole supervisor result remains failed;
the native component results are accepted separately. No tests were repeated
to replace the failed wrapper result, and this does not establish current
full-app, installer or package acceptance.

Evidence: `_dev/root-windows-native-0b-review-20261009/`, including the reviewed
plan (`6b94db30`), wrapper manifest (`7a9d7f5d`) and retained remote terminal
record. The laptop worker retains the raw CTest output, pixels and source pins.

### Current Windows application preflight

Source review of the locked dependencies identifies two requirements for the
next full-app check. `qml-video-rs` at `855130d4f423321e60c4bb95b913dc1e22c1eb88`
uses a supplied `MDK_SDK` only when its required `lib/x64/mdk.lib` exists. With a
fresh build output and no valid supplied SDK, its build script downloads and
extracts MDK directly; Cargo's `--offline` does not prevent that request. The
candidate build therefore needs an explicitly verified existing SDK prefix,
headers, import library and runtime DLLs before Cargo starts. The Windows app
candidate should use `--no-default-features --features opencv,ocio-runtime`,
consistent with the Mac candidate's crash-reporter opt-out. The three-case
standalone native preview fixture does not use this dependency or Cargo.

`app_dirs2` at `1137ee05d745c2d5fa3fd01aecb6e1300d6fc280` obtains Windows user
data through `SHGetKnownFolderPath`; overriding `APPDATA` or `LOCALAPPDATA` does
not isolate the application's settings. Application startup also opens its
normal `gyroflow.log` with `File::create` before CLI argument handling, including
`--help`. A future smoke runner must protect the actual settings/log directory
and verify preservation. Environment overrides alone are insufficient. This
review does not change the production data-directory contract or establish a
tested Windows file-preservation guard.

An opt-in `GYROFLOW_PLUS_DATA_DIR` override now selects an explicit profile
directory before the platform's normal user-data lookup. It must be a nonempty
absolute path; an invalid path or directory-creation failure stops startup
instead of falling back to the saved user profile. The directory is resolved
once per process. With the variable unset, the existing platform lookup is
unchanged. Settings, `gyroflow.log` and the user lens-profile directory share
this selected core data directory. The override does not redirect output media
or promise a filesystem sandbox for dependencies and platform caches.

App validation should set this variable to a fresh owned directory and copy
only the intended test settings and lens inputs into it. Avoid changing the
user's normal profile to create a test fixture. The standard-library resolver
tests cover path rejection, real directory creation, existing settings/file
preservation and non-UTF-8 paths without lossy substitution. Missing parent
directories are created, so check the absolute path before setting the variable.
The selected profile needs write permission for logs and saved settings; this
option does not add a separate permission probe or change the existing logger's
terminal fallback when opening a log fails. Validate copied settings as JSON
and retain the original outside the test profile. A normal GUI save can add
`exeLocation` and reformat settings, so compare the intended parsed keys when
testing a session that saves preferences.

### Packaged Mac profile and export check

Exact source `ab680a27d75d1f109e92935b360c33e2d421758b` completed a clean,
locked/offline Mac arm64 build in 276.05 seconds with
`--no-default-features --features opencv,ocio-runtime,ffmpeg-next/static`.
The resulting technical package passed its required-library audit with no
external required dependencies or audit errors. All 9,151 dependency notice
files matched the supplied notice tree byte for byte, and the source archive
matched `git archive` for this exact commit. Existing Rust notice receipts retain
their original source identity; their reuse is based on unchanged Cargo input
hashes, selected features and target.

The packaged executable then passed native CLI startup with
`GYROFLOW_PLUS_DATA_DIR` pointing to a separate directory containing a copy of
the test settings. Startup created the selected log and lens directory, and
the export log confirmed the selected settings path. The saved DJI O4 project,
including its LUT, eight color controls and stabilization settings, exported
3840×2160 HEVC 10-bit video with `-allow_sw 0` in 9.41 seconds. All 242 decoded
frames and timestamps matched the accepted `0b5ba007` export exactly. The
normal user profile, input media, LUT and reference files remained unchanged.

The first test script stopped after the successful export because it expected
a preferred-lens-folder log line for an empty folder. The loader intentionally
logs that path only for a nonempty folder. That failed test receipt was retained;
analysis continued on the existing export without rerendering it. This result
is packaged CLI/profile/export evidence, not a new GUI, Windows, performance
matrix, notarization or public-release claim. The independent source review
found no blocking override or default-fallback defect.

### Windows dependency capture

The bounded read-only capture completed in 12.06 seconds, with all 1,210
protected/provider file pins unchanged and its owned job closed with zero active
processes. The recorded lockfile hash matches the current application source.
Its 155 missing registry sources describe the whole lockfile, including unused
and other-platform packages: none appear in the accepted 331-crate selected
Windows graph. This establishes focused presence, not complete Git payload
integrity or successful offline Cargo resolution. The absent MDK `ffmpeg-5.dll`
is an optional copy in the locked `qml-video-rs` build script; its absence does
not require downloading an unverified replacement. Windows runtime dependency
closure still needs the staged PE audit.

The retained full `9fab4b58` Windows application build took 8 minutes 22 seconds.
Its successor needs a separately reviewed build deadline and resource slot;
the 300-second standalone preview limit is not a measured full-app build budget.
The native component check above passed; current full-app execution remains
pending. Source-review evidence is retained
in `_dev/root-windows-native-0b-review-20261009/WINDOWS-APP-INPUT-REVIEW.json`.

### Independent crash-reporting source review

The independent successor review of `0b5ba007` found no blocking source defect.
The owner verified all three delivered manifest members and six pinned source
hashes, and independently confirmed that the retained desktop handler body is
unchanged from `de8bd219`. This accepts source review; it adds no platform compile
or runtime claim beyond the Mac evidence above.

The removed startup dump scan/upload is distinct from unrelated directory reads
and network features. Three legitimate core directory reads remain, as does the
automatic lens-checksum usage request. With default features on mobile, startup
still calls `current_dir()` before the desktop-only handler block is removed by
conditional compilation. An optional patch moving that call into the desktop
block is deferred because mobile compilation was not exercised and it is outside
this desktop release scope. Default-build Breakpad linkage and redistribution
remain separate from acceptance of the opted-out Mac candidate.

### Selected-feature Rust notice recipe

The reviewed release-preparation recipe is now retained under `_scripts/notices/`.
It uses pinned official `cargo-about` 0.9.2 output, a small validation gate and
checksum-pinned upstream supplements. Its README gives the Linux collector
requirements and corresponding-source procedure. The recipe is separate from
application compilation and does not change color processing or the Cargo default.

Frozen C3 evidence at exact application source `0b5ba007` covers the selected
Mac arm64 `opencv,ocio-runtime,ffmpeg-next/static` and Windows x64
`opencv,ocio-runtime` features, both with defaults disabled. The selected graphs
contain 321 and 331 runtime crates respectively; each removes only
`breakpad-sys 0.2.0` compared with its default control. Their notice text SHA-256s
are `c2ef4af29a9d875f6cb1004d19d10c6c4f35d1900af87e12436c974ca5c20be1`
and `8462c06460774dd7b7d78eff27f7f8830dc80792cece838b0164f504464ac845`.
All 37 frozen packet members were independently checked against their manifest.
These are Linux-generated target metadata/notices, not a Windows build result.

Integration preserves the reviewed gate/config/supplement/archive-helper bytes.
The runner now refuses unsupported old Bash before collection and redacts source
paths literally; the template accurately labels overincluded build dependencies.
Syntax checks, actual old-Bash refusal and the exact redaction code with special
path characters passed. The full collector was not rerun for these changes, and
the frozen C3 outputs retain their original template and receipt identities.
Final package notice matching, corresponding-source delivery, attribution
decisions and current Windows native/app acceptance remain open.

### Corresponding-source archive layout correction

The deterministic Rust dependency archive was materialized from the retained
source tree. Its reported SHA-256 is
`15844ceb7bfb4a8051f34f10ee1e4590328bc4698b3d1b184cf4da6f04570d93`,
with an actual measured size of 1,062,123,520 bytes. The earlier 1,061,888,000-byte
measurement belongs to a different stream and must not be paired with this hash.
The archive remains in reviewer-owned cloud scratch; it has not been delivered
locally, uploaded for distribution, or accepted as a complete release source bundle.

Review found that extracting its generated `.cargo/config.toml` over the Git
archive would replace the tracked target linker flags. Instructions now require
the dependency archive at a parent root and the unchanged Git source at `root/src/`,
with Cargo invoked from the child. The parent source-only and child target-only
configs can then merge under Cargo's documented hierarchy. The archive-generation
implementation is unchanged. Actual current-source offline graph resolution and
full source-preservation checks for this layout are pending in the existing review.

### Offline source availability and local Mac notice stage

The parent/child layout was subsequently checked for exact application source
`0b5ba007`. With a newly empty Cargo home, both selected offline graphs match
the frozen C3 lists byte for byte: 321 Mac arm64 and 331 Windows x64 crates.
All 672 public source files, modes and Git blob identities match before and
after, including the tracked target config. This establishes dependency-source
availability and preservation, not a new application build or compiler observation
of merged linker flags. The ten-member C6 report packet was independently hashed
and bound to the public Git tree and both complete graph lists.

One local `cargo vendor --frozen` invocation then completed from the Mac's
existing cache without a refetch. Its 30,761-file content manifest and generated
config match the reviewed tree exactly. The locally generated archive matches
the full SHA-256 and measured size above; all 30,762 members are unique, regular
files with safe paths. It is retained on the project's SSD, so delivery no longer
depends on the temporary review container.

The production packaging helper ran from a clean, isolated `0b5ba007` checkout
using its actual build receipt and the combined native/Rust notices. Source,
target, features and disabled defaults match the Rust notice receipt. Staging
completed in 5.86 seconds with zero runtime-audit errors or required external
Mac dependencies, and the ad-hoc signature passed strict verification. All 9,151
supplied notice files match their staged copies. The staged directory retains
the Git source archive and matching Rust archive beside the application.

The new signed executable SHA-256 is
`0b4669323894a4a0a3906f3b42c31bdb29625c0d97da045d34890ec85de3b5c0`.
After signatures were removed from owned comparison copies, its executable
payload matches the earlier tested `0b5ba007` stage exactly (SHA-256
`51d0918643668c185eff9462cdf2856923031beb9a5e1ab9cd8c7828233a0531`).
No application was rebuilt, started or installed during this notice-only stage.

Evidence: `_dev/root-rust-source-delivery-20261009/`, especially
`ARCHIVE-RESULT.json`, `FINAL-TECHNICAL-STAGE.json` and
`stage-with-rust-notices/SOURCE-BUNDLE.json`. This remains a local technical
candidate: current Windows full-app/package validation, final redistribution/source
review, supported-OS checks and distribution signing/notarization remain open.
No download was published and the default color runtime was not switched.


### Current Windows application build: 2026-10-09

The complete Windows x64 application now builds successfully from exact source
`ab680a27d75d1f109e92935b360c33e2d421758b`, with defaults disabled and features
`opencv,ocio-runtime`, using the locked offline Cargo deploy build. The source
was acquired as an exact commit archive, not a Git checkout; all 682 approved
files matched before and after compilation. The resulting AMD64 executable is
43,899,904 bytes, with SHA-256
`cb9da6639f24a507e9e0b6a4f1b78c5c4ecd63392d25335077e160d507a0f954`.
Cargo reported success and the expected feature set. Its preliminary PE audit
found no debug CRT imports; full packaged runtime closure remains a separate check.

The enclosing verification wrapper exited with a failure because its `/EHsc`
check searched Cargo's top-level logs. Both actual compiler commands were instead
retained in the application's build-script output, at lines 34 and 450: the OCIO
bridge and generated preview translation unit each include `/EHsc`. Independent
read-only reconciliation verified those commands and completed the source/cache
comparisons skipped after the failed check. All 2,654 copied cache inputs and
23,358 protected files matched. The owned build job reached zero active processes
and closed; user settings and the existing applications remained unchanged.
The original failed wrapper result is retained, rather than relabeled as a pass.

This accepts the compiled application independently of that wrapper. It does
not establish execution of the new app, interactive preview, saved-grade hardware
exports, installation, or a portable Windows package. A fresh private package
and those app-level checks are the next steps; no rebuild is needed solely to
resolve the log-search error. The public download and default color runtime
remain unchanged.

### Current Windows private application checks: 2026-10-09

The exact application above was staged privately with Qt 6.7.3, official OCIO
2.4.2 and the pinned native dependencies. The native dependency audit reported
zero errors, including architecture, import/symbol resolution and the native
CRT FileVersion check. This is an audit and run on the development laptop, not
proof of a clean-machine portable release.

Two saved-project exports used the same original DJI O4 clip, stabilization and
45–49 second requested trim: neutral, and the selected DJI LUT with all eight
controls set. Both completed and independently decoded to 242 frames at
3840×2160, HEVC Main 10, with matching timestamps, pixel format and color tags.
Their actual duration was 4.037367 seconds; the application's nominal 240-frame
progress total is not an exact output-frame count. Every full-resolution decoded
frame hash differs between the neutral and graded files. This establishes that
the saved grade affects export while preserving the compared output properties;
it is not a numerical color oracle or a new matched performance benchmark.

GPU encoding was requested. Both runs reported `Rendering completed` and no
`uses_cpu` error. The existing queue marks initialization of the software HEVC
encoder as `uses_cpu` when GPU encoding is requested, so the fallback guard
passed. NVENC specifically is inferred, rather than established by a retained
encoder-name observation.

Actual interface startup exposed a packaging error: generated `qt.conf` pointed
QML imports at the application root, while the deployed modules were under
`qml/`. The staged configuration was corrected and its native audit passed.
The application then created its window without QML path environment overrides.
The matching packaging source fix is `d2f45862`; the application executable is
unchanged. The original failed startup evidence is retained. Screen capture
showed the laptop's screensaver, so visible preview comparison and interactive
save/reopen/reset checks are still unverified.

The private phase closed every owned application job and verified all 1,298
original input pins without mismatches. Its frozen handback SHA-256 is
`f937fece805730436a8095653a35207d668e02eea4692e5e96aa4797b8e10fd0`.
Native dependency notice/source provenance collection and the interactive checks
remain open. This does not approve an installation or public download, and the
default color runtime remains unchanged.
