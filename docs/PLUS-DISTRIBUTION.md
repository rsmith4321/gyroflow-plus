# GyroGrade desktop distribution foundation

GyroGrade is based on Gyroflow and maintained by Ryan Smith. It was called
Gyroflow Plus until 1.0.1, and it is not affiliated with the Gyroflow project. Original authors,
copyright headers, GPLv3 source license and third-party notices are retained.
New prototype source is GPL-3.0-or-later. OpenColorIO tone samples include its
BSD 3-clause copyright/license; see `resources/color/OCIO-LICENSE.txt`.

## FreeType acknowledgment

This software uses the FreeType font engine, including FreeType code in
MDK's `libass.dll`. For the FreeType 2.14.3 font-engine portion identified
in the Windows notice packet, GyroGrade elects the FreeType License
(FTL). The original license-selection document, FTL, alternate GPLv2 text
and separately licensed file notices remain intact. The acknowledgment
is retained in `mdk-0.39.0-e89bc0b/bundled/DISTRIBUTION-CREDITS.txt` in the
native notice tree and accompanies stages that include that tree. Other
dependency source-delivery and provider requirements remain open.

## Independent identities

| Surface | Fork identity |
| --- | --- |
| Application/UI | GyroGrade wordmark; subtitle “Stabilize · Color correct · Export”; “Based on Gyroflow” credit in the sidebar, documentation and notices |
| Application version | `1.0.1` (window title “GyroGrade 1.0.1”); upstream core retains its own version |
| Mac bundle | `com.ryansmith.gyrograde`, `GyroGrade.app` |
| Windows portable executable | `GyroGrade` directory; executable keeps `Gyroflow.exe` for the embedded MDK key |
| Settings | `GyroGrade` user-data directory; on first launch it copies `settings.json` and `lens_profiles` from a `Gyroflow Plus` directory beside it, once. `GYROGRADE_DATA_DIR` (or the older `GYROFLOW_PLUS_DATA_DIR`) selects another profile |
| Update API/download | `rsmith4321/gyrograde`, stable `plus-v<semver>` tags only (the prefix is kept so 1.0 installs find updates) |
| Project format | Compatible `.gyroflow`, no default-handler takeover |

Official settings and the earlier LUT Preview settings are not automatically
copied. Import an existing project or chosen preset explicitly. Mac staging
imports the official project UTI and uses handler rank None. Windows staging
is portable and writes no association registry entries. The internal Mac binary
and Rust package name remain `gyroflow` to retain existing build integration;
the installed bundle, product version, settings and updater identities differ.

Inherited release/Store/WinGet automation is guarded to run only in upstream's
repository. This fork must never publish under upstream package IDs or signing
credentials. This prototype does not provide a public packaged release.

## Build and stage

Build with the checked-in Cargo locks. Current dependency recipes are in
`_scripts/common.just`, `macos.just` and `windows.just`. Windows pins the existing
FFmpeg archive/version/SHA256 and Qt version. Record the exact compiler, Qt,
FFmpeg, OpenCV and MDK versions, source revisions and dependency license texts
with each packaged artifact. Source/build reproducibility is the goal; bitwise
reproducible binaries across arbitrary compilers are not established.

The inherited desktop dependency/deploy recipes are a starting point for
preparing a runtime with Qt, QML, FFmpeg, OpenCV, MDK and codecs. On Mac the
recipe needs an explicit target (`just deploy local` or `just deploy universal`);
on Windows it is `just deploy`. Do not use upstream Store/bundle signing recipes
or credentials. These portable recipe paths have not been accepted for this
prototype. Once a runtime is prepared and audited, stage it under the fork identity:

```sh
# After committing source, run in the prepared Mac dependency environment.
# Cargo reports the exact executable path in _dev/mac-build.json.
python3 _scripts/build_plus.py --no-default-features \
  --features opencv,ocio-runtime,ffmpeg-next/static --output _dev/mac-build.json
python3 _scripts/package_plus.py mac path/to/prepared/Gyroflow.app path/to/new-stage \
  --binary _dev/mac-build.json.target/deploy/gyroflow --deploy-receipt _dev/mac-build.json \
  --licenses path/to/dependency-notices
```

## Mac runtime library paths

For a prepared portable bundle, set `OCIO_RPATH=@loader_path/../Frameworks`
before building. `OCIO_ROOT` still selects the pinned headers and link library;
the override changes only where the executable searches at runtime. Without
the override, development builds retain the install prefix as their runtime
path. Windows does not use this ELF/Mach-O setting.

The prepared linker flags must also use bundle-relative Qt/MDK runtime paths,
such as `-Wl,-rpath,@loader_path/../Frameworks`, rather than absolute SDK or
development-prefix paths. Link-search paths may still point at the prepared
build dependencies. The package auditor rejects external runtime paths and
checks the full bundled dependency closure; this option alone is not portable
package or older-OS acceptance.

The Mac stage report separates absent weak library lookups
(`optional_weak_missing`) and nonexistent search directories contained in the
bundle (`absent_contained_search_paths`) from required dependency failures.
Present weak libraries still undergo architecture, deployment-floor and
transitive-load checks. External paths, missing required libraries and obsolete
framework dependencies remain release refusals. These diagnostics describe
loader inputs; they do not prove that optional codecs or camera SDKs work.

## Lens profile build input

Portable builds explicitly select the tracked `src/core/lens_profiles.pin`: official lens-profile release v41, asset SHA256 `5b9136697b75ddf9cda20965f17e786b6c8530e3d59109f87505069602e7f676`. The Mac receipt helper defaults to this pinned mode. For Windows deploy, set `$Env:GYROFLOW_LENS_PROFILES = 'pinned'` before running the recipe. An existing different database is refused without replacement; use a fresh isolated build tree instead of modifying an authored/development database.

Stages include the exact upstream v41 CC0-1.0 license and asset attribution in
`Notices/lens-profiles-v41/`. Its source commit and hashes are recorded in
`resources/lens-profiles-v41/README.md`. Review that notice when changing the
database pin. Development stages can contain another database; their staged
identity is recorded separately in `Notices/BUILD.json`.

For an offline build, supply the matching file with `--lens-profiles-file path/to/profiles.cbor.gz` to the Mac helper and use `--offline`. Direct Cargo/Windows builds use `GYROFLOW_LENS_PROFILES_FILE` plus `GYROFLOW_BUILD_OFFLINE=1` (or `CARGO_NET_OFFLINE=true`). Cargo's command-line `--offline` alone does not inform the HTTP build script; the helper explicitly forwards it. A missing or digest-mismatched pinned input fails the build.

Fresh publication uses a uniquely owned sibling file, bounded transfer and gzip decoding, then an atomic hard link that cannot replace an existing destination. A concurrent matching pinned file is reused; a different one is preserved and refused. Only this invocation's partial file is removed. In pinned mode, filesystems without hard links fail closed, including common exFAT/ReFS configurations: the supplied-file option also uses this publication path. Use a supported build volume or prepopulate the matching database in a fresh isolated tree. Ordinary latest mode can continue without the optional database after a warning. Gzip integrity is checked; CBOR semantics and runtime lens updates are separate.

The build/deploy receipt records the database identity. Portable staging requires the staged database hash to match both the receipt and tracked pin, and records the facts in its manifests. Ordinary direct Cargo builds retain the latest/reuse mode, the Mac helper has an explicit `--lens-profiles latest` development option, and the app's existing runtime updater is unchanged. This pins one build input; it does not establish reproducibility or close the other public-release gates.

The Mac helper runs a locked Cargo build, selects this package's executable from
Cargo's artifact report and records its SHA256 only if source stays clean at the
same commit. Each invocation uses a fresh, exclusively owned Cargo target
directory beside the receipt (`<receipt-name>.target`); it never reuses or
overwrites another build's target directory. Keep that directory exclusive until
staging completes. `--target` and `--profile` support explicit single-architecture builds;
use the reported executable path when it differs from the example. It does not
prepare or modify the runtime bundle. A combined universal executable needs a
separate controlled build-and-combine receipt; the single-target helper does not
attest a later `lipo` output. Build receipts are local provenance, not signatures
or proof that dependency/toolchain inputs meet the remaining release gates.

For the selected Windows OCIO candidate, compilation uses the explicit feature
selection below, after preparing and verifying the native dependency environment
(including `OCIO_ROOT` and `MDK_SDK`):

```powershell
cargo build --locked --profile deploy --target x86_64-pc-windows-msvc `
  --no-default-features --features opencv,ocio-runtime --jobs 2
```

This compilation command does not create a prepared runtime or its deploy
receipt. The existing `just deploy` recipe enables Cargo defaults and does not
pass through `--no-default-features`; it is not the reproduction path for the
accepted candidate. Keep its deployment tooling separate until that pass-through
has been implemented and tested on Windows. Current private validation uses an
independently recorded build/stage plan; see the
[current Windows preflight](OPENCOLORIO-INTEGRATION.md#current-windows-application-preflight).

Once a matching runtime and verified build/deploy receipt have been prepared,
the staging command is:

```powershell
python -m pip install --require-hashes -r _scripts/requirements-package.txt
python _scripts/package_plus.py windows _deployment/_binaries/win64 path/to/new-stage `
  --binary target/x86_64-pc-windows-msvc/deploy/gyroflow.exe `
  --deploy-receipt _deployment/_binaries/win64-deploy.json `
  --msvc-redist-floor 14.44.35211.0 `
  --licenses path/to/dependency-notices `
  --native-notices-sha256 72a5beebbca38b76ae810fee11575bb14b64f1f3dc07813dd65bf3f4cbdb9f7e
```

`--native-notices-sha256` pins the reviewed native notice tree, which must be
inside the `--licenses` directory. Staging fails unless exactly one
`MANIFEST.json` there has that hash and its integrity check passes.
`BUILD.json` and `PACKAGE.json` record the manifest hash and path, the
integrity result and the `--require-release-complete` result. That result stays
3 while the recorded release gaps remain.

Corresponding source is delivered as bundles beside the package, not as a
written offer. Add `--source-bundle NAME=PATH` for each of `qt`, `libass`,
`ffmpeg` and `mdk-ffmpeg9`. Each bundle is copied to the stage's `Source`
folder. The Qt bundle and libass source kit must match the identities recorded
in the reviewed notice tree (`qt-6.7.3/source-bundle.sha256` and
`LIBASS-SOURCE-QUALIFICATION.json`); a mismatch stops staging. The receipts
record each bundle's hash. Delivery is recorded as `beside-package` only when
all four are present; otherwise it stays `open`. The FFmpeg and MDK FFmpeg
bundles have not been assembled yet. Recording a bundle does not approve a
public release.

The floor above is an example; replace it with the full FileVersion required by
the newest toolset used to build the app, OCIO, Qt and OpenCV. Run deploy in a
Visual Studio developer environment. It copies one runtime set from
`VCToolsRedistDir` and writes a build receipt only after all required copies and
archiving succeed. Move prior runtime, receipt and ZIP outputs before deploying.

Derive that minimum from the recorded toolset and its corresponding Microsoft
redistributable, not by changing `19` to `14` in `cl.exe`'s FileVersion: the
compiler, toolset-directory and redistributable build numbers can differ. Keep
the explicit full-version comparison; a wrongly supplied minimum must be
corrected from provenance, rather than silently ignored by the audit. See
[Microsoft's DLL redistribution guidance](https://learn.microsoft.com/en-us/cpp/windows/determining-which-dlls-to-redistribute).

The import audit distinguishes Windows components from app dependencies. It
recognizes the in-box AVICAP32, BCryptPrimitives, DirectSound, ImageHlp and legacy
MSVCRT libraries; staging those system DLLs is rejected. This does not accept
missing `vcruntime140`/`msvcp140` redistributables or verify the symbols supplied
by an arbitrary Windows version. Those still need the native runtime gate.
[BCryptPrimitives requirements](https://learn.microsoft.com/en-us/windows/win32/seccng/processprng),
[AVICAP32 requirements](https://learn.microsoft.com/en-us/windows/win32/api/vfw/nf-vfw-capgetdriverdescriptiona),
[ImageHlp requirements](https://learn.microsoft.com/en-us/windows/win32/api/imagehlp/nf-imagehlp-mapfileandchecksuma).

The Windows audit also rejects known Microsoft debug runtime DLLs in any staged
directory, required or delayed imports of them, and export forwarders to them.
Resolving their symbols does not make them release redistributables. Release
runtime names and ordinary application DLLs with "debug" in their names remain
allowed by this rule. See Microsoft's
[DLL redistribution guidance](https://learn.microsoft.com/en-us/cpp/windows/determining-which-dlls-to-redistribute).

The stager requires a clean source checkout for every candidate and a matching
build/deploy receipt for portable stages on both platforms. It checks the receipt's
commit, clean-source flag and executable SHA256 before creating the output and
retains its bytes as `Notices/BUILD-INPUT.json`. It preserves
the runtime's dependency notices, adds GPL/OCIO/fork and pinned qmetaobject derive
notices, corresponding app source archive, source URL, input-build binary SHA256 and commit manifest, and refuses an
existing output. Mac auditing rejects absolute non-system dependencies. Windows
auditing (on Windows) rejects unresolved imports or symbols, stale library
versions and an incoherent or too-old C++ runtime; it is not a run on a clean
machine. Windows `qt.conf` points `QmlImports` at the deployed `qml` directory;
Qt plugins remain relative to the application directory. Static import auditing
does not prove that QML modules load, so packaged interface startup is also a
runtime gate. It
ad-hoc signs local Mac stages; that does not establish Developer ID signing,
notarization, Windows trust or public-release readiness. Supplying notices does
not establish that every dependency's license/source obligations are satisfied;
that audit remains a release gate.

For a local development build, `--development-runtime` explicitly permits the
prepared runtime's machine dependencies and records them. Such builds may rely
on Homebrew and are not advertised as portable downloads. Staging does not
install, publish, register Windows project associations or create a GitHub release.
Commit newly added files and other source changes before staging development
builds too. This keeps the accompanying source archive complete without copying
untracked private files into a package.

Development staging may omit the build receipt. In that case `source_commit`
and the build manifest's `commit`/`source` are null, `binary_source_verified` is
false, and the Mac bundle has no `GyroGradeSourceCommit`. The separately named
`checkout_commit` and `GyroGradeCheckoutCommit` identify the accompanying
checkout archive, which is not evidence that an unverified binary came from it.
If a receipt is supplied for a development stage, it must pass the same identity
checks. This prevents a stale executable from being labeled with a newer commit.

## Public-release gates

- Latest native brightness/contrast and new tone controls tested in the full
  Windows application, including D3D preview, real moving footage and encoding.
- Portable Mac/Windows runtime dependency closure, license/corresponding-source
  audit, clean-machine install/uninstall and coexistence checks.
- Reproducible build inputs and dependency source/build manifests; signed and
  notarized Mac package as appropriate and ordinary Windows trust checks.
- Project/preset/queue compatibility, native UI and frame/alpha/color references.
- Own tagged release (`plus-v...`) with matching source and acknowledgments;
  final working name/icon approval before a public product launch.

The focused upstream LUT PR remains on `codex/export-lut` and contains neither
this branding nor these additional tone controls.

`Notices/BUILD.json` records `input_binary_sha256` for the pre-signing build
input. `PACKAGE.json`, beside the app, records the final
`packaged_binary_sha256` after signing. These can differ for a Mac Mach-O file;
the final receipt stays outside the signed bundle to avoid a circular resource
hash. Older stages used the ambiguous `binary_sha256` field for the input hash.


## Retained Qt derive source

The root app uses the `qmetaobject_impl` source retained under
`vendor/qmetaobject-rs/`, from upstream revision
`ff1e23dcdd722a0c335bbd51f7dcfdb722384db2`. Only the signal-field offset expression
changes: Rust's standard `offset_of!` replaces a null-reference calculation.
The version and every other dependency package identity stay pinned. See that
directory's `UPSTREAM.json` and `PATCHES.md` for exact hashes and scope.

Both platform stages add the original MIT license, pin and patch description to
`Notices/qmetaobject-rs/`; the committed source archive contains the complete
retained crate with its original source headers. This is a downstream correction,
not a new upstream release. Mac app tests and notice-copy tests do not establish
Windows execution or portable-package readiness. The later
[private Windows acceptance](OCIO-WINDOWS-ACCEPTANCE.md) records a current build,
hardware CLI export and complete notice assembly while keeping native preview
and public-release requirements open.

## Retained FFmpeg binding source

The root app uses the published `ffmpeg-sys-next` 9.0.0 crate under
`vendor/ffmpeg-sys-next-9.0.0/`. The exact package SHA-256 is
`9b939bf79dd5949412a4b81cfe21a07f48ea21b47fcbb5f57816c8c2de5ae30b`;
its upstream source is `80b7dd8327c3539159f37d8ca5423c75d6cd2e57`.
Only the two obsolete macOS static framework requests for QTKit and
VideoDecodeAcceleration are removed. FFmpeg source, bindings, all remaining
link requests and non-macOS/dynamic paths are unchanged. The root lock removes
only this package's registry source/checksum; other package records are exact.

Both platform stages copy the original README and manifest license declaration,
package provenance and exact patch to `Notices/ffmpeg-sys-next/`. The source
archive contains the retained crate. Portable Mac audits reject either obsolete
framework load even when it appears under an Apple system path. This does not
replace FFmpeg's own notices, corresponding source or codec-rights checks.
Use `_scripts/verify_vendored_ffmpeg_sys.py` with the pinned published `.crate`
to verify every retained file against the original package plus patch.
