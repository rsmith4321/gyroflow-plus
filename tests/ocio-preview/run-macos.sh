#!/bin/sh
# Synthetic fixture only. Builds outside the application's Cargo target.
set -eu
repo=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
: "${OCIO_ROOT:?Set OCIO_ROOT to pinned OpenColorIO 2.4.2 install prefix}"
qt_prefix=${QT_PREFIX:-/opt/homebrew}
qt_version=${QT_VERSION:-6.11.2}
fixture_out=${OCIO_PREVIEW_TEST_OUT:-"$repo/_dev/ocio-runtime/native-preview"}
mkdir -p "$fixture_out"
/usr/bin/clang++ -std=c++17 -F"$qt_prefix/lib" -I"$qt_prefix/include" \
  -I"$qt_prefix/lib/QtCore.framework/Headers" \
  -I"$qt_prefix/lib/QtGui.framework/Headers" -I"$qt_prefix/lib/QtGui.framework/Headers/$qt_version/QtGui" \
  -I"$qt_prefix/lib/QtQuick.framework/Headers" -I"$qt_prefix/lib/QtQml.framework/Headers" \
  -I"$qt_prefix/lib/QtShaderTools.framework/Headers" -I"$qt_prefix/lib/QtShaderTools.framework/Headers/$qt_version/QtShaderTools" \
  -I"$OCIO_ROOT/include" "$repo/tests/ocio-preview/native_preview.cpp" "$repo/src/rendering/ocio/bridge.cpp" \
  -framework QtCore -framework QtGui -framework QtQuick -framework QtQml -framework QtShaderTools \
  -L"$OCIO_ROOT/lib" -lOpenColorIO -Wl,-rpath,"$OCIO_ROOT/lib" -Wl,-rpath,"$qt_prefix/lib" \
  -o "$fixture_out/native-preview"
"$fixture_out/native-preview" "$repo" "${1:-}" "$fixture_out/results.json"
"$fixture_out/native-preview" --software-check
