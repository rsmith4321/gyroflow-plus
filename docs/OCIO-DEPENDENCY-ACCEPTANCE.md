# Private OpenColorIO dependency acceptance

Verified 2026-10-08 on Apple M4 Max / macOS 27.0.1. This is an official
OpenColorIO **2.4.2 dependency candidate**, independently reviewed and exercised
with production fixtures. It is not a complete portable app or a public download.
This section records the dependency candidate as tested on that date. The
[current installed Mac candidate](OCIO-MAC-ACCEPTANCE.md#current-installed-candidate-2026-10-09)
now bundles its runtime dependencies; the older installed development app used
the local OCIO prefix recorded in the historical Mac acceptance section.

A later separately linked, relocated and locally signed full app candidate had
current-Mac native preview/hardware export evidence. Its initial color-output
comparison with the earlier b9 development build required investigation. See
[private app acceptance](OCIO-PRIVATE-APP-CANDIDATE.md) for that investigation, the
exact build/stage identities, completed checks and remaining gates. Later
acceptance and installation do not change the identities or scope of the
individual dependency checks below.

The later [current Windows application acceptance](OCIO-WINDOWS-ACCEPTANCE.md)
records a successful selected-feature build, directly observed hardware export,
complete decoded-output comparison and private notice assembly. Native Windows
preview and public distribution remain separate open gates; historical Windows
limitations below describe the earlier dependency checks.

## Compiled runtime closure

The shared OCIO library includes private static Imath, yaml-cpp, pystring and
minizip-ng, and uses Apple's system Expat/zlib. OCIO applications, Python, Java,
documentation, upstream tests, OpenFX and Nuke were disabled.

| Property | Verified result |
| --- | --- |
| Library | `libOpenColorIO.2.4.2.dylib` |
| Bytes | 6,365,128 |
| SHA-256 | `b1939e6d021afebdabdd22c6748bebc89c73866f51fde3e773d229911f4911f3` |
| Architecture | arm64 |
| Recorded minimum macOS | 11.0, including inspected private static archive members |
| Build SDK | macOS 27.0 / Apple clang 21 |
| Install ID | `@rpath/libOpenColorIO.2.4.dylib` |
| Runtime search path | `@loader_path` only |
| Non-Apple dynamic dependencies | None |

Actual dynamic loads are system Expat, zlib, libc++, libSystem, ColorSync,
CoreFoundation, CoreGraphics and IOKit. Homebrew CMake was a build tool; no
Homebrew library appears in this runtime's load commands. Recorded deployment
metadata does not establish execution on macOS 11. Older-OS execution remains
an acceptance gate.

## Upstream source and SIMD

Independent review compared all 1,938 OCIO files and 337 Imath files with their
official archives: no differences or extra files. The external dependency source
archives also match the compiled private sources. No color algorithm was edited.

An upstream CMake compiler check split an include path containing spaces into
separate shell arguments and disabled SSE2NEON in the earlier development build.
A private override changes only the check's include-directory argument:

```cmake
# Old try_compile argument:
COMPILE_DEFINITIONS "-I${sse2neon_INCLUDE_DIR}"
# Private build override:
CMAKE_FLAGS "-DINCLUDE_DIRECTORIES:STRING=${sse2neon_INCLUDE_DIR}"
```

The intrinsic test source is unchanged. Actual compiler/linker execution succeeds;
both ARM NEON and SSE2NEON checks pass, and the generated arm64 configuration
sets `OCIO_USE_SSE2NEON` to 1. No feature result is forced.

Top-level discovery excludes `/opt/homebrew` and `/usr/local`; the recorded
external subprojects exclude `/opt/homebrew`. Actual link inputs were verified
as private archives or SDK libraries. Future build recipes should propagate
both exclusions into every subproject and recheck the complete inputs.

## Production fixture acceptance

Root independently ran the existing fixtures against this exact stable prefix:

- **29 production Rust tests passed**, including owned-frame validation,
  copy-on-write, unequal strides, alpha/padding preservation, YUV conversion,
  processor concurrency and generated resource extraction.
- **82 actual Metal float32 comparisons passed**, with maximum CPU/GPU difference
  **2.384185791015625e-7** against the 1e-5 bound. These use Qt 6.11.2 and the exact
  production bridge/preview adapter. Cache cleanup, scenegraph recreation,
  ownership/error delivery and separate software-renderer rejection passed.
- A separate synthetic official LUT3D-plus-matrix probe compared **131,072 float
  values** with the previous OCIO prefix: observed maximum difference **0.0**.
  It separately checked populated 1D/3D resources and generated shader text.

In three processor-only measurements, the synthetic probe's median throughput
was 295.207 MP/s for this private build versus 215.113 MP/s for the previous
development build, a ratio of 1.3723. Each run applies 2,000 rounds to 32,768 RGBA
pixels; copies and input preparation are outside the interval. This comparison
covers two complete dependency builds and does not isolate SIMD from dependency
version/linkage differences. It is not a video-export or universal speed claim.

Private logs and machine-readable receipts are retained under
`_dev/ocio-runtime/portable-prefix/` and `portable-validation/`. No camera media
or vendor LUT is redistributed. These new fixture results do not substitute for
the previously recorded full-app/stabilized-video checks or a new app candidate
linked against this prefix.

## Source pins and notices

| Dependency | Version | Exact upstream commit |
| --- | --- | --- |
| OpenColorIO | 2.4.2 | `6918fad3f5d22ac3ef2397c754bf4268c2b58dd0` |
| Imath | 3.1.12 | `c0396a055a01bc537d32f435aee11a9b7ed6f0b5` |
| yaml-cpp | 0.7.0 | `0579ae3d976091d7d664aa9d2527e0d0cff25763` |
| pystring | 1.1.3 | `c2de99deb4f0bd13751f8436400b5e8662301769` |
| minizip-ng | 3.0.7 | `241428886216f0f0efd6926efcaaaa13794e51bd` |
| SSE2NEON | OCIO's upstream pin | `227cc413fb2d50b2a10073087be96b59d5364aea` |

The official codeload OCIO archive SHA-256 is
`2d8f2c47c40476d6e8cea9d878f6601d04f6d5642b47018eaafa9e9f833f3690`;
Imath's is `8a1bc258f3149b5729c2f4f8ffd337c0e57f09096e4ba9784329f40c4a9035da`.
The private provenance receipts retain every other archive/content hash, SDK
header/stub hash, exact configuration, command and resolved library input.

The notice collection includes all direct static dependencies and OCIO's
embedded SampleICC/xxHash copyright/license headers. OCIO's root BSD notice
alone is insufficient for redistributing those embedded components. Apple's
Expat/zlib are system dependencies; runtime versions come from the user's OS.
The SDK/current host report Expat 2.7.4 and zlib 1.2.12. No independent security
patch conclusion is inferred from those version strings.

The exact runtime notice packet and public source-pin/hash index are now retained
in [the repository](../resources/color/ocio-third-party/README.md), alongside the
unchanged OCIO root notice. This preserves the texts with a source clone; it
does not add them to the earlier staged app or close whole-app distribution
notice/source obligations. Binary packaging must include and verify the packet
against the actual selected OCIO build.

## Remaining app and release gates

### Matching Qt 6.7.3 preview compatibility

A separate official Qt 6.7.3 Mac SDK candidate now passes the same **82 actual
Metal comparisons** and separate software-renderer rejection with this OCIO
prefix; maximum CPU/GPU difference remains **2.384185791015625e-7**. Production
source compiled unchanged against the matching Core/Gui/Quick/Qml/ShaderTools
modules and private headers. This checks the inherited Apple Silicon Qt version;
Intel's separate Qt 6.4.3 recipe remains untested and unchanged.

The three vendor archives were checked against fresh official checksum sidecars
and additionally SHA-256 hashed. Matching official source archives and 151
notice/version files are preserved. All 124 inspected runtime arm64 slices and
the linked QtQmlBuiltins static members record a macOS 11.0 minimum. The required
ten-file framework/Cocoa closure totals 67,805,808 bytes and resolves within the
private Qt SDK or Apple system libraries. The entire SDK also includes unused
SQL drivers with external iODBC, Postgres.app and unresolved Mimer loads; those
remain intact and are excluded from this narrow closure claim. Every plugin
actually shipped by a future app must pass the complete stage audit.

The private dependency inventory originally discarded the first dependency of
bundle plugins by assuming it was a dylib ID. Independent review caught this;
the corrected inventory parses explicit Mach-O IDs and all load commands and
matches independent inspection of all 124 files with zero differences.

On SDK 27, the old Qt CMake OpenGL target adds a direct AGL link requirement
whose SDK stub is absent. A private configuration omits only that redundant
consumer link entry for the Metal harness, which calls no AGL API. Official
QtGui still imports Apple's loadable AGL runtime. SDK binaries and production
source are unchanged. This workaround is scoped to the fixture and is not yet
accepted for a complete application build.

Private reproducibility, archive hashes, notices and corrected inventory are
retained under `_dev/ocio-runtime/portable-qt/`. This is current-host preview
compatibility and a dependency candidate, not old-OS execution or a portable app.

### Inherited FFmpeg archive

The inherited FFmpeg 9 static recipe was acquired and audited separately. Two
vendor transfers match SHA-256
`9e79bc612d38f844faf725dbe4576f8aa2dd715ec57d3654dbadcc9b860645b9`
(20,099,916 bytes). It is not accepted for a macOS 11 app candidate:

- Some arm64 x264/x265 assembly objects record a **macOS 14.0** minimum, although
  FFmpeg core objects record 11.0.
- A real consumer link using the recipe's nine static libraries fails with
  **34 unresolved FreeType/HarfBuzz symbols**; those libraries are absent.
- The bundled GPL notice is empty. Exact vendor patches/build commit and
  corresponding dependency source remain unverified.

The header's `ad500d5-avbuild` identity resolves to official FFmpeg baseline
`ad500d59cb6e0126add4fcb95afb4e2557c4292c`; its source and notices are preserved.
That identifies a baseline, not complete corresponding vendor-patched source.
Shared-library metadata queries succeed on the current Mac and report the
expected codecs and VideoToolbox encoder registration. They do not resolve the
static blockers or prove hardware encoding, older-OS or full-app execution.

No codec or filter was removed and no installed app was replaced. Private
hashes, object metadata, link failure and provenance receipts remain under
`_dev/ocio-runtime/portable-ffmpeg/`. A separate reproducible source build must
retain the required capabilities, verify its entire static closure and OS floor,
and preserve matching source and notices before app staging.

### Separate official-source FFmpeg candidate

A separate private rebuild now supplies unchanged official FFmpeg baseline
`ad500d59cb6e0126add4fcb95afb4e2557c4292c`, with pinned x264, x265 4.3,
FreeType, HarfBuzz and XZ dependencies. Independent review compared all 10,424
FFmpeg source files and the selected dependency sources with their retained
official archives. All 482 installed SDK files match the frozen manifest.

The fourteen static archives contain **1,904 arm64 object members**, all recording
macOS 11.0, including codec assembly. Native static consumers and FFmpeg/ffprobe
link with Apple-only declared dynamic dependencies and no rpaths. Corrected
relocatable pkg-config metadata also works from the application checkout and an
unrelated directory containing spaces. Original generated metadata is retained.

Actual candidate/vendor registrations match: **41 encoders, 90 decoders and 77
filters**, plus the same VideoToolbox/Vulkan hardware registrations. An initial
parser counted the CLI legend as a codec; independent review corrected the
counts while preserving the original receipts. x264 and VideoToolbox pixel
formats match; x265 retains the eighteen vendor formats and adds two alpha
formats. Hardware-required H264/HEVC sessions create and prepare on the current
Mac, but no frames were submitted in that dependency probe.

This is an independently pinned source candidate, not an exact reconstruction
of the opaque vendor build. Codec versions and vendor software-fallback,
timestamp, MPEGTS/HLS and atempo patches differ. Registration parity does not
establish behavioral equivalence. Production app linking, moving-frame and
hardware encoding, optional Vulkan runtime discovery and complete packaging
remain gates.

Independent review found missing FreeType license/embedded notice texts in the
first copied packet. The corrected conservative source/notice packet retains
8,641 exact files and covers the declared selected compiler dependencies without
recognized notice-bearing omissions. Its source bytes and all frozen SDK files
were independently rechecked. This closes that packet omission within its
declared scope; final distribution obligations and the separate MDK component
packet remain open. Build recipes, pins, failures and corrected receipts are
retained under `_dev/ocio-runtime/portable-ffmpeg/source-plan/`.

### Full application

Use this prefix only for a separately staged candidate and preserve the `.2.4`
library-name symlink and complete notices. A matching Qt distribution including
ShaderTools and SVG, compatible FFmpeg/codecs, OpenCV, MDK/plugins and all other
runtime components need complete application integration and closure checks.
Bundle-relative app search paths, full app preview/export acceptance, execution
on the declared minimum OS, Windows, signing/notarization and clean-machine
installation remain open. Cargo defaults, public releases and website engine
claims are unchanged by this dependency acceptance.

### Matching Qt SVG graphics

The matching official Qt SVG 6.7.3 supplement preserves the application's SVG
graphics. Its two frameworks and two image/icon plugins total 1,534,632 universal
bytes; all inspected arm64 slices record macOS 11.0. Their declared imports
resolve within the private matching Qt SDK or Apple libraries. A native synthetic
probe on the current Mac rendered identical 128x128 images through QSvgRenderer
and the actual SVG image plugin, with expected red/blue pixels and no observed
Homebrew runtime loads. The icon plugin and QtSvgWidgets have metadata inspection
only; the probe does not establish complete app or older-OS behavior.

Independent review found the first notice collector omitted SPDX-named license
texts. The corrected packet includes the complete upstream `LICENSES` directory;
all seven license texts and thirteen retained notice files match source bytes.
Official archives, checksums, source, native load logs and corrected notice
receipts remain under `_dev/ocio-runtime/portable-qt-supplements/`. A separate
copy of the accepted Qt SDK combines these modules for future app builds without
changing either accepted input.

### Matching OpenCV and contrib

The existing vcpkg dependency is OpenCV 4.14.0; its retained core objects record
macOS 27.0 and its installed headers lack the declared contrib optical-flow
module. A separate official-source candidate keeps the twelve existing modules
and adds `optflow` plus its `ximgproc` dependency. OpenCV source is pinned to
`0654a42e19215ef25b1d367d822f3c630447e7c7`, contrib to
`a8e9acd62cabd30419dba83007f2ac0d07de5e2c`.

All 431 arm64 objects across fourteen static archives record macOS 11.0. A native
consumer force-loads every archive object and links successfully using private
archives and Apple SDK libraries. Synthetic calibration, feature tracking,
optical flow and parallel-work checks pass on the current Mac. The actual
application's OpenCV Rust crate 0.99.1 and requested feature set also build and
execute in a private probe; all eight generated binding objects record 11.0.
NEON, pthreads/GCD and AVFoundation remain enabled. This is dependency evidence,
not full stabilization or older-OS app acceptance.

The generated OpenCV pkg-config file has incomplete static framework metadata
and an invalid SDK zlib library token. Use the verified explicit fourteen-library
environment retained with this candidate instead. Independent review also found
omitted embedded TVL1, SLIC/MSLIC and FLANN notices. The corrected packet retains
319 distinct original legal texts mapped to 1,622 source occurrences, with all
431 objects and 812 source/header dependencies covered. Ship the **entire**
`notices/corrected-v2/` packet, including its text files, plus the original project
notices. Independent reinspection found no remaining gap within that declared
scope. Source, build, closure and corrected notice receipts remain under
`_dev/ocio-runtime/portable-opencv/`.

### Existing MDK preview and RAW-format gates

The retained MDK framework and plugins are coherent private build inputs, with
arm64 slices recording macOS 11.0. They are not an accepted portable runtime
closure. The already running development app actually loaded Homebrew dav1d
(minimum macOS 26.0), and the old Qt/MDK wrapper object records macOS 27.0. A new
candidate must rebuild the wrapper against private Qt and prove bundled dynamic
resolution. Retained MDK search paths include Homebrew and `/usr/local`.

The pinned `qml-video-rs` wrapper commit is
`855130d4f423321e60c4bb95b913dc1e22c1eb88`; its default unversioned nightly SDK
download is separately unpinned. Reusing the identified cached SDK through the
verified `MDK_SDK` guard avoids a new mutable download during private integration.
That does not recover the original binary acquisition provenance or establish
distribution rights/notices for this fork.

BRAW, R3D and NEV processing paths and existing plugins remain intact. Plugin
loading does not establish RAW decoding: the retained app/target trees lack the
separate vendor RAW runtimes named in the audit. Exact runtime versions, terms,
corresponding sources/notices for the shipped MDK components, and fork-specific
entitlement remain release gates. No vendor agreement was accepted or RAW SDK
acquired during this audit. Detailed read-only evidence is retained under
`_dev/ocio-runtime/portable-mdk-audit/`.

### Metal build tool acquisition

The FFmpeg source candidate initially encountered Xcode's missing Metal compiler
component. The matching official Apple component (Xcode build `27A266a`, compiler
`32023.921`) was downloaded with an export destination. Xcode also installed and
activated it in its managed component cache; this was a host toolchain change,
not a private-only export. Compiler version and Apple signature checks pass.
The unchanged upstream FFmpeg `yadif` Metal source separately compiles with an
explicit macOS 11.0 target and Metal 2.3 language version. This is a shader build
check, not filter/video execution. Original failure logs, exported component
hashes and activation receipts are retained under
`_dev/ocio-runtime/portable-metal-toolchain/` and the FFmpeg source candidate.
