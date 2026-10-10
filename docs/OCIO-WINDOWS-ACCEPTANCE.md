# Private Windows OpenColorIO application acceptance

Hardware export and private assembly were checked on 2026-10-09 (local time).
After the supported computer-use connection recovered, native preview and
settings interaction were checked on the same Windows laptop at 2026-10-10
03:09–03:18 UTC (the evening of 2026-10-09, UTC−4) using the unchanged selected
`427a6ca4` application. By design, this build uses the official OpenColorIO
processor for export and for its generated GPU preview; the interface check
below does not independently confirm the preview backend. This is a private
candidate, not an approved public download.

## Exact identities

| Item | Verified identity |
| --- | --- |
| Application source | `427a6ca40670a8ad9902fa7f15fa9677792ccde2` |
| Selected Cargo features | `--no-default-features --features opencv,ocio-runtime` |
| Executable | `Gyroflow.exe`, 43,900,928 bytes |
| Executable SHA-256 | `26c09dccb980811f397457e20c9496bb9cd308b7efcc720ce79486fad1c8763d` |
| Native runtime inventory | 120 DLLs; staged imports resolved, x64 audit passed |
| Notice and supplemental source commit | `6e27b793cea6ee2434caee768c49def0eed5b834` |
| Native notice manifest SHA-256 | `fe2e3e0a457cba28b38f2a9333ca3d3eaef7d72ae79c3c66079c91edc3ed5a25` |
| Private assembly receipt SHA-256 | `62cbbf21f49cb27262533034bea2d5e95aa2e29b07f91f4b6cb18201587ffc6e` |

The locked offline application build completed successfully. The staged
application's isolated `--help` invocation also exited successfully. Its
`qt.conf` points `QmlImports` at the deployed `qml` directory. These startup and
import checks do not establish native preview behavior.

## Hardware export and decoded output

The current executable exported a four-second section of moving DJI footage
with a selected LUT and all eight color controls nonzero. The actual NVIDIA
encoder-session table identified an H.265 3840×2160 session belonging to the
render process, including nonzero frame-rate samples. This is direct hardware
encoding evidence for that run.

| Output check | Result |
| --- | --- |
| Render process | Exit 0; measured render interval 17.215 seconds |
| Output | HEVC Main 10, `yuv420p10le`, BT.709 limited range |
| Frame rate / duration | 60000/1001 fps; 4.037367 seconds |
| Complete independent decode | Exit 0; 242 frames |
| Output bytes | 67,820,243 |
| Output SHA-256 | `2fb159b29cf0f22f4ac29e9b7256b59e6bc7513ef8f53a20968b916cb24f9ac5` |
| Decoded frame-hash file SHA-256 | `44f6c88d52f5140dfbc78402aee457c5aad149bf646b06f7fa640f67a79bafcd` |

Both the output bytes and decoded frame-hash file match the previously accepted
graded export. The export metadata records brightness 0.12, contrast 0.18,
shadows −0.5, highlights 0.5, exposure 0.37, saturation 0.23, warmth 0.41 and
tint −0.27. This confirms preservation of that export case; it does not prove
every camera/codec, Windows GPU preview parity or general performance.

## Recovered native Windows interface check

The supported helper previously returned `GetCursorPos: Access is denied`.
After supported input recovered, the worker tested an owned copy of the accepted
application, with an owned project and DJI O4 LUT. The executable hash matches
the identity above. The original private assembly's indexed files matched their
baseline hashes afterwards (see below).

| Native check | Result |
| --- | --- |
| Preview colors off/on | Worker observed a visible color change at the same paused 47-second frame; the LUT and all eight adjustment values stayed selected |
| Double-click reset | Exposure settled at zero; the other seven values stayed unchanged |
| Reset adjustments | All eight controls settled at zero; the LUT stayed selected |
| Clear LUT | The selector returned to its empty state and the Clear button disappeared |
| Save and reopen | After saving the owned project, resetting and clearing, native reopen restored all eight nonzero values and the selected LUT. In the settled post-reopen and close-prompt accessibility snapshots the selector shows the LUT and the Clear button is present again, as a newly created accessibility element; only the snapshot taken immediately on reopen, before the project finished loading, still showed the cleared state. Active-LUT grading after reopen was worker-observed |
| Exit | After the worker confirmed the close prompt, the application exited normally; no remaining owned window or modal |

The saved grade matches the eight values listed in the export case above.
Root independently checked the transferred evidence-file hashes, 17 timestamped
accessibility observations, settled slider/editor and LUT-selector values, and
the saved-project semantic snapshot. Accessibility data does not record the
Preview colors checkbox state; the off/on toggle and color change were
worker-observed. Screenshot pixels were viewed by the worker in the native
tool history; they were not transferred for independent image comparison. This
is interface and persistence evidence, not a new numerical GPU parity or export
performance measurement.

The worker's final hash check compared every indexed file with the historical
accepted baselines: 1,233 frozen assembly files, 7,455 protected inputs and the
652-file Easy Eject review/profile subset. All matched. Root verified the exact
baseline indexes and subset against the transferred summaries; it did not
rehash the remote files directly. Preservation is established only for those
indexed files. The keeper was not queried or touched, security settings were
outside this slice, and no export was repeated.

The terminal receipt is 5,308 bytes, SHA-256
`da55dd7baed8d262fb079e454419851c46440f0c8b05af59077800eff84d2b60`.
Private evidence and the independent data-only inspector are retained under
`_dev/root-windows-native-gui-427a-20261010/`.

### Direct3D compiler observation

The tested process loaded its app-local `D3DCompiler_47.dll`: 4,173,928 bytes,
version `6.3.9600.16384`, SHA-256
`e994847e01a6f1e4cbdc5a864616ac262f67ee4f14db194984661a8d927ab7f4`.
Its loaded path (compared case-insensitively) and hash match the app-local file
in the tested owned copy. This does not identify which component loaded it or
prove that omitting it is safe. The existing
120-DLL inventory and `d3d-terms` requirement remain unchanged; a possible
future package using the system compiler needs separate candidate proof.

## Complete private notice assembly

An initial deep-path notice copy failed before packaging. A later file-only
assembly used a short destination, with a maximum normal path length of 227
characters. No Windows path policy or security setting was changed.

The new assembly preserves all 627 original stage files, the original build
receipt and source archive, the executable, and all 120 DLL identities. It adds
603 native notice members plus their manifest **inside the application
directory**, and a complete source archive for the supplemental `6e27b793`
commit. The original receipt is retained unchanged; `ASSEMBLY.json` records the
new assembly separately from the older binary build.

Independent acceptance checked all transferred evidence-file hashes, compared
all 1,301 supplemental source files with the committed checkout and all 1,283
original source files with the original Git revision, and verified the notice
member hashes against committed files. All 661 files outside documentation
and notice areas are byte-identical between those source versions. The 25
changed paths contain only documentation and notices.

The assembly has 1,233 files including its receipt. Its canonical final
inventory SHA-256 is
`52d262d178a2925ea6f33e34978b3d5e7b4fbea79006f78c8111cfc19056d7c4`.
The supplemental source archive is 46,899,200 bytes, SHA-256
`99db08c21601dde9b3e68024fc8959c67cf44ae5f1a0116c577f0104aefbd70d`;
the worker's complete archive-member map matches the independently verified
source inventory. Remote package/binary byte hashes are worker observations;
the acceptance host did not execute or transfer those binaries again.

Content integrity passed. **Historical (2026-10-09 `6e27b793` assembly):** strict
provenance checking of that assembly's notice manifest returned the expected
incomplete result for **ten remaining requirements** across Qt, FFmpeg, MDK,
Microsoft CRT, D3D compiler and software OpenGL. That count, and the notice
commit, manifest and receipt identities above, describe only that private
assembly and are not updated here. Complete notice copying is distinct from
establishing every provider's distribution/source obligations. All assembly
jobs ended, including preserved failed helper attempts.

### Current source notice packet

The current native notice snapshot, `resources/notices/native/windows-x64`, is a
separate, later packet. Its `MANIFEST.json` is 559,717 bytes, SHA-256
`41edb624f5aa46aab954d03555b33ba18876d36546df68248b45de1192433530`. It uses schema
`gyroflow-plus/native-notices-manifest/v2`, has status `CANDIDATE`, targets
`x86_64-pc-windows-msvc`, and sets `public_release_approved: false`.

The offline verifier ran pinned to that hash. It found:

- 1,392 listed members (8,209,623 verified bytes), matching 1,392 files plus the manifest
- 25 reused repository paths
- 11 required components
- a staged inventory of 120 DLL entries across 10 components

Content integrity passed with 0 problems. The strict check reported
`RELEASE-PROVENANCE: INCOMPLETE`, with exactly eight blocking gaps across six
components (3 blockers, 5 obligations):

- d3dcompiler: `d3d-terms`
- ffmpeg: `ffmpeg-texts`, `ffmpeg-source`
- mdk: `mdk-ffmpeg9-source`, `mdk-libass-fribidi-source`
- msvc-crt: `crt-terms`
- qt: `qt-source`
- unattributed: `opengl32sw-provider`

The later libass archive-source build/relink qualification and retained draft
source kit are indexed in
`mdk-0.39.0-e89bc0b/bundled/evidence/LIBASS-SOURCE-QUALIFICATION.json`. They do not close
public delivery or remaining corresponding-source/provider requirements.

Fifteen advisories are recorded separately from the eight blocking requirements.
This source check does not establish assembly or installation of the later
packet on Windows; the dated `6e27b793` assembly acceptance above is unchanged.

Private evidence is retained under `_dev/root-windows-427a-acceptance-20261009/`
and `_dev/root-windows-6e27-assembly-acceptance-20261009/`. Source preparation
supplements are retained in an unpublished GitHub draft; they do not establish
complete corresponding source or approve a binary release.

## Remaining acceptance

- Windows GPU preview numerical parity with export (interface check only; not
  measured).
- Remaining exact provider notices, terms and corresponding-source delivery.
- Clean-machine and supported Windows version testing and ordinary trust checks.
- Final release packaging tied to the accepted source and runtime identities.

The [public-release gates](PLUS-DISTRIBUTION.md#public-release-gates) remain in
force. No public release, default runtime switch or website download approval
follows from this private acceptance.
