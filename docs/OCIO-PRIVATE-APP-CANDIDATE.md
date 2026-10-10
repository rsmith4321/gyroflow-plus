# Private official-runtime Mac app candidate

Checked 2026-10-08 on Apple M4 Max / macOS 27.0.1. The separately built and
staged application uses official OpenColorIO 2.4.2 for CPU color processing and
generated GPU preview. This report describes a historical private candidate,
not a public download. The Cargo default and public release remain unchanged.

The [current installed Mac candidate](OCIO-MAC-ACCEPTANCE.md#current-installed-candidate-2026-10-09)
supersedes the earlier Homebrew-dependent installation. The separately rebuilt
dependency inputs are described in [dependency acceptance](OCIO-DEPENDENCY-ACCEPTANCE.md).

The [current Windows acceptance](OCIO-WINDOWS-ACCEPTANCE.md) separately records
the later Windows build, hardware export and complete private notice assembly.
Windows-unavailable statements in this historical Mac report describe those
earlier checkpoints; current Windows native preview remains unverified.

## Build and stage identities

The frozen source snapshot is `a8e5dc1dcbfe361bffd623c0ed61199b5cc1fc83`;
its runtime implementation is `b9f744a3e09c38e5ca0a19f933739cbb28277df6`.
Intervening changes affect documentation and remove privileged Spotlight/XProtect
manipulation from the deployment recipe; the runtime color files are unchanged.
The private deploy build
uses `ocio-runtime,ffmpeg-next/static`, an arm64 target and macOS 11 deployment
metadata. It completed in 3m46s; that is build duration, not an export benchmark.

| Artifact | SHA-256 |
| --- | --- |
| Original deploy executable | `aaac3400ff01abea52cafe44d5198a2f0f871b46110fdc6660e022e3ebabe031` |
| Final staged executable | `63237f564646fdd26e34a170ea0ffcfb33b7edac65c242ec186c3be89c411ee2` |
| Final bundle path/file/symlink manifest | `9e203c3713d957495dfe3f3696258c4242ff5268c784606214480fdf39e3895f` |

The final bundle has 836 regular files, 157 symlinks and 146,870,829 regular-file
bytes. Its local ad hoc CDHash is
`cfc28a75b82b118ec9cdfeba77fbdf4de0711d6d`; deep/strict signature verification
passes. This is not a Developer ID signature or notarization acceptance.

Accepted private inputs are Qt 6.7.3 with matching ShaderTools and SVG,
OpenColorIO 2.4.2, OpenCV/contrib 4.14.0, source-built static FFmpeg with the
recorded codec dependencies, and the identified existing MDK 0.39 SDK. Fresh
bindings, 129 generated native objects and 71 compiled QML/JS units were
independently checked. Every inspected stage Mach-O slice is arm64 and records
macOS 11.0. That metadata does not establish execution on macOS 11.

The only private ffmpeg-sys-next overlay removes obsolete unconditional QTKit
and VideoDecodeAcceleration framework link requests. Their SDK stubs are absent
on the build host, and the accepted static archives import no symbols from them.
The overlay changes no FFmpeg headers or processing code. The private lockfile
changes only that crate's source identity; all other package records match the
frozen main lockfile.

That statement describes the original frozen candidate. The current root source
now retains the published crate and the same two-request correction under
`vendor/ffmpeg-sys-next-9.0.0/`, with an offline package/patch verifier and staged
notices. Its only difference from the original private overlay is the explanatory
comment. Current-source build/runtime acceptance is recorded separately in
[integration evidence](OPENCOLORIO-INTEGRATION.md); it does not replace the
historical artifact identities above.

The unchanged core build script fetched a missing lens-profile database through
its mutable `latest` URL despite Cargo `--offline`. The retained bytes match
official lens-profile release v41, asset 492091898, with SHA-256
`5b9136697b75ddf9cda20965f17e786b6c8530e3d59109f87505069602e7f676`.
Reproduction must reuse that retained digest-checked asset. Cargo offline mode
alone is not evidence that arbitrary build-script HTTP is disabled.

## Reviewed runtime closure

All 92 staged Mach-O images were independently audited. Their 1,220 hard
dependency edges resolve to 744 Apple/system and 476 bundled targets. No retained
search path expands outside the bundle or Apple system locations. Optional weak
loads remain separately recorded; unused external RAW runtimes are not supplied
or accepted by this result.

Stage-only corrections preserve the accepted input SDKs:

- Three unused external SQL drivers are retained outside the candidate bundle;
  SQLite, QtSql and QML local storage remain included.
- Seventeen flattened Qt Quick plugins receive corrected bundle-relative search
  paths. MDK codec aliases and wrapper paths resolve to the retained bundled
  libraries.
- Zero-byte source placeholders are retained outside code directories so strict
  signing can succeed.
- The matching SVG image plugin is explicitly included after native testing
  exposed its omission by deployment tooling. The logo and icons then display
  correctly, and actual load samples observe this plugin inside the bundle.

No installed app was replaced. Complete distribution notices/source obligations,
MDK provenance and rights, clean-machine loading and older-OS execution remain
separate release gates.

## Native preview and hardware exports

Three private CLI exports use the same DJI O4 ten-bit source copy, saved
stabilization, 45–49 second trim and explicit settings as the retained b9 cases:
neutral, LUT only, and LUT plus all eight controls. Each succeeds with 242 decoded
frames, 3840x2160, HEVC Main 10, 60000/1001 fps and BT.709 limited range.
VideoToolbox `allow_sw=0` is required; no initialized software-encoder marker or
failed completion appears. Sampled non-system libraries resolve inside the
candidate bundle. Single instrumented export durations are not matched timing
measurements or a performance acceptance.

The final signed bundle also completes a 4K grading export through the normal
native interface. All 242 decoded GUI frames equal the new CLI grading output
exactly, including packet timestamps. Their shared decoded SHA-256 is
`b978e185c3d7a92b0328f9c8af3c05fe2abc7dde02cc58ab09d79d4d0fa83212`.
Preview color switching changes the paused picture, and double-click exposure
resets it to zero. These actions were checked with normal pointer input.

An earlier startup observation briefly displayed an unloaded-video warning or
incomplete first frame. A later ordinary chooser load and seek displayed the
moving picture and enabled export; the earlier startup boundary has not been
classified as fixed. The original installed app/session was restored after the
private test, with its previous LUT and exact live slider values. The installed
executable, authored project, source media and LUT remain unchanged.

## Hold: color output versus the earlier b9 build

Independent full decoding of all 242 frames establishes:

| New candidate versus retained b9 OCIO | Mean absolute error in 10-bit codes | Maximum error |
| --- | ---: | ---: |
| Neutral | 0, exact | 0 |
| LUT only | 4.09322 | 159 |
| LUT plus all controls | 5.80621 | 237 |

Source/authored-project/LUT hashes, dimensions, range, matrix, timestamps and
keyframe positions match. Generated case projects differ only in output filename
and folder. The color integration source files are byte-identical. Local
positive/negative differences and nearly unchanged plane means do not support
assuming a simple global matrix/range shift. Compressed outputs alone do not
identify the cause.

A bounded old/new OCIO comparison uses the exact production LUT parser,
canonical cube and C++ bridge. For 32,768 RGB pixels, actual O4 LUT-only maximum
float difference is 5.96046448e-8; O4 with the exact export controls is
2.38418579e-7. Alpha is exact and all values are finite. These small sampled
differences do not reproduce the large decoded export difference or establish
full real-frame parity.

The earlier exact 131,072-float prefix comparison used a synthetic LUT plus
matrix. Rust29 uses synthetic fixtures. Metal82 includes actual O4 cases but
compares CPU/GPU within the same new prefix. None of those earlier checks was an
old/new actual-O4 comparison; the production bridge check above supplies that
missing coverage within its bounded sample.

A standalone synthetic conversion probe also found eight supported conversions
exact between retained vendor-static FFmpeg and the new source-static candidate.
The actual b9 app uses Homebrew dynamic FFmpeg; that first probe did not exercise
the b9 conversion runtime. A second bounded probe links against the actual
Homebrew 9.0.1 library family matching b9's declared imports, and observes those
libraries at runtime. Historical b9 loaded-library inodes are not reconstructed.
Its eight
supported default/legacy conversions also match the private static candidate
exactly, with unchanged synthetic inputs. Pure-C backend selection rejects the
four conversions in both builds; no fallback substitutes for those failures.
Neither standalone probe accepts real rendering frames or explains the color
output difference.

A subsequent real-video discriminator exports four frames per case through
software H.264 with explicit ten-bit CQP0. Actual bitstreams establish transform
bypass, zero luma/chroma quantizers and the requested pixel format; this is not
an assumption based on a quality-option name. Old/new neutral output is exact
across 49,766,400 decoded samples. With the O4 LUT and all eight controls,
256 samples differ by one code value, with mean absolute error
5.1440329218107e-6. Independent checks confirm every decoded value is within
0–1023 and the signed differences are evenly split. LUT contents and all
source/settings/project/binary/media preservation checks pass.

This lossless test changes the target to planar YUV420P10LE and shortens the trim
to 45,000–45,040 ms. Both changes can affect the processing route or adaptive
zoom. It establishes near agreement for this software branch, not equivalence
of the original VideoToolbox branch. Existing hardware-export differences
are smaller at keyframes and increase between them, which is compatible with
predictive encoding propagating small differences. That remains a hypothesis;
the retained hardware exports did not record their encoder input.

Two bounded debugger attempts produced no frame samples: the first stopped
before FFmpeg loaded and the second timed out before reaching application main.
Both diagnostic children were stopped, and preservation checks passed. This
debugger route is discontinued.

A subsequent private source diagnostic preserves the original 45–49 second
trim, 4K HEVC settings and stabilization. Two rebuilt variants hold source,
Qt/OpenCV/MDK and static codec inputs constant while selecting the previous
Homebrew FFmpeg/OCIO family or the private static FFmpeg/OCIO family. Four
sequential runs capture one frame at each color boundary, then deliberately
stop before encoder initialization or submission. This is test instrumentation,
not a production change or recreation of the retained b9 executable.

Actual loader logs observe the intended OCIO prefix in each variant. The new
executable contains static application FFmpeg definitions but also loads the
Homebrew FFmpeg images later during MDK initialization. These isolated build
targets are not the relocated app bundle, and this diagnostic is not evidence
of a Homebrew-free runtime. Loaded-image lists alone do not establish ownership
of every FFmpeg call.

Both cases capture the same PTS, P010LE input/output, GBRPF32LE intermediate,
color metadata and strides. The YUV boundaries record BT.709 limited range;
the float intermediates record RGB matrix and unspecified range. The Rayon
pool records 16 threads with the production OCIO worker limit of eight. All
input/settings/source/prefix preservation checks pass. Across the complete
first frame:

| Boundary | LUT only | LUT plus all controls |
| --- | --- | --- |
| Stabilized P010 input | Exact bytes | Exact bytes |
| Float input to OCIO | Exact bytes | Exact bytes |
| Float output from OCIO, maximum absolute difference | 1.1920928955078125e-7 | 2.980232238769531e-7 |
| Restored P010, changed 10-bit samples | 59 of 12,441,600 | 79 of 12,441,600 |
| Restored P010, maximum difference | One code value | One code value |

All captured float values are finite. Restored P010 comparisons use the ten
significant bits; their six unused low bits are zero. Input P010 low bits are
often nonzero, and the exact-byte input comparison includes them. The small
restored differences are nearly evenly split in sign. Capturing these inputs
alone does not explain the larger decoded hardware-export differences; the
controlled sensitivity test below supplies first-frame reproduction.

The new GUI/CLI and short software-lossless results do not lift the original
hardware-output hold. No production algorithm or conversion workaround is
justified by the results so far. The captured boundaries establish near
agreement for one rebuilt frame; they do not establish all-frame equality,
encoder determinism, or a cause for the retained outputs. A controlled encoder
comparison with identical input supplies the next bounded result below.

## Identical-input encoder discriminator

Four fresh standalone VideoToolbox sessions use the same captured restored
P010 frame: previous FFmpeg family, private static family, then one repeat of
each. The small consumer mirrors the inspected production bitrate, frame rate,
GOP, color fields and options. All four recorded contexts match, and actual
`allow_sw=0`/`realtime=0` readbacks require the hardware path. Each submits one
frame and drains one packet. Actual encoder/mux API addresses resolve to the
pinned Homebrew libraries in the previous family and the executable in the
static family. These standalone processes load no MDK, Qt or OCIO.

One pinned software HEVC decoder produces one 4K Main 10 YUV420P10LE frame from
each output. All 12,441,600 samples are exact across the four decoded pictures,
with shared SHA-256
`f39418d09faa8e2777962b2eee57b983fcfaf2321fe6ccaa370fff248b0346f2`.
The four encoded packet and file hashes differ; those differences alone are
not decoded-image differences. Independent MP4/NAL byte parsing finds exact
codec configuration and coded-picture NAL bytes across all four; the differing
sample bytes are confined to a prefix SEI NAL. Their meaning was not decoded,
so no timestamp/session explanation is assumed. All fixture/tool/library/source
preservation checks pass. Matrix and primaries tags are BT.709, range is
limited, and the transfer tag is unspecified in these isolated outputs.

This shows no decoded variation for the fixed fixture in these four sessions.
It does not establish general encoder determinism or reproduce the original
242-frame app lifetime. The probe uses direct software P010 with a device-only
VT context; the historical app's upload/context branch was not recorded.
The old dependencies themselves record macOS 26 even though the consumers
record macOS 11, so this is not older-OS acceptance. The remaining concrete
questions at this point are sensitivity to the measured small input changes,
temporal encoding and the actual full-frame sequence/process context.

## Measured-input sensitivity and original first-frame reproduction

Four further standalone sessions use one fixed previous-family encoder binary:
the captured old LUT fixture, new LUT fixture, then one repeat of each. Only
fixture selection changes. The recorded encoder contexts and hardware-option
readbacks match; actual API providers resolve to the same pinned libraries in
all four sessions. Each session submits one frame and drains one packet.

Independent comparison of the complete input confirms exactly 59 of 12,441,600
P010 samples differ by one ten-bit code value. Within each fixture, the two
decoded outputs are exact. Across fixtures, 5,883,985 decoded samples differ,
with mean absolute error 0.9785809702932099, root mean square error
1.8773769013458086 and maximum 41 codes. Every first-frame plane's differing
count, absolute-error sum and maximum exactly match the retained original
b9-versus-candidate LUT comparison.

Independent MP4 sample-table and HEVC NAL parsing also checks the original
exports themselves. Their full-file hashes match the retained receipts; both
first samples are sync pictures at presentation/decode time zero. The original
old first coded-picture payload equals both old-fixture outputs byte for byte;
the original new first coded-picture payload equals both new-fixture outputs.
All six decoder configurations are exact. Corresponding whole samples differ
only in prefix SEI bytes whose semantics were not parsed.

This establishes that the measured 59 one-code input changes are sufficient
to reproduce the original first LUT coded-picture difference using the same
encoder. It supplies a concrete first-frame explanation without changing
production color algorithms or converting tiny float differences into an
encoder-implementation fault. It does not establish the cause across all 242
frames, temporal rate-control behavior or the historical app upload branch.
This first-frame experiment did not establish full-sequence acceptance; the
later bounded sequence checks below address that separate scope. All source,
fixture, tool, library and settings preservation checks pass.

## Late color failures and CLI completion

Full-sequence instrumentation initially imposed an invalid ordering constraint
on raw AVFrame timestamps. Stabilization reuses its image buffer, and the real
encoder timestamp is assigned later. The observer now orders captures by the
serial color-call ordinal, keeps raw metadata for paired checks, and checks
completed packet timing separately. Production timestamps and stabilization
were not changed.

That failure exposed two error-path issues: the packet loop could suppress a
color-processing error after encoding started, and the CLI could print
completion when its counter reached an estimated total. The failed diagnostic
retained one captured frame and an incomplete temporary output, then reached
its log cap amid repeated completion messages. The precise second-call
timestamp rejection is source-derived; the old error path did not report its
exception text. That run is retained as a failure.

Two narrow source corrections propagate `ExportLut` errors after encoding has
started and require the queue's actual finished signal for CLI completion.
Color operations, decoder-error tolerance and hardware selection are unchanged.
The earlier staged and installed binaries predate these corrections.

A fresh deliberate failure before the second color call completed naturally
in **2.189 seconds**. It reported the injected error and `Rendering failed`,
reported no completion, retained one complete four-stage capture, and produced
no finalized video. Source, settings, project, LUT, original clip and all
**666** pinned inputs were preserved. The CLI's existing handled-error contract
still returns process status **0**; status alone does not establish success.

The diagnostic observes `hevc_videotoolbox`, VideoToolbox/P010, and the actual
encoder options `allow_sw=0` with `require_sw` absent/default zero. Together
with the successful first encoder open/send path, this establishes a
hardware-required session contract. It does not claim a specific AVE encoder
ID, a session-property readback, or a decoded frame from the unfinished fault
output. FFmpeg's [VideoToolbox implementation](https://github.com/FFmpeg/FFmpeg/blob/n9.0.1/libavcodec/videotoolboxenc.c)
requires hardware with these options. Private diagnostic logging is separate
from the production patch and is not timing evidence.

## Bounded full-sequence pipeline acceptance

Four normal exports completed with the corrected error/completion guards:
LUT-only and an eight-control grade, each using the old and new dependency
builds. Every export produced **242 encoded packets and decoded frames** of
3840x2160 HEVC Main10, `yuv420p10le`, BT.709 space/primaries, limited range and
60000/1001 fps. A transfer-function field was not reported by the probe.
The observed encoder options required VideoToolbox hardware, with software
fallback disabled. Finalized files, normal completion, exact selected OCIO
providers and preservation checks passed in all four cases.

Across all 242 ordered color calls, every active input plane before color
conversion and before the CPU processor had an identical paired SHA-256.
Thus the stabilized frame data entering color processing matched. Every
post-processor float plane was fully scanned for finite values and the fixed
min/max/compensated aggregate bounds. Output comparisons used **4,096 pinned
spatial coordinates per call**, including RGB and corresponding YUV components:

| Sampled comparison | LUT only | Eight-control grade |
| --- | ---: | ---: |
| Maximum absolute post-processor float difference | 1.1920928955078125e-7 | 2.384185791015625e-7 |
| Maximum restored 10-bit YUV difference | 1 code | 1 code |
| Differing restored components, out of 2,973,696 sampled components | 72 | 102 |
| Paired output packet PTS/DTS/durations | Exact | Exact |

These pass the preselected **1e-6 float / 1-code restored** bounds. They
establish the bounded sampled-pipeline contract, not exhaustive output-pixel
equality or identical lossy encoded/decoded pictures. Capture identity is the
serial color-call ordinal; raw reusable-frame timestamp metadata is not the
source clock. Output packet timing is checked separately.

This current-Mac check used rebuilt diagnostics with the same frozen color
implementation and two exact production guards. Observer/logging overhead is
not a speed benchmark. The diagnostics can load pinned incidental Homebrew
libraries through MDK; this does not establish portable dependency closure or
ownership of every FFmpeg call. The installed development app and earlier
staged bundle remain unchanged and predate the guards. The retained packet is
`full-sequence-color-diagnostic-v3/sequence-20261008T090459Z` under the private
evidence directory below; the deliberate fault packet is `fault-20261008T090440Z`.

## Real-frame CPU and generated GPU color agreement

Two retained stabilized 3840x2160 first frames now pass a complete-image
comparison through the production GPU adapter on Metal / Apple M4 Max. The
unchanged production bridge, fragment wrapper and adapter use the accepted
private OCIO 2.4.2 and Qt 6.7.3 inputs. The canonical O4 LUT and exact eight
controls match the capture. References are retained CPU export-stage float
planes; the test does not regenerate its own expected color values.

| Every full-resolution RGB component | LUT only | Eight-control grade |
| --- | ---: | ---: |
| Components compared per case | 24,883,200 | 24,883,200 |
| Maximum absolute float error | 1.1920928955078125e-7 | 4.172325134277344e-7 |
| Mean absolute float error | 8.931167941429256e-9 | 3.3321352583186437e-8 |
| Opaque alpha error | 0 | 0 |

All input, reference and GPU components are finite. Both cases pass the existing
strict **1e-5** native float tolerance, with exact dimensions and direct top-left
row order. Independent recomputation covers every RGB and alpha component;
runtime providers, source/input hashes, build provenance and preservation pass.
A separate display-scale visual comparison shows matching orientation, framing
and apparent colors. That illustration samples the image for display only;
the numerical acceptance uses every full-resolution component.

The retained packet is `real-frame-preview-parity-plan-v1/runs/replay-01` under
the evidence directory below. It performs two offscreen processor comparisons,
not native video decoding/display or an interactive frame-time benchmark. It
does not establish all 242 GPU frames, Windows execution, public packaging, or
resolve the original b9 lossy decoded-output compatibility hold. The installed
app, staged bundle, production algorithms and feature default remain unchanged.

## Matched candidate export timing

A fresh fixed-artifact comparison completed exactly **20 exports**: one
eight-control warmup per binary, followed by three alternating paired trials
for each of neutral, LUT-only and eight-control grading. The installed b9
development executable and private staged executable retain their pinned
identities. Both predate the later error/completion guards.

| 45–49 second source segment | Installed median (s) | Staged median (s) | Paired staged / installed |
| --- | ---: | ---: | ---: |
| Color disabled | 5.058269 | 4.942471 | 0.966513 |
| LUT only | 9.968430 | 8.024112 | 0.805157 |
| Eight-control grade | 11.865412 | 9.269408 | 0.783609 |

Ratios are the geometric mean of three matched pairs. All cases pass the
preselected **15% maximum/minimum spread** gate. All 20 exports finalized
242-frame, 3840x2160 HEVC Main10 output at 60000/1001 fps, with limited range
and BT.709 space. Actual options require hardware encoding without software
fallback; logs, selected providers and preservation checks pass. Independent
recomputation exactly matches every median, paired ratio, spread and noise flag.

These are CLI wall times including startup, export and teardown; validation
and preservation scans are outside the interval. They compare complete fixed
artifacts, without isolating OCIO, SIMD, FFmpeg or encoder contributions.
Chrome was active throughout recorded snapshots, reaching 94.7% CPU. A
Backblaze file scan during the staged warmup is retained and excluded only
from timed statistics; no timed trial trips the frozen interference classifier.
Passing repeatability does not rule out sustained background contention.
These results describe the observed host load and the pinned earlier binaries.

The retained packet is `matched-timing-plan-v2/runs/timing-v2` under the
evidence directory below. Settings, original media, both bundles and runtime
identities remain exact. This timing acceptance does not resolve the original
lossy decoded-output compatibility hold or establish a public package.

## Bounded generated GPU color timing

The unchanged production adapter, bridge and fragment wrapper now have
a bounded cached real-frame timing measurement on Metal / Apple M4 Max,
using the same accepted private OCIO 2.4.2 and Qt 6.7.3 providers. Each of
the two existing 3840x2160 RGBA32F cases uses **20 discarded warmup draws
and 100 measured draws**, followed by one untimed output guard.

| Cached 4K draw | GPU median (ms) | GPU p95 (ms) | CPU-through-GPU-completion median (ms) |
| --- | ---: | ---: | ---: |
| LUT only | 0.465938 | 0.578000 | 0.630292 |
| Eight-control grade | 0.462354 | 0.572292 | 0.624167 |

Every selected GPU duration is finite and positive. The separate wall interval
covers CPU polish, recording, submission and GPU completion. GPU elapsed
includes target clear and the production ShaderEffect draw. Initial input/LUT
texture upload and shader preparation occur before timing; readback, pixel
comparisons, hashes and file I/O are outside the measured loop. Raw ordered
samples retain the corresponding draw ordinals.

Review caught a one-frame publication delay in the exact
[Qt 6.7.3 Metal implementation](https://github.com/qt/qtbase/blob/v6.7.3/src/gui/rhi/qrhimetal.mm).
The corrected private fixture associates the following getter with each
measured draw; its final sample is collected when the existing untimed guard
begins. All 100 wall/GPU pairs are retained, with no added draw. The held initial
recipe was not executed. No Qt library or production code was patched.

Both post-timing full images exactly match the accepted GPU output SHA-256
and retain the previously verified CPU/GPU error and alpha results. Build/run
bounds, selected providers and preservation checks pass. The retained packet
is `real-frame-preview-timing-plan-v2/runs/timing-01` under the evidence
directory below.

Backblaze and Chrome were active in the retained host snapshots. These results
measure a resident, repeated first-frame color draw; they exclude MDK decoding
and stabilization, new-frame uploads, presentation/vsync, interaction and
export. They do not measure app FPS, isolate incremental OCIO cost without a
neutral baseline, or establish quiet-host or Windows performance.

## Historical sequence bridge

A bounded, decoder-free MP4 comparison now connects the retained historical
LUT/grade outputs to their respective later instrumented outputs. All four
mappings have **242/242 byte-exact coded pictures**, identical `hvcC`, packet
PTS/DTS/durations and keyframe positions. Only two bytes in each first prefix
SEI differ; SEI semantics were not interpreted. All seventeen inputs were
preserved, and independent retained-byte review passed.

This ties the accepted full-sequence stabilized input hashes and sampled
post-color checks to the original coded-picture sequences. It does **not**
make the old and new decoded outputs equal, expand sampled output checks to
every pixel, or lift the original exact decoded-preservation hold. The packet
is `goal-audit-current-v1/coded-picture-bridge-v1`.

## Current-source private bundle and integration

A fresh production candidate was built from clean, pushed source
`04f19fd42a84fade7cd881d75a83ea1de12b291e`, including the reviewed late color-error
and actual CLI-completion guards. It uses the accepted production dependency
recipe and pinned lens asset, without diagnostic hooks or a mutable profile
download. The independently reviewed bounded preparation, build and staging
phases completed naturally with source/settings/dependency preservation.

The fresh bundle differs from the earlier accepted bundle only in its main
executable, top-level CodeResources and twelve exact OCIO notice files.
Nested payloads remain byte-identical. All 92 Mach-O images retain arm64 and
macOS 11 minimum-version metadata; all 1,220 hard dependency edges resolve to
Apple or bundled images. Local ad hoc deep/strict signature verification
passes. These metadata checks do not prove older-OS execution or distribution
readiness. The signed executable SHA-256 is
`9ee723e59266f36e747027fb8838715ce92b846be59f28bb6f9efa4285909ad9`.

One independently accepted CLI integration export uses the existing 45–49
second O4 clip, canonical DJI LUT and all eight grading controls. It completes
with the hardware-required `allow_sw=0` contract and no rendering-failure or
CPU-fallback marker. The bounded probe confirms 242 frames, 3840×2160 HEVC
Main10 (raw profile enum `2`), `yuv420p10le`, limited range, BT.709 color space
and 60000/1001 fps. Transfer characteristics were not among its probe fields.
All eighteen observed non-Apple loaded images are inside the new bundle;
none comes from Homebrew. The log retains a separate H.264 constant-bit-rate
capability-probe error before the successfully completed requested HEVC export.
This is a single integration check, without a new timing or decoded-parity claim.

The installed app, earlier bundle, source media, authored projects, LUT,
settings and dependency identities are preserved. Retained packets are
`stage-v2-execution-v2` and `native-stage-v2-smoke-plan-v1/runs/smoke-01`.

## Current visual and preview boundaries

The computer-use tool launched the fresh candidate but failed to read its
window: an accessibility error followed by a timeout. Root closed only that
verified test process. Its two settings changes (app path and one-pixel window
width) were checked against the exact original backup and conditionally
restored; independent review verifies the original bytes and file identity.
This attempt supplies **no new GUI visual acceptance**.

Root viewed one 1920×1080 RGB8 derivative of the completed export. Orientation,
framing and image content are visible, with bright/clipped highlights in this
aggressive test grade. That is a single display-resampled frame inspection,
not a full-clip quality, native preview or numerical color comparison. The
first extraction exceeded its PNG size cap and remains a failed packet; the
fresh explicit RGB8 extraction passes its bounds and preserves the export.

A focused source audit confirms that native MDK/stabilization preview uses
RGBA8 and preview-dependent dimensions. It cannot be compared directly to
full-resolution floating export planes using the processor's `1e-5` limit.
The accepted same-input CPU/generated-GPU agreement remains valid within its
original scope. Unqualified end-to-end display/export pixel parity is not
claimed. Windows resume dispatch still reports an unavailable Codex app server;
no new Windows execution occurred.

## Current production output bridge

A further bounded, decoder-free comparison connects the guarded production
stage's grade export to the accepted earlier new-family grade output. All
242 coded pictures, decoder configuration, complete packet timing and
keyframe positions match exactly. Inspected container leaves match; only two
unparsed bytes in the first prefix SEI differ. Independent review confirms
all eleven fixed inputs were preserved. This is artifact correspondence,
not a new old/new decoded-equality result. The retained packet is
`current-stage-byte-bridge-v1`.

## Recovered native UI and preview toggle

A computer-use reset allowed a bounded native window check. It exposed a
checkbox integration issue: an accessibility action changed the displayed
check state without updating the model or color layer. The shared checkbox's
Return handler has the same direct property-assignment behavior. Reviewed
commit `1b7e832950f82f9db61a62b86754a0118495ee39` changes only the color checkbox
handler from `onToggled` to `onCheckedChanged`, plus an explanatory comment.
Color algorithms, export settings and processor defaults are unchanged.

A fresh private production bundle from that commit passed the same bounded
preparation, build and staging checks. Independent review verifies its signed
executable SHA-256
`d29a9d69f86ae39bd8442952c203f2c1db61dadbd6cfd1247501d69eddcec0ea`,
unchanged nested dependencies and notices, and preserved phase inputs. The
build retains two existing dead-code warnings.

Root observed the native app at a paused frame inside the existing test
range. Accessibility toggle, physical mouse click and Return key all made
the checkbox, LUT status text and visible picture change together between
original log colors and the selected aggressive grade. Gyroflow+ branding,
Community fork text and the eight color controls are visible; the exposure
field has no overflowing stops suffix. The candidate quit naturally with
exit zero. Source media, LUT and test project stayed unchanged, and only
three proven launch preferences were conditionally restored to the exact
original settings bytes and identity.

This is one-frame native UI integration evidence, not numerical display/
export parity or full-clip stabilization/quality acceptance. The initial
00:00 view was largely blank with a small triangle; that observation outside
the selected 45–49 second test range is retained without first-frame visual
acceptance. Retained packets are `stage-v3-preview-toggle-v1` and
`native-stage-v3-preview-toggle-v1`. No new export or timing matrix was run
for this UI-only fix. Current Windows access remains unavailable.

## Remaining acceptance

Original decoded color-output release acceptance, current Windows native
preview/export, complete bundle notices/provenance, clean-machine installation,
older-OS execution and public signing/notarization remain open. The private
bundle must not be offered as a release download on this evidence.

Exact commands, hashes, build/source reviews, stage inventories, native logs,
input-preservation receipts and independent output comparisons are retained
under `_dev/ocio-runtime/portable-app-build/`. Camera media and vendor LUTs are
not redistributed.
