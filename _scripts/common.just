set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
PathSep := if os() == "windows" { ";" } else { ":" }

ProjectVersion := "1.6.3"
ProjectDir := if path_exists(justfile_directory() / "Cargo.toml") == "true" { justfile_directory()
       } else if path_exists(justfile_directory() / ".." / "Cargo.toml") == "true" { justfile_directory() / "../"
       } else { justfile_directory() }
ExtDir := ProjectDir / "ext"
Arch := env("FORCE_ARCH", arch())

# ――――――――――――――――――――――――――――――――――――――――― Qt ――――――――――――――――――――――――――――――――――――――――――
QtVersion := env_var_or_default("FORCE_QT_VERSION", if os() == "windows" { "6.7.3" } else { if Arch == "aarch64" { "6.7.3" } else { "6.4.3" } })
QtArch := if os() + Arch == "windowsx86_64"  { "msvc2019_64"
   } else if os() + Arch == "windowsaarch64" { "msvc2019_arm64"
   } else if os() == "macos"   { "macos"
   } else if Arch == "aarch64" { "gcc_arm64"
   } else                      { "gcc_64" }
QtPath := ProjectDir / "ext/" / QtVersion / QtArch / "bin"
export QMAKE := env_var_or_default("QMAKE", if path_exists(QtPath / "qmake.bat") == "true" { QtPath / "qmake.bat" } else { QtPath / "qmake" })
# ――――――――――――――――――――――――――――――――――――――――― Qt ――――――――――――――――――――――――――――――――――――――――――

# ――――――――――――――――――――――――――――――――――――――― FFmpeg ――――――――――――――――――――――――――――――――――――――――
# Slim build of BtbN's scripts (docs/WINDOWS-FFMPEG-SLIM.md), kept in a private
# draft release of this repository until a public release is approved.
WindowsFFmpegRepo := "rsmith4321/gyrograde"
WindowsFFmpegRelease := "ffmpeg-slim-n9.0.2-22-g46d8f462ee-r1"
WindowsFFmpegArch := if Arch == "aarch64" { "winarm64" } else { "win64" }
WindowsFFmpegSHA256 := if Arch == "aarch64" { "a0e2484817ec803819dd5908575533ce4e90fe77c294e6daf6a6cc095ed1a423" } else { "0926f6aca7b98307394f363973c0418cdb98ab61893f3f6a8de0e1be627a5de6" }
FFmpeg := if os() == "windows"               { "ffmpeg-n9.0.2-22-g46d8f462ee-" + WindowsFFmpegArch + "-gpl-shared-9.0-gyroflowplus-slim"
   } else if os() + Arch == "macosaarch64"   { "ffmpeg-arm64"
   } else if os() + Arch == "macosx86_64"    { "ffmpeg-x86_64"
   } else                                    { "ffmpeg-9.0-linux-clang-gpl-lite" }
export FFMPEG_DIR := env_var_or_default("FFMPEG_DIR", ProjectDir / "ext" / FFmpeg)
export FFMPEG_ARCH := if Arch == "aarch64" { "arm64" } else { if os() == "windows" { "x64" } else { "amd64" } }
# ――――――――――――――――――――――――――――――――――――――― FFmpeg ――――――――――――――――――――――――――――――――――――――――

# ――――――――――――――――――――――――――――――――――――――― OpenCV ――――――――――――――――――――――――――――――――――――――――
VcpkgArch := if os() + Arch == "windowsx86_64"  { "x64-windows"
      } else if os() + Arch == "windowsaarch64" { "arm64-windows"
      } else if os() + Arch == "macosaarch64"   { "arm64-osx"
      } else if os() + Arch == "macosx86_64"    { "x64-osx"
      } else if Arch == "aarch64"               { "arm64-linux"
      } else                                    { "x64-linux" }
export OPENCV_LINK_LIBS := "opencv_core4,opencv_calib3d4,opencv_features2d4,opencv_imgproc4,opencv_video4,opencv_flann4,opencv_imgcodecs4,opencv_objdetect4,opencv_stitching4" + if os() == "linux" { if Arch == "aarch64" { ",tegra_hal,png" } else { ",png" } } else { "" }
export OPENCV_LINK_PATHS := ProjectDir / "ext/vcpkg/installed" / VcpkgArch / "lib," + ProjectDir / "ext/vcpkg/installed" / VcpkgArch / "lib/manual-link/opencv4_thirdparty"
export OPENCV_INCLUDE_PATHS := ProjectDir / "ext/vcpkg/installed" / VcpkgArch / "include/opencv4"
OpenCVPath := ProjectDir / "ext/vcpkg/installed" / VcpkgArch
# ――――――――――――――――――――――――――――――――――――――― OpenCV ――――――――――――――――――――――――――――――――――――――――

# ――――――――――――――――――――――――――――――――――――――― MacOS ―――――――――――――――――――――――――――――――――――――――――
export DYLD_FALLBACK_LIBRARY_PATH := if os() == "macos" { if path_exists(`xcode-select --print-path` + "/Toolchains/XcodeDefault.xctoolchain/usr/lib/") == "true" { `xcode-select --print-path` + "/Toolchains/XcodeDefault.xctoolchain/usr/lib/" } else { `xcode-select --print-path` + "/usr/lib/" } } else { "" }
export MACOSX_DEPLOYMENT_TARGET := "10.15"
# ――――――――――――――――――――――――――――――――――――――― MacOS ―――――――――――――――――――――――――――――――――――――――――

# ――――――――――――――――――――――――――――――――――――――― Clang ―――――――――――――――――――――――――――――――――――――――――
LlvmLibDir := if os() == "linux" { `d=""; for x in $(ls -d /usr/lib/llvm-*/lib 2>/dev/null | sort -V); do v=${x#/usr/lib/llvm-}; v=${v%/lib}; [ "$v" -ge 13 ] 2>/dev/null && d=$x; done; if [ -z "$d" ]; then v=$(llvm-config --version 2>/dev/null | cut -d. -f1); [ "${v:-0}" -ge 13 ] 2>/dev/null && d=$(llvm-config --libdir 2>/dev/null); fi; echo "$d"` } else { "" }
export LIBCLANG_PATH := if os() == "macos" {
   DYLD_FALLBACK_LIBRARY_PATH
} else {
   if path_exists(ExtDir / "llvm/bin") == "true" {
      ExtDir / "llvm/bin"
   } else {
      env_var_or_default("LIBCLANG_PATH", LlvmLibDir)
   }
}
LLVMPath := LIBCLANG_PATH
# ――――――――――――――――――――――――――――――――――――――― Clang ―――――――――――――――――――――――――――――――――――――――――


export LD_LIBRARY_PATH := ProjectDir / "target/release:" + QtPath / "../lib:" + FFMPEG_DIR + "/lib:" + FFMPEG_DIR + "/lib/" + FFMPEG_ARCH

export PATH := QtPath + PathSep + FFMPEG_DIR + "/bin" + PathSep + FFMPEG_DIR + "/bin/" + FFMPEG_ARCH + PathSep + OpenCVPath + "/bin" + PathSep + LLVMPath + PathSep + env_var('PATH')

# export VULKAN_SDK := "D:/Programy/VulkanSDK/1.3.236.0"
