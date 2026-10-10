#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Trim a BtbN/FFmpeg-Builds checkout to the components Gyroflow+ uses.
#
# Usage: slim-btbn.sh <btbn-checkout>
#
# BtbN's gpl-shared variant enables about 80 external libraries. Gyroflow+ only
# needs the encoders it offers (x264, x265, rav1e, aom, SVT-AV1 and the NVENC,
# AMF, QSV and Vulkan GPU paths), dav1d for AV1 decoding, zlib for PNG/EXR, and
# FFmpeg's own codecs and filters. Everything else only adds licence texts and
# corresponding source to ship. See docs/WINDOWS-FFMPEG-SLIM.md.
set -euo pipefail

BTBN="$(cd "$1" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
FFMPEG_COMMIT="$(sed -n 's/^ffmpeg_commit=//p' "$HERE/slim.pin")"
BTBN_COMMIT="$(sed -n 's/^btbn_commit=//p' "$HERE/slim.pin")"
[[ -n "$FFMPEG_COMMIT" && -n "$BTBN_COMMIT" ]]
[[ "$(git -C "$BTBN" rev-parse HEAD)" == "$BTBN_COMMIT" ]] || {
    echo "BtbN checkout is not at $BTBN_COMMIT" >&2; exit 1; }

# Build stages kept, by scripts.d name (files or directories). vmaf stays
# because the pinned aom build enables tune=vmaf.
KEEP=(10-mingw-std-threads.sh 10-mingw.sh 10-xorg-macros.sh 15-base.sh
      20-zlib.sh 45-vmaf.sh 47-vulkan
      50-amf.sh 50-aom.sh 50-dav1d.sh 50-ffnvcodec.sh 50-onevpl.sh
      50-rav1e.sh 50-svtav1.sh 50-x264.sh 50-x265.sh zz-final.sh)
DEPENDS=(zlib vmaf vulkan amf aom dav1d ffnvcodec onevpl rav1e svtav1 x264 x265)

cd "$BTBN/scripts.d"
for entry in *; do
    keep=0
    for wanted in "${KEEP[@]}"; do [[ "$entry" == "$wanted" ]] && keep=1; done
    (( keep )) || rm -rf -- "$entry"
done
for wanted in "${KEEP[@]}"; do
    [[ -e "$wanted" ]] || { echo "Missing BtbN stage: $wanted" >&2; exit 1; }
done

# The final stage lists what FFmpeg links against; generate.sh only collects
# configure flags from stages reachable from it.
{
    sed -n '1,/^ffbuild_depends() {$/p' zz-final.sh
    printf '    echo %s\n' "${DEPENDS[@]}"
    sed -n '/^ffbuild_depends() {$/,$p' zz-final.sh | sed -n '/^}$/,$p'
} > zz-final.sh.new
mv zz-final.sh.new zz-final.sh

cd "$BTBN"
# Build the pinned FFmpeg commit, with a fixed version suffix instead of the
# build date, and give the bundle its own name so an existing full BtbN
# extraction under ext/ is never mistaken for it.
grep -q '^    cd ffmpeg$' build.sh
FFMPEG_COMMIT="$FFMPEG_COMMIT" perl -pi -e '
    s|^    cd ffmpeg$|    cd ffmpeg\n    git checkout --detach $ENV{FFMPEG_COMMIT}|;
    s|--extra-version="\\\$\(date \+%Y%m%d\)"|--extra-version="gyroflowplus-slim"|;
    s|^BUILD_NAME="(.*)"$|BUILD_NAME="$1-gyroflowplus-slim"|;
' build.sh
grep -q "git checkout --detach $FFMPEG_COMMIT" build.sh
grep -q 'extra-version="gyroflowplus-slim"' build.sh
grep -q -- '-gyroflowplus-slim"$' build.sh
echo "Trimmed $BTBN to: ${DEPENDS[*]}"
