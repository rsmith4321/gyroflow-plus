# Native OCIO preview acceptance

This standalone synthetic fixture compiles the exact production Qt preview adapter,
fragment wrapper, and pinned OCIO bridge. It renders through `QQuickRenderControl`
without opening the user application or reading/writing application preferences.
The renderer must actually be Metal on macOS or D3D11 on Windows; a silent software
fallback fails the pixel test. Input, 3D LUT storage, render target, and readback use
float32. The shader pack contains the official OCIO GPU operations, with no test
replacement color evaluator.

## Coverage

- Gray/channel ramps, primaries, exact endpoints, and input values outside 0–1.
- Neutral, all eight grade controls, identity/inverted/asymmetric nonlinear LUTs,
  and an optional locally owned official DJI O4 LUT, with and without grading.
- Seventy generated shader/native texture swaps crossing the 64 distinct URL
  cache threshold. Public `QQuickWindow::releaseResources()` bounds Qt's own GUI
  shader cache; the active shader/data remain leased through this purge.
- The same active source and LUT after public cache release and actual scenegraph
  invalidation/reinitialization, without replacing their binding to mask failure.
- Stale token disposal, invalid edge 129 rejection, live owner reuse after LRU
  eviction, unique filenames after regeneration, and stale/current native errors.
- A separate `--exception-check` process deliberately fails shader compilation
  while the cache mutex is owned, then prepares a valid shader in the same process.
  CTest limits it to 30 seconds, so a mutex left locked by broken C++ unwinding
  fails rather than waiting indefinitely. This checks recovery through the exact
  adapter; Cargo's MSVC compiler commands must also show `/EHsc` explicitly.
- Separate process using the actual software renderer, verifying the factory
  rejects it with the visible hardware-renderer message and releases its token.
  The production QML bypasses the factory for neutral settings and disables the
  color layer, so a neutral preview remains available on software rendering.

The tolerance is 0.00001 (1e-5) per RGB/alpha component for this synthetic float32 path. The CPU bridge uses an official
OCIO sampled tone transform for speed while the GPU uses the exact official tone
shader. A native pixel match confirms this synthetic path; it does not establish
camera support, real decoder/stabilizer/encoder parity, native app visual behavior,
Windows execution, or portable distribution readiness by itself.

## macOS

With Qt 6.11.2 at `/opt/homebrew` and a pinned OCIO 2.4.2 install:

```sh
OCIO_ROOT="$PWD/_dev/ocio-runtime/install" \
  tests/ocio-preview/run-macos.sh "/absolute/path/to/official-o4.cube"
```

The LUT argument is optional. Set `QT_PREFIX`, `QT_VERSION`, and
`OCIO_PREVIEW_TEST_OUT` to use another matching Qt install/output directory.
Generated binaries and result JSON default to `_dev/ocio-runtime/native-preview`.
No LUT asset is redistributed by this fixture.

## CMake / Windows

Qt Core, Gui, Quick, Qml and ShaderTools development modules must come from the
same Qt version, with the matching private RHI headers. OCIO must be exactly 2.4.2.
Use the installed Qt/OCIO prefixes and their normal DLL search path on Windows.
For example, from a configured compiler environment:

```sh
cmake -S tests/ocio-preview -B _dev/native-preview-build \
  -DCMAKE_PREFIX_PATH="/path/to/qt;/path/to/pinned-ocio" \
  -DOCIO_PREVIEW_LUT_FILE="/absolute/path/to/official-o4.cube"
cmake --build _dev/native-preview-build --config Release
ctest --test-dir _dev/native-preview-build -C Release --output-on-failure
```

The CMake configure/build has also been verified on Homebrew macOS using separate
`qtbase`, `qtdeclarative`, and `qtshadertools` prefixes. The normal private module
version warning is expected: use one matching Qt build, as the application does.

macOS execution has been verified with Qt 6.11.2, OCIO 2.4.2, and Metal / Apple M4
Max: 82 pixel comparisons, maximum absolute error 2.384185791015625e-7, both
resource recreation checks, shader ownership/error checks, and software rejection
passed. D3D11/Windows execution still requires a run on the laptop.
