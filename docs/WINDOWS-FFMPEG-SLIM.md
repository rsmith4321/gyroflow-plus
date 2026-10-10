# Slim Windows FFmpeg

Gyroflow+ switched the Windows FFmpeg from avbuild's GPL-lite bundle to BtbN's
full `gpl-shared` bundle in `62318d48`, because the export LUT path needs
`lut3d` (and the export tests' reference graph needs `geq`). That bundle also
compiles in about 80 external libraries the app never uses (xvid, libass and
its font stack, librsvg, Blu-ray/DVD, SRT, RIST, ZeroMQ, SSH, SDL, VapourSynth,
frei0r, ...). Each one adds licence texts and corresponding source that a
release has to carry.

The slim bundle is built from the same pins with only what the app uses.

## Pins

`_scripts/ffmpeg-windows/slim.pin`:

- BtbN FFmpeg-Builds `9acad4a9ef15` (the scripts behind the current bundle).
- FFmpeg `46d8f462ee` (n9.0.2-22, the same source as the current bundle).
- BtbN's `base` and `base-win64`/`base-winarm64` toolchain images by digest.
  They were built on 2026-10-04, before the 2026-10-06 autobuild the current
  bundle came from. BtbN deletes untagged images, so if a digest disappears
  the toolchain has to be rebuilt from `images/base-*` at the same commit.

## Kept components

| Stage | Why |
|---|---|
| zlib | PNG and EXR encode/decode |
| x264, x265 | Software H.264/HEVC export; the app treats GPL FFmpeg as present only when both exist |
| rav1e, aom (+ vmaf, used by aom's `tune=vmaf`), SVT-AV1 | The three software AV1 encoders the app offers |
| dav1d | AV1 decoding |
| nv-codec-headers, AMF, oneVPL, Vulkan | NVENC, AMF, QSV and Vulkan encoders and hardware decoding |
| mingw-w64 runtime | Toolchain runtime |

Everything else in FFmpeg the app uses is FFmpeg's own code: ProRes, DNxHD,
CineForm, FFV1, PNG, EXR, AAC, ALAC and PCM encoders, the camera decoders,
the MP4/MOV/MKV/MXF/image muxers, `lut3d`, `geq`, `scale`, `colorspace`, and
D3D11VA, D3D12VA, DXVA2 and Media Foundation, which come from the mingw-w64
headers.

aom and oneVPL are not built for Windows ARM64 by BtbN, in either bundle.

## Build and checks

`.github/workflows/windows-ffmpeg-slim.yml` trims the BtbN checkout with
`_scripts/ffmpeg-windows/slim-btbn.sh`, builds with BtbN's own scripts on the
pinned toolchain images, then on native Windows x64 and ARM64 runners:

1. runs `tests/export-lut/check_windows_ffmpeg.py --app-coverage`, which adds
   every encoder, decoder, muxer, demuxer, filter and hardware device type the
   Windows app can select to the existing build gate;
2. runs the same coverage check on the full bundle as a reference;
3. encodes and decodes every software codec the app offers, plus the
   `lut3d`/`geq` graph (`_scripts/ffmpeg-windows/smoke_encode.py`);
4. records exactly which encoders, decoders, formats, filters, protocols and
   configure flags the slim bundle drops compared with the full one.

Hardware encoders are checked for presence only; hosted runners have no GPUs.

## Mac and Linux

macOS and Linux still use avbuild's GPL-lite builds. The installed Mac app
(`/Applications/Gyroflow Plus.app`, built with `ocio-runtime`) contains the
filter names `scale`, `colorspace` and `buffersink` but neither `lut3d` nor
`geq` (2026-10-10, `strings` on the binary). Its LUT export works because the
OCIO runtime applies the LUT without FFmpeg. A default (legacy) Mac build
would fail LUT export with "This FFmpeg build does not include the lut3d
filter". The Linux lite build was not inspected and is assumed to be the same.

## Status

Pinned since 2026-10-10. Run 38057762428 built both bundles; they are kept in
the private draft release `ffmpeg-slim-n9.0.2-22-g46d8f462ee-r1` of this
repository, so `windows.just` downloads them with the signed-in GitHub CLI.

| Target | Archive SHA-256 | Bytes |
|---|---|---|
| win64 | `0926f6aca7b98307394f363973c0418cdb98ab61893f3f6a8de0e1be627a5de6` | 33,564,288 |
| winarm64 | `a0e2484817ec803819dd5908575533ce4e90fe77c294e6daf6a6cc095ed1a423` | 22,754,298 |

Both passed every check above on native runners (x64 in the build run, ARM64
in verify run 38061390279). Compared with the full bundle, the slim one drops
only components the app never selects: library-backed encoders and decoders
such as xvid, vpx, opus, lame, theora, webp, jxl and openjpeg (FFmpeg's own
VP9, Opus and Vorbis decoders remain), subtitle, OpenCL and VAAPI filters, the
DASH and IMF demuxers and the SRT, RIST and SFTP protocols. The DLLs shrink
from 191 MB to 89 MB.

The Windows native notices list the 27 slim components and the 65 Rust crates
rav1e links. 52 of those crates had no notice in the full-bundle tree because
they leave no source paths in the DLLs; their texts were added from the
checksum-verified `.crate` files.

Not yet done: a Windows app build and export run with the slim bundle (needs a
Windows machine), and public delivery of the archives and their corresponding
source, which waits on release approval.
