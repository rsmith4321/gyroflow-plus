# Windows x64 native dependency notices (candidate)

Status: CANDIDATE for `resources/notices/native/windows-x64`. Not a legal review and
not a release approval (`public_release_approved: false`).

The original v5 snapshot added exact installed-provider facts to the accepted v4 tree. Every v4
file is kept byte for byte except this README and the per-component PROVENANCE.json
files. Notice texts are verbatim copies of official upstream files at exact pins, or
of original installed provider files. `.gitattributes` keeps those bytes unchanged.

Later additions retain MDK bundled notices, the FreeType license choice and
acknowledgment, and the byte-matched OpenCL SDK provider's copyright and metadata.
The current `427a6ca4` private Windows stage has the same 120 DLL identities as
the frozen inventory, except that the seven FFmpeg entries now record the slim
Gyroflow+ FFmpeg archive (`docs/WINDOWS-FFMPEG-SLIM.md`) that the current pin
builds with. Seven blocking requirements remain; consult the manifest for the
current component records. A copied notice tree does not close them.

`MANIFEST.json` lists:
- every file with its size and SHA-256
- all 120 staged DLLs from the frozen stage inventory, each assigned to one component
  with the basis for that assignment
- every open gap with a class: `blocker`, `obligation` or `advisory`, plus the gaps
  v5 closed (`resolved` or `duplicate`)

`verify_native_notices.py` (delivered beside this candidate) checks integrity
separately from these gap classes.

## Components

| Directory | Component | Notice text here |
|---|---|---|
| `qt-6.7.3/` | Qt 6.7.3: 30 DLLs and 49 plugins | Module licences and 46 third-party attributions at tag v6.7.3 |
| `ffmpeg/` | FFmpeg n9.0.2, slim Gyroflow+ build of BtbN's scripts: 7 DLLs | FFmpeg, BtbN, all 27 build components, the 65 Rust crates rav1e links and the toolchain runtimes |
| `opencv-4.14.0/` | OpenCV 4.14.0: 12 DLLs | The provider's `COPYRIGHT.txt`, identical to the repository copy |
| `ocio-2.4.2/` | OpenColorIO_2_4.dll | None here. The tracked `resources/color` notices are staged by `package_plus.py` |
| `rust-windows-x64-ocio/` | Gyroflow's Rust crates | None here. Include the tracked `resources/notices/rust/windows-x64-ocio` in the same `--licenses` input |
| `msvc-crt-14.51.36247.0/` | Microsoft C/C++ runtime: 10 DLLs | None. The installed `Redist.txt` is kept as provenance |
| `mdk-0.39.0-e89bc0b/` | MDK 0.39.0 git e89bc0b, plus its bundled `ffmpeg-9.dll` and `libass.dll` | Original SDK `README.md`, bundled dependency notices and FreeType acknowledgment |
| `d3dcompiler_47/` | D3Dcompiler_47.dll 6.3.9600.16384 | None. Windows SDK 10.0.26100.0 terms are kept as provenance only, because they cover a different copy |
| `zlib-for-z.dll/` | zlib 1.3.2#2 (z.dll) | The upstream v1.3.2 `LICENSE`, which is byte-identical to the installed `copyright` |
| `opencl/` | OpenCL SDK 2024.10.24#1 loader and utilities: 3 DLLs | Exact installed provider copyright: Apache-2.0 and the whereami MIT alternative |
| `unattributed/` | opengl32sw.dll, byte-matched to Qt 6.7.3 and its published Mesa 11.2.2 / LLVM 3.6.2 reference | Verbatim version-matched Mesa/LLVM notices and older Qt-published attributions; additional Gallium/Unicode notices and regex documentation credits; complete binary copyright-holder coverage remains open |

**shaderc** is omitted. No `shaderc*.dll` is in the accepted stage.

## Limits

- Identities come from the owner's frozen stage inventory (`f7f930f4...`) and the
  facts supplied with it. The pinned FFmpeg archive and the official MDK archive
  are used for byte comparison only.
- A component's directory does not prove the shipped binaries were built from the
  cited sources. Each PROVENANCE.json says what was compared.
- Original incomplete `opencl/PROVENANCE.json` and `unattributed/PROVENANCE.json`
  are retained as historical records. Their `CURRENT-PROVIDER.json` files record
  the later byte comparisons and their remaining limits. The additive software
  OpenGL `REFERENCE-ATTRIBUTION.json` records an exact published Qt archive/DLL
  match and static Mesa/LLVM version strings. `NOTICE-SOURCES.json` records the
  accepted version-matched text review and remaining binary coverage gap.
  `ACKNOWLEDGMENTS.txt` retains the supplementary regex documentation credits.
  `unattributed/source-artifacts.json` and `source-bundle.sha256` identify the
  original version-matched upstream archives retained with an unpublished
  source-only GitHub draft. They do not establish the Qt build/patch source.
  These records preserve the notice/source gap;
  the earlier unknown-version snapshots remain unchanged.
- Corresponding-source routes, acceptance of the MDK and Microsoft terms, and codec
  policy are decisions for root and the owner.

## AMD AMF header notices

The AMF 1.5.2 tag LICENSE and verbatim preambles from all 57 released headers
are retained with source and excerpt hashes. Public Actions logs identify AMF_VER
1.5.2. The matching FFmpeg artifact has equal defined section payloads; its raw
DLL differs from MDK in one PE size field and padding beyond the code section
VirtualSize. `mdk-0.39.0-e89bc0b/bundled/evidence/ACTIONS-BUILD-CONTENT.json` records this limited
comparison for FFmpeg and libass. No raw binary identity or complete corresponding
source is inferred from it. Only the missing AMF notice gap is closed.

## libva header notices

All 28 libva 1.19.0 headers in the retained historical dependency artifact match
Microsoft.Direct3D.VideoAccelerationCompatibilityPack 1.0.2 byte for byte. The
17 distinct header license blocks and full package NOTICE are retained, with
package License and nuspec recorded as provenance. The historical dependency
download is supported by workflow timing and archive size; its original checksum
is absent from the FFmpeg log. This closes the missing header-notice text, while
the download-identity advisory and broader source obligations remain open.

## Software OpenGL source notice inventory

The v10 review adds a conservative superset of 668 version-matched source
attribution excerpts, with 23 build-input and six flagged contexts retained as
provenance. All 697 excerpts and the declared source accounting were independently
checked against the official Mesa and LLVM archives. Files use content hashes to
keep Windows paths short; source paths, byte/line ranges and the canonical mapping
are in `unattributed/SOURCE-HEADER-DELTA-v10.json` and
`unattributed/SOURCE-COVERAGE-REVIEW-v10.json`. These records preserve the unknown
Qt patch/build/linkage and source-license limits. The provider blocker remains.

## Bundled FFmpeg patch-stage source

`mdk-0.39.0-e89bc0b/bundled/evidence/FFMPEG-PATCH-STAGE.json` indexes a
retained source-only archive after the 40 ordered patch attempts. Two installed
Apple patch runs and an independent replay of 169 vendor-recorded hunk outcomes
agree for all 10,714 source files. The independent replay retains exact EOF
markers and rejects/skip outcomes; tool diagnostic positions alone were not
treated as equivalent. Backup/reject files are excluded from the source archive.
Later conditional patches, sed edits, configuration, generated files, dependency
closure and complete corresponding-source delivery remain open. The source-only
draft remains unpublished and the eight distribution requirements are unchanged.

## Bundled libass source inputs and Unicode data

`mdk-0.39.0-e89bc0b/bundled/evidence/LIBASS-BUILD-INPUTS.json` records
the successful vendor job's exact checkout pins and x64 link to static FriBidi,
FreeType and HarfBuzz. It includes seven logged FriBidi generation commands and
the identities of their five Unicode 18.0.0 inputs. The original UCD ReadMe and
full Unicode License V3 are retained alongside the FriBidi LGPL notice.

The previously missing FreeType `subprojects/dlg` source matches all 28 upstream
Git blobs and is retained in the existing unpublished source-only draft. Its
Boost license and header notice are included as a conservative source superset;
this does not assert that dlg code is linked. Vendor build pins are directly
logged, but raw shipped DLL identity remains limited by PE header/padding
differences. These input-collection records are historical. The later hosted
archive-source build and relink qualification is recorded separately below.
Public corresponding-source delivery remains open; the eight distribution
requirements are unchanged.

## Supplementary libass configure inputs

`LIBASS-OFFLINE-CONFIGURE-INPUTS.json` records the logged Snappy and GLFW
checkout pins reached by devpkgs's top-level configuration. Their source
archives are retained in the same unpublished draft. All 218 regular Git blobs
match, including six GLFW files restored from exact Git blobs after the official
archive omitted them through `export-ignore`. Snappy's two test gitlinks are
listed and omitted; the original parent build disables tests and benchmarks.
This does not assert that Snappy or GLFW is linked into libass, or establish a
full recursive Snappy source snapshot. The top-level configuration also reaches
other projects. The later archive-source qualification below covers the retained
build recipe; complete public source delivery remains open.

## Later libass source-build qualification

`mdk-0.39.0-e89bc0b/bundled/evidence/LIBASS-SOURCE-QUALIFICATION.json`
records successful hosted run `38017550683` at source `4dd7582a`. It used 12
retained source archives, built libass with seven assembly objects, checked seven
FriBidi generated-output hashes against the earlier source qualification, and
relinked from 34 libass objects and the recorded static libraries. Both candidate
DLLs exported the expected 50 symbols. Their hashes differ; neither candidate
replaces or is shown to match the shipped vendor DLL.

The reviewed source kit at `6f17b323` retains those archives, the build recipe,
original license texts and the hosted text evidence on an unpublished draft.
The runner had network access. Independent acceptance checked logs and runner
assertions; binary products and generated-table bytes were not transferred for
independent rehashing. Public delivery alongside the package and remaining
corresponding-source/provider checks are still open. This qualification changes
no app binary, runtime default, Windows GUI acceptance or release approval.

## Bundled FFmpeg later source edits

`FFMPEG-LATER-EDITS.json` qualifies deterministic edits after the ordered
patch stage. The retained full vendor log proves that the initial NVIDIA
header gitlink was replaced by `eddcea9e`; five optional-symbol substitutions
and the two `mfplat` spellings are retained as independently reconstructed
data-only diffs. The partial-availability deletion is a no-op for this source.

Packaged x64 configuration text and all seven pkg-config prefixes are hashed
as supporting evidence. Final source line endings, concurrent insertion counts,
generated configuration and full dependency/rebuild delivery remain open.
These source candidates do not reproduce or replace a DLL. All eight
distribution requirements remain unchanged; no public release is approved.

The independent later-edit follow-up verifies five header substitutions and
qualifies all 20 sed conditions against the retained source, full vendor log and
packaged SDK text (7 proved, 13 contradicted). The five conditional patches
remain contradicted. The successful x64 configure branch supports the
`ffmpeg.c` insertion condition, while final insertion counts, line endings and
`config.mak` bytes remain unknown. This adds source provenance evidence; it does
not close any of the eight release requirements.
