# Vendored crates

## ffmpeg-sys-next 9.0.0

`ffmpeg-sys-next-9.0.0/` is the published crates.io package with one change,
`ffmpeg-sys-next-9.0.0.patch`. The root `Cargo.toml` selects it with
`[patch.crates-io]`, so its `Cargo.lock` entry has no registry source or checksum.
Every other lockfile record is unchanged.

| Fact | Value |
| --- | --- |
| Package | https://static.crates.io/crates/ffmpeg-sys-next/ffmpeg-sys-next-9.0.0.crate |
| Package SHA-256 | `9b939bf79dd5949412a4b81cfe21a07f48ea21b47fcbb5f57816c8c2de5ae30b` (the checksum the unpatched `Cargo.lock` recorded) |
| Upstream source | https://github.com/zmwangx/rust-ffmpeg-sys tag `v9.0.0`, commit `80b7dd8327c3539159f37d8ca5423c75d6cd2e57` |
| License | `WTFPL`, as declared in the package manifest; the package ships no license text |
| Not vendored | the package's own `Cargo.lock`, which Cargo ignores for path dependencies and the package's `.gitignore` excludes |

**The change.** With the `static` feature on macOS, the upstream build script always asks
the linker for the `QTKit` and `VideoDecodeAcceleration` frameworks. FFmpeg removed its QTKit
input device in 3.4 and its VDA hwaccel in 4.0 (FFmpeg `Changelog`). This crate's 9.0 series
targets FFmpeg 9.0, which references neither, and SDKs without those frameworks fail the link.
The patch removes those two names and adds a comment. It changes no other framework or
library, no FFmpeg source or header, no binding and nothing on iOS, tvOS, Windows, Linux or
Android, and dynamic macOS builds are unaffected.

**Verify** (nothing is downloaded or built; obtain the `.crate` file yourself):

```sh
python3 _scripts/verify_vendored_ffmpeg_sys.py --crate path/to/ffmpeg-sys-next-9.0.0.crate
FFMPEG_SYS_CRATE=path/to/ffmpeg-sys-next-9.0.0.crate python3 -m unittest discover -s tests/package-plus
```

The removal is supported by the [pinned FFmpeg changelog](https://github.com/FFmpeg/FFmpeg/blob/ad500d59cb6e0126add4fcb95afb4e2557c4292c/Changelog).
The offline verifier extracts the same bytes it hashes; it does not reopen the input path
after the identity check. Both platform stages retain this provenance, the original
README and manifest (including the WTFPL declaration), and the exact patch under
`Notices/ffmpeg-sys-next/`. No license text was added to the original crate.

**Updating or removing.** Delete this directory and the `[patch.crates-io]` entry once the
upstream crate stops requesting these frameworks. `cargo metadata` then restores the registry
source and checksum. To move to another version, vendor that package, re-apply the patch, and
update the verifier's name and SHA-256 together.

## qmetaobject_impl

The separately retained Qt derive crate and its MIT license are documented in
`qmetaobject-rs/PATCHES.md` and `qmetaobject-rs/UPSTREAM.json`.
