# Official OpenColorIO runtime probe

Development experiment for replacing custom color evaluation with OCIO's public
CPU/GPU processor API. It does not change the installed app or default renderer.
The selected camera LUT still belongs to the existing LUT path in this probe.

`probe.cpp` defines the current eight-slider semantics once using OCIO matrix,
range, video tone and video primary transforms. OCIO executes the CPU operations
and generates the GPU shader. The only mathematical mapping outside OCIO prepares
the existing relative RGB balance/display exposure parameters; there is no custom
per-pixel tone, matrix, saturation or interpolation evaluator in the probe.

The optional `baked` CPU mode generates 4097 samples of the official tone
processor after the preceding bounded Range op, then uses OCIO's own
`Lut1DTransform` to evaluate the result. The GPU path remains the direct generated
tone code. This is a measured approximation; it is not an exact analytic CPU
tone evaluation.

## Reproduce

Build official **OpenColorIO 2.4.2**, with applications, Python and tests disabled,
into a private install prefix. The release archive used here was
`https://codeload.github.com/AcademySoftwareFoundation/OpenColorIO/tar.gz/refs/tags/v2.4.2`,
SHA-256 `2d8f2c47c40476d6e8cea9d878f6601d04f6d5642b47018eaafa9e9f833f3690`.
Use the official source's build instructions and retain its license/dependency
notices. This probe finds the exact version via CMake:

```sh
cmake -S tests/ocio-runtime -B /path/to/probe-build \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/path/to/ocio-install
cmake --build /path/to/probe-build
python tests/ocio-runtime/check_probe.py /path/to/probe-build/ocio_probe \
  /path/to/qt/bin/qsb /path/to/qt/bin/qml /path/to/results
```

The Python reference requires `opencolorio==2.4.2`, NumPy and Pillow. The GPU
check is Mac-specific and requires actual Metal, rather than a software fallback.
QSB compilation also generates GLSL, HLSL SM5 and MSL variants; compilation
does not prove execution on Windows.

On this Mac, the bundled old zlib source failed with the current Xcode SDK.
The successful development build used the SDK's system zlib and the already
installed Imath, with missing dependencies built by OCIO. CMake 4 required
`CMAKE_POLICY_VERSION_MINIMUM=3.5` for older external dependency projects.
No upstream processing source was edited. This is a local development dependency
closure, not a portable dependency recipe or finished security/license audit.

## Probe scope

- Compare neutral, each slider's extremes/fractional values and combined grades
  with the existing independent Python reference.
- Compare packed RGBA and padded planar RGBA; preserve alpha and padding.
- Generate a Qt preview shader from the same definition and compare actual
  Metal rendering with the official CPU result.
- Time processor application separately from file I/O and parameter preparation.

Current limitations: no full-application preview plumbing, slider-update shader
cache, selected-camera LUT integration, decoder/encoder integration, persistent
projects, concurrency acceptance, Windows execution or portable package proof.
See [integration boundaries](../../docs/OPENCOLORIO-INTEGRATION.md). The working
application path remains in place until those checks pass.

## Isolated production C ABI checks

`bridge_check.cpp` compiles the actual production `bridge.cpp` separately from
Cargo. Run from the repository root, using the pinned OCIO 2.4.2 prefix and the
same FFmpeg development library as the application. Example for macOS:

```sh
clang++ -std=c++17 -O2 \
  -I/path/to/ocio-install/include -I/path/to/ffmpeg/include \
  tests/ocio-runtime/bridge_check.cpp src/rendering/ocio/bridge.cpp \
  -L/path/to/ocio-install/lib -L/path/to/ffmpeg/lib \
  -lOpenColorIO -lavutil \
  -Wl,-rpath,/path/to/ocio-install/lib \
  -Wl,-rpath,/path/to/ffmpeg/lib \
  -o /tmp/gyroflow-ocio-bridge-check
/tmp/gyroflow-ocio-bridge-check
```

This compares 800 concurrent calls sharing one immutable processor with serial
output, exercises unequal RGB plane strides, neutral behavior, prefix/suffix
and row-padding guards, invalid parameters and bounded error/shader output.
It also proves that FFmpeg may retain a valid negative stride after
`av_frame_make_writable`; the production Rust adapter must validate signed
linesizes before calling FFmpeg wrappers that expose plane slices.

These checks do **not** exercise the Rust frame/AVBuffer validator, Rayon band
splitting, alpha plane sharing, a real decoder/encoder, the Qt preview, Windows
execution or package dependency closure. The application fixture and native
acceptance need to cover those separately. No malicious pointers are passed to
the C ABI; its image pointers/ownership are caller preconditions enforced by the
Rust adapter.

The fixture also constructs bounded, non-neutral `.cube` tables with standard
0–1 input domains and both bounded and extended finite output values. It compares
the production combined processor with independent official tetrahedral
`FileTransform` followed by the grade, and proves a reversed-order negative
control differs. LUT-only behavior, packed alpha, missing/incomplete files and
processor use after removal of the loaded LUT file are checked.

Dense direct-versus-cached tone coverage uses **98 settings and 65,577 RGB
samples per setting**, including 16 subdivisions per baked LUT interval and
adjacent floating-point values at public VIDEO shadow/highlight starts, pivots
and midpoints. Each setting constructs a new production bridge snapshot and
compares it with a fresh official processor. On the development Mac, the maximum
analytic-versus-cached deviation was **5.37e-7**; the existing **1e-5** floating
point acceptance bound is enforced. This is still not native preview or an
encoded-video error measurement.

Keep an OCIO configuration's processor cache scoped to a single snapshot when
using these generated in-memory tone LUTs. In OCIO 2.4.2, the streamed transform
description used by `Config::getProcessor` omits complete `Lut1D` entry data.
Reusing one configuration across differently sampled LUTs of the same shape
may reuse an earlier processor. The production bridge creates a fresh
configuration per snapshot; future configuration sharing needs explicit cache
handling and a retained multi-setting regression check.

GPU resource extraction coverage makes **400 concurrent first-access shader and
texture queries** and compares the results with serial extraction. It checks
the official descriptor's texture ordering, the normalized sampler's binding,
RGB texture contents, null pointers, exact and insufficient capacities, copy
guards, and the no-LUT resource contract. This validates extraction and lazy
initialization only; native Qt upload, preview output and GPU execution still
need their separate application checks.

Cache-lifetime coverage removes a retained processor's LUT source, then applies
its CPU processor and performs its first lazy GPU extraction while another
thread constructs and destroys **64 fresh LUT snapshots**. Their constructor
clears OCIO's global filename caches. **16 missing/incomplete loads** are also
rejected and repaired at the same filename, proving that negative cache entries
do not prevent recovery. Retained CPU output, shader text and texture contents
must match the serial snapshot before, during and after those clears.
