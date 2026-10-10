# Rust dependency notices

## Windows native notice snapshot

The reviewed native snapshot is in
[`resources/notices/native/windows-x64`](../../resources/notices/native/windows-x64).
Its manifest describes the frozen `ab680a27` Windows stage: 120 DLL identities,
verbatim notice texts, provider provenance and explicit remaining gaps. A new
stage must be compared with those identities before reusing the snapshot.

Check content and the 25 reused repository files with the offline standard-library
verifier:

```sh
python3 -I _scripts/notices/verify_native_notices.py \
  resources/notices/native/windows-x64 --repo-root . \
  --manifest-sha256 72a5beebbca38b76ae810fee11575bb14b64f1f3dc07813dd65bf3f4cbdb9f7e
```

The Qt GPL-2.0-or-later alias is retained as the full upstream target text,
rather than the literal Git symbolic-link target name. Content integrity currently passes. Add `--require-release-complete` to check the
recorded release gaps; it currently returns **3**, because eight blockers or
obligations remain. A normal integrity exit of zero is not distribution approval.
The manifest pin prevents an edited gap classification from silently passing.

For a Windows package, combine the reviewed native tree and the matching Rust
notice output in the prepared directory supplied to `package_plus.py --licenses`.
That option copies the supplied tree; the native snapshot alone does not contain
the Rust notice output. The packager also retains the tracked OpenColorIO notices.
Keep corresponding-source and provider-term records with the release evidence;
this snapshot does not establish license compatibility or satisfy those open
obligations by itself.

## MDK bundled dependency notices

The MDK snapshot includes 23 original notice texts for the bundled FFmpeg and
libass dependencies, plus their source and binary provenance. Seventeen are full
upstream files and six are license comment excerpts with recorded line ranges.
`mdk-0.39.0-e89bc0b/bundled/evidence/NOTICE-SOURCES.json` records each upstream
repository, commit, path, blob identity and whether the DLL build pin is exact
or inferred. All 23 delivered texts were independently compared with those
upstream commits.

An embedded library version does not establish an exact source commit. The
HarfBuzz version is exact, while its source pin and other documented build pins
remain inferred in the historical provenance. The remaining MDK requirements
cover corresponding-source delivery; the historical libva download identity
remains an advisory. The FreeType credit/license choice and OpenCL notice gaps have since
been resolved with retained documentation and exact installed provider files.
Eight recorded blockers or obligations remain across the complete native tree.
AMF 1.5.2 now has its tag LICENSE and all 57 release-header preambles retained
with public Actions and limited binary section comparison evidence; the AMF
notice gap is resolved. Raw binary identity and broader source requirements remain
open. The software OpenGL component now retains version-matched Mesa/LLVM notices
and an older Qt-published attribution, with source and excerpt identities in
`unattributed/NOTICE-SOURCES.json`. The version-matched texts have been reviewed;
complete binary copyright-holder coverage remains
open, and the original provider gap remains blocking. Supplementary Gallium and
Unicode notices and explicit regex documentation credits are retained.
`unattributed/source-artifacts.json` indexes the retained original Mesa and LLVM
source archives and their unpublished source-only GitHub draft. The accompanying
`source-bundle.sha256` pins its archive, review record and extraction README.
These additions do not change the staged DLL inventory or establish complete
corresponding source.

## Qt source artifacts

The Qt snapshot records five official mirror archives in
`qt-6.7.3/source-artifacts.json`: four modules at verified `v6.7.3` commits and
the exact test262 submodule omitted from GitHub's module archives. All 86 selected
Qt notice files match these sources after resolving the upstream license alias.
`qt-6.7.3/source-bundle.sha256` identifies the prepared source bundle.

Keep `Qt-6.7.3-source-bundle.tar` with the release artifacts and deliver it with the
matching package. Its `SOURCE-README.txt` describes extraction into a new empty
directory, including the test-suite submodule placement. The large source archive
is a release artifact, not a Git source file. These retained sources do not close
the recorded source obligation until delivery and provider/build-provenance
checks are complete. No written source offer or release approval is implied.

## Rust collector

This is a release-preparation recipe, separate from application compilation.
It uses the official `cargo-about` 0.9.2 collector. The Python gate checks that
its output covers the selected Cargo graph and copies checksum-pinned extra
upstream notices. A successful gate does not establish license compatibility,
native-library coverage, complete corresponding source, or release approval.

## Supported collector environment

Run the shell collector on Linux with Bash 4.4 or newer, GNU `timeout`, Python 3,
Git, and the appropriate pinned Rust toolchain/cache. macOS's system Bash and
native Windows PowerShell are not supported runner environments. The resulting
notice files can accompany a Mac or Windows package after their receipt's commit,
target, manifest/lock hashes and feature selection are matched to the actual build.
The runner does not install tools or fetch dependencies. Provision the locked
cache separately before running it; all Cargo collection commands use `--frozen`.

Install the pinned collector in an explicitly chosen tool prefix:

```sh
cargo install cargo-about --version =0.9.2 --locked --features cli --jobs 2 --root "$tool_prefix"
```

The published crate archive SHA-256 is
`0cd19d99696eb83f0a2d6ab7a347b14968d2980416c8cca827ded220e6e9c4bb`.
The `cli` feature is required to install its executable. Place that prefix's `bin`
directory on PATH for collection; the runner checks the reported tool version.

From a clean checkout, with fresh output and work directories:

```sh
bash _scripts/notices/run_rust_notices.sh \
  --no-default-features --features opencv,ocio-runtime,ffmpeg-next/static \
  --absent breakpad-sys \
  "$checkout" "$checkout/_scripts/notices" "$output" "$work" aarch64-apple-darwin
```

For Windows x64, select `opencv,ocio-runtime` and `x86_64-pc-windows-msvc`.
The compile must use the same explicit `--no-default-features` selection. The
existing Windows `just deploy` recipe does not pass that flag; use a separately
reviewed Cargo build plan until its deploy pass-through is implemented and tested.
No Windows build is implied by generating its metadata on Linux.

Each Cargo step has a 300-second timeout by default (`STEP_TIMEOUT` overrides it).
Use an external overall time/output bound as well. Failed runs retain a `.partial`
directory for diagnosis and never rename it to the final output. JSON containing
local cache paths stays in the work directory, outside the shipped notice packet.

## Corresponding Rust source

`vendor_archive.py` makes a deterministic archive from an already populated
`cargo vendor --frozen --versioned-dirs` directory and its generated config.
See its header for invocation. Extract the two archives into this parent/child
layout, matching the source commit and dependency lock recorded by their receipts:

```text
source-bundle/
  .cargo/config.toml       # generated vendor source configuration
  cargo-vendor/            # dependency sources
  src/                    # Git source archive, unchanged
    .cargo/config.toml     # tracked target linker flags
    Cargo.toml
    Cargo.lock
```

Run Cargo from `source-bundle/src/`. Cargo merges the parent vendor-source config
with the repository's target config; the vendor directory resolves relative to
`source-bundle/`. **Never extract the vendor archive over the Git source tree:**
that would replace the tracked config and discard linker flags, including Mac
runtime search paths. This follows Cargo's [configuration hierarchy and relative
path rules](https://doc.rust-lang.org/cargo/reference/config.html).

The `cargo-vendor/` directory is separate from the repo's existing `vendor/` path
crates. Graph resolution with an empty Cargo cache and
`--frozen` is a source-availability check; it is not a successful application build.
Native dependencies and their source/build requirements remain separate.

## Provenance and verification limits

Integrated from the reviewed C2/C3 recipe at public application commit
`0b5ba007bfad303f88c143615a9d2baf384de4cb`. The frozen C3 manifest SHA-256 is
`2b549b1b00c39d620f04600a9b901ebe68889d42a659ddc62ff2561ae77334bc`.
The gate, config and supplements retain the reviewed bytes. The archive helper's
implementation is unchanged; its instructions now require the parent/child layout.
Integration adds an explicit runner environment check, replaces regex-based path
redaction with literal replacement, and corrects the template's overinclusive
"statically linked" label. Earlier C3 outputs retain their original receipt and
template hash; these small integration changes do not retroactively regenerate them.

Reviewed evidence includes refusal of empty/malformed graphs and blank license
text, preservation of Cargo failures, and current selected Mac/Windows graphs
with only `breakpad-sys` removed. The original independent gate checks are retained
in project continuity. The collector and complete app/package were not rerun by
this integration. Malformed supplement/metadata may fail with a traceback; such
failures are nonzero and must never be treated as a completed packet.

Remaining attribution decisions include the upstream objc2 and pulp licensing
statements, nalgebra 0.30.1's declaration/text discrepancy, and native libraries
outside Cargo's view. Keep full upstream texts and supplements; the gate's fallback
allow-list is a recorded review decision, not a general exemption from attribution.

The libva header notice gap is resolved by exact comparison of all 28 retained
historical headers with official NuGet package 1.0.2. All 17 distinct verbatim
header comments and the full package NOTICE are retained. Package License and
nuspec are provenance; original download identity remains explicitly unproven.

The MDK FFmpeg source recipe must preserve actual vendor patch outcomes:
35 master patches have no logged failures, while all five common patches have
skipped or failed hunks and the final time patch partially applies. The retained
MDK `bundled/evidence/FFMPEG-PATCH-OUTCOMES.json` records every patch identity
and log lines. It does not prove a reproduced DLL or close source delivery.

The software OpenGL v10 inventory retains all 668 attribution excerpts and
29 supplementary contexts after independent source-byte/range checks. The
original proposed paths map to shorter content-hash paths in the root review
record. This is a source superset, with parser, copyright-only, no-header and Qt
compiled-coverage limits retained; the provider blocker remains unchanged.

## Hosted libass source qualification

`native-libass-source.yml` is a manual-only, text-evidence workflow for this fork's
`codex/lut-preview-controls` branch. It checks the original pinned Windows x64
libass target with assembly enabled, its three static dependencies, seven
FriBidi generated outputs, exported symbols and a relink using unchanged objects.
It does not build or install Gyroflow+, upload binaries, or publish a release.

The Python runner uses twelve exact public Git commits, builds NASM 2.16.01 from
its official source, limits compilation to two jobs, and records commands, source
identities and tool hashes. The source work has a fifteen-minute budget and the
job has a twenty-minute timeout. Log caps are checked by polling; retained logs
are truncated if a cap is exceeded. The private developer environment capture
is excluded from artifacts. If Windows refuses to delete it because another
process still holds a handle (WinError 32), the runner attempts to truncate it,
records the disposition without contents or hash, and tries deletion once more
at the end of the run. Truncation can also be refused, and an inherited handle
can write later; the capture remains outside the uploaded evidence. Any other
deletion error fails the run.

The graph check retains the exact 34 object inputs, all seven x64 assembly
commands, LTCG/x64 flags and the three pinned static dependencies. Hosted run
38013124997 built NASM and libass successfully, then exposed one checker mismatch:
the checker counted three unique static dependencies without allowing the second
FreeType token. Both that hosted command and the original vendor log's x64 link
command (line 1630) contain `FriBidi, FreeType, HarfBuzz, FreeType`. The pinned HarfBuzz
`CMakeLists.txt` lines 611–612 explicitly link FreeType, and the vendor log also
compiles `hb-ft.cc` with `HAVE_FREETYPE=1` and archives it in HarfBuzz. The checker
admits the historical library multiset or exactly the observed ordered sequence
`FriBidi, FreeType, HarfBuzz, FreeType`; other repeats, missing libraries and
foreign/absolute project libraries remain refused. The literal link command must
also appear in the actual Ninja build log and is retained in `BUILD-PROOF.json`.
This qualifies the known dependency edge, not compiler or DLL identity.

NASM's original `Mkfiles/msvc.mak` uses constructs NMake and cmd do not accept
(hosted run 38010050723 stopped with U1005 at its line 238). The runner leaves
that pinned file byte-identical and, only when its SHA-256 matches, writes a
separate `Mkfiles/msvc.gyroflowplus-compat.mak` beside it. Fourteen lines change:
empty-search `$(WARNFILES:=.time)` becomes the three listed names, a nested
`$(O)` substitution is spelled `.obj`, POSIX `: >` and `@:` become `type nul >`
and `@rem`, an explicit-rule `$<` names `misc\emacstbl.pl`, and the three
recursive NMake calls name the derived file. The pinned Git snapshot lacks
`config/config.h.in`, which stopped hosted run 38011830481 with U1073 even
though its generated target `config/unconfig.h` is checked in. The derived
recipe therefore omits only that absent template prerequisite, retaining the
target and its recipe. Before writing the derived makefile or starting any build
command, the runner checks the exact sizes and SHA-256 values of the official
`config/unconfig.h` and `config/msvc.h`, and refuses an unexpected template or
symlinked header. It checks the headers again after the NASM build. No template
or header is fabricated, and no Autotools step is added. NASM sources, version,
flags and all other target prerequisites are unchanged. Any other original, context or construct
count is refused, and both `nmake /f` calls use the derived file. The original
and derived hashes, configuration-header identities and the exact unified diff
are saved in `NASM-MAKEFILE.json`.

The candidate passed 47 isolated standard-library mocked tests in Claude's v13
review. The targeted v14 cleanup regression suite reported 58 passing mocked
tests and one explicit missing-fixture skip. The v15 NASM recipe suite
reported 70 passing mocked tests and one explicit missing-fixture skip. Root's
v16 correction passed all 78 mocked tests with all source-text fixtures supplied,
including missing/changed/symlinked header refusal, unexpected template refusal,
refusal before any command or derived file write, and post-build header checks.
No upstream generators or compilers ran in these mocked tests. Root independently checked the
packet/output hashes, twelve source
archives, twenty-one quoted source ranges and exact patch replay. Those checks
do not establish that a Windows source build or relink works. Run the reusable
mocked tests from a checkout with:

```sh
python3 -I _scripts/notices/test_rebuild_libass_windows.py
```

Set `V13_LIBASS_SYM` to `libass/libass.sym` extracted as data from the pinned
`wang-bin/libass` source to include its optional fifty-symbol fixture. Without
that file, the corresponding fixture is explicitly skipped. Set
`V15_NASM_MAKEFILE` to the pinned NASM `Mkfiles/msvc.mak` to include the recipe
fixtures; without it, those fixtures are explicitly skipped. Set
`V16_NASM_CONFIG_DIR` to the pinned source's `config/` directory for the header
fixtures and successful recipe-preparation fixture; otherwise those checks are
explicitly skipped. The fixture files are read as data, never executed.
Set `V17_HOSTED_GRAPH` to the retained `command-094.log` from run 38013124997
for its hash-pinned actual graph fixture. With all four fixture variables set,
all 81 mocked tests pass, including exact repeated-FreeType acceptance and
rejection of other repeat counts or orders. These tests do not execute that graph.

Hosted run [38014071478](https://github.com/rsmith4321/gyroflow-plus/actions/runs/38014071478)
at source `aab1d5f5cd764a3be46ba7fe812a9acbdf4dac31` passed the actual
NASM generation/build, 187-step libass build, fifty exported symbols and a
single-step relink. Root checked all 73 nonempty public log hashes, 24 empty logs,
twelve source pins and literal build/link commands. The runner checked that all
181 retained object/static-library hashes survived the relink and recorded the
seven generated FriBidi output hashes. Those binaries/table bytes are not in the
text artifact and were not independently rehashed by root. This is an online
pinned-source build, not an offline reconstruction from a distributed source
bundle. See [the acceptance and remaining limits](../../docs/WINDOWS-LIBASS-SOURCE-ACCEPTANCE.md).

The hosted Visual Studio is discovered with
vswhere on each run and recorded with tool paths and hashes; hosted run
38008920591 reported `C:\Program Files\Microsoft Visual Studio\18\Enterprise`.
That path does not by itself establish a compiler version or show that the
toolchain matches the vendor's build. Shallow source checkouts also change
libass version metadata. No vendor-identical compiler, metadata or DLL, and no
complete corresponding-source claim follows. Native source and provider
requirements remain blocking until their separate evidence and delivery checks
pass.

### Retained source archives candidate

`native-libass-archives.yml` is a separate manual-only candidate workflow. It
downloads one retained source-only ZIP, then the same runner uses archive mode
(`GYROFLOWPLUS_LIBASS_SOURCE_MODE=archives`). The original workflow and default
Git acquisition remain unchanged. The build job retains read-only repository
permission. Hosted preflight run 38017447900 confirmed that a read-only token
cannot see the unpublished source draft. A separate fetch job therefore has
`contents: write` solely to read that draft: it has no checkout and executes no
acquired source. It verifies the ZIP size/hash and passes it as a one-day
artifact to the read-only build job. No personal token is supplied, and the
workflow contains no release upload, publication or repository write command.

`libass-source-archives.json` pins the ZIP and twelve original archive hashes,
sizes, paths, member counts, link identities and uncompressed sizes. ZIP entries
must be exactly the twelve stored archive files. Every archive passes before
source extraction starts. Extraction uses standard `tarfile` with its `data`
filter in fresh private staging directories, preserving original archive names
so Windows' standard link-copy fallback can resolve the known HarfBuzz
documentation link. Any fallback is checked and recorded. Source instructions
inside dependency archives are inert input data.

Archive mode rejects collisions, unsafe Windows paths, unexpected member types,
links, Git metadata and nonempty source destinations. It hashes all five Unicode
inputs before any compiler command. The same NASM/header, assembly, 34-object
link, exported-symbol and retained-object relink checks run afterward. All seven
FriBidi output hashes must match qualified Git-source run 38014071478.

Only archive mode adds CMake's standard
`CMAKE_DISABLE_FIND_PACKAGE_Git=TRUE`. The two retained `find_package(Git QUIET)`
sites are libass version metadata and the disabled dav1d project. This uses
libass's existing unknown-version fallback and prevents an enclosing repository
from supplying a false source version. No `.git` directory, vendor version or
generated header is fabricated.

Hosted run
[38017550683](https://github.com/rsmith4321/gyroflow-plus/actions/runs/38017550683)
at source `4dd7582a606ec39ba7e9385f58b4195085ae6a4b` passed with both jobs:

- The fetch job read the draft and passed the verified ZIP.
- The build job ran with `contents: read`.

This followed preflight run 38017447900, which failed because a read-only token
could not see the draft. Root fixed a review finding before acceptance.

Root's data-only inspector checked the 28 text artifact files and passed all
listed counts:

- 14 commands
- 13 nonempty log hashes
- 187 steps
- seven assembly objects
- 34 objects
- 50 exports
- 181 runner-checked retained hashes
- seven FriBidi hashes matching run 38014071478

Binary products were not transferred. See
[the acceptance and limits](../../docs/WINDOWS-LIBASS-SOURCE-ACCEPTANCE.md#retained-archive-source-run).

The acquisition tests include
real extraction of all twelve retained archives as data, Unicode/header checks,
and standard Windows link-copy fallback, with subprocess execution forbidden:

```sh
V18_SOURCE_BUNDLE=/absolute/path/libass-retained-source-archives-v18.zip \
  python3 -I _scripts/notices/test_libass_source_archives.py
```

Without that fixture, the real-archive test explicitly skips. Extraction alone
does not establish compilation, network isolation or complete corresponding
source. The build job still has network access; this workflow makes no stronger
offline-isolation claim. No installed app, public release or recorded source
obligation is changed by this candidate.
