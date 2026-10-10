# Windows libass source kit

This kit retains the inputs and evidence for a hosted source-rebuild qualification
of libass in run [38017550683](https://github.com/rsmith4321/gyroflow-plus/actions/runs/38017550683) at Gyroflow+ commit `4dd7582a606ec39ba7e9385f58b4195085ae6a4b`. It is inert data: archives, text and build glue. Nothing in it runs when you download, list, hash or extract it.

It is **not** a Gyroflow+ application release and contains no application binaries. It is not offered as complete corresponding source or as legal acceptance of any distribution. It is prepared for additive retention on an unpublished, source-only draft release. The existing `libass-retained-source-archives-v18.zip` asset there is unchanged.

## Contents

| Member | What it is |
| --- | --- |
| `libass-retained-source-archives-v18.zip` | 62447389 bytes, SHA-256 `8cdbf56eb72add8f592bccd9dfc93a39395d51e4bc91c77f67d6781a5e8ea2e5`. Contains twelve original `.tar.gz` source archives, exactly as retained. |
| `libass-build-glue.tar` | A `git archive` of the build script, manifest, tests, manual workflow, `LICENSE`, repository `README.md`, acceptance documentation and this file, taken from the kit commit. |
| `libass-qualification-evidence.tar` | The 28 original JSON/log evidence files from the successful hosted build and root acceptance, retained before GitHub artifact expiry. No binary products or private environment-capture output. |
| `SOURCE-KIT-MANIFEST.json` | The size and SHA-256 of the three payload members and their file maps, the kit source commit, retained source draft/tag and qualification identities. The manifest does not hash itself; the outer ZIP hash covers it. |

The kit commit is the commit recorded for these instructions and build files, and `SOURCE-KIT-MANIFEST.json` records it. Members are stored uncompressed, with the commit timestamp and fixed permissions. Preparing a kit requires its build script to match the one qualified at `4dd7582a`. Draft retention does not publish a release.

## Verify and extract

Work in a new, empty directory. First check the kit ZIP against the size and SHA-256 published where you obtained it. Then hash each extracted member and compare it with `SOURCE-KIT-MANIFEST.json`:

```sh
sha256sum FILE                         # Linux
shasum -a 256 FILE                     # macOS
Get-FileHash -Algorithm SHA256 FILE    # Windows PowerShell
```

Python's standard library can list, test and extract ZIP files without third-party tools:

```sh
python -I -m zipfile -l KIT.zip
python -I -m zipfile -t KIT.zip
python -I -m zipfile -e KIT.zip kit/
```

Then unpack the glue and the retained archives into separate directories:

```sh
mkdir glue && tar -xf kit/libass-build-glue.tar -C glue
python -I -m zipfile -e kit/libass-retained-source-archives-v18.zip sources/
```

Each of the twelve `.tar.gz` files should match the repository, commit, size and SHA-256 recorded in the retained-source manifest in the glue. Extract each archive with `tar -xzf` into its own directory. The HarfBuzz archive contains one symlink (`CLAUDE.md` → `AGENTS.md`). On Windows, extracting it may need symlink privileges, or the tool may substitute a copy.

Extracting the files is enough to read and inspect the sources. These instructions do not cover running the build script or any extracted code on your own machine.

## Hosted rebuild (qualified route)

The only qualified rebuild is the manual GitHub Actions workflow **Native libass retained source archives**. It is bound to repository `rsmith4321/gyroflow-plus`, branch `codex/lut-preview-controls`, and `workflow_dispatch`. Its admission checks restrict that qualified job to these identities.

- **`fetch-retained-source`** has `contents: write` only because GitHub hides draft releases from read-only tokens. It downloads the retained ZIP and checks its size and SHA-256. It then passes the ZIP to the next job as a one-day artifact. It does no checkout and runs no downloaded code.
- **`source-rebuild`** has `contents: read`. It checks out the dispatched branch commit and verifies every archive hash pin. The qualified route requires that commit's build script, archive manifest and workflow to match the file hashes in this kit. A later branch tip is not automatically qualified. It builds on the GitHub-hosted `windows-2025` image, using the MSVC, CMake, Ninja and Perl that the image provides. NASM is built from its pinned source archive. Only JSON and log evidence is uploaded, and it is kept for 14 days.

Before dispatch, compare those three files at the intended branch commit with
`SOURCE-KIT-MANIFEST.json`. Do not infer recipe identity from a branch name.
A maintainer with write access can start the workflow from the GitHub UI (Actions → workflow → Run workflow) or with the GitHub CLI:

```sh
gh workflow run "Native libass retained source archives" \
  --repo rsmith4321/gyroflow-plus --ref codex/lut-preview-controls
gh run list --repo rsmith4321/gyroflow-plus \
  --workflow "Native libass retained source archives"
gh run download RUN_ID --repo rsmith4321/gyroflow-plus
```

Users without repository write access cannot start this workflow. This kit provides no supported build route outside it: not on another machine, and not in another repository or branch.

## What run 38017550683 established

Run 38017550683 built from the twelve retained archives, without Git, at `4dd7582a`. It established that:

- all twelve archive pins verified;
- all seven original x64 assembly objects built, as part of a 187-step libass build;
- 34 libass objects linked with the FriBidi, FreeType and HarfBuzz static dependencies;
- fifty exported names matched the pinned `libass.sym`, both before and after relink;
- deleting only the DLL produced a relink, with all 181 retained object and static-library hashes unchanged;
- the seven generated FriBidi outputs matched reference run 38014071478.

The initial and relinked candidate DLLs have different hashes. Neither is shown to match the vendor DLL. The candidate was not installed, did not replace any shipped binary, and is not part of this kit.

## Licenses

License files inside the original archives are preserved unchanged. The repository's GPLv3 license and additional permissions are retained in `LICENSE` and
`README.md` inside `libass-build-glue.tar`. Individual source notices remain intact.

## Limits

- The hosted runner had network access, so no network-isolation or offline-build claim is made.
- The hosted toolchain is not shown to match the vendor's toolchain.
- No claim is made about local buildability, binary equivalence or version metadata.
- The recorded Windows distribution requirements remain open, including `mdk-libass-fribidi-source`. This kit does not close the license or corresponding-source gap.
