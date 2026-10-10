# OpenColorIO runtime notices

This packet retains the original notices for the separately built OpenColorIO
2.4.2 arm64 Mac dependency candidate described in
[dependency acceptance](../../../docs/OCIO-DEPENDENCY-ACCEPTANCE.md).
The existing [OpenColorIO BSD notice](../OCIO-LICENSE.txt) is unchanged.

| Component | Retained material |
| --- | --- |
| OpenColorIO 2.4.2 | Root BSD notice, linked above |
| Imath 3.1.12 | [License](Imath-3.1.12-LICENSE.md) |
| yaml-cpp 0.7.0 | [License](yaml-cpp/LICENSE) |
| pystring 1.1.3 | [License](pystring/LICENSE) |
| minizip-ng 3.0.7 | [License](minizip-ng/LICENSE) |
| SSE2NEON (arm64 only) | [License](sse2neon/LICENSE) |
| SampleICC embedded in OCIO | [Modification context](ocio-internal/sampleicc/README.md) and complete original headers |
| xxHash embedded in OCIO | Complete original header with its notice |
| CDL file format code in OCIO | [Cinesite VFX notice](ocio-internal/cdl/FileFormatCDL-notice.txt), lines 1-27 of `FileFormatCDL.cpp` |
| Expat 2.5.0 (Windows) | [License](expat/COPYING) |
| zlib 1.2.13 (Windows) | [License](zlib/LICENSE) |

[manifest.json](manifest.json) records the exact source commits, archive hashes,
candidate library identity, and sizes and SHA-256 hashes of the retained files.
SampleICC and xxHash headers are retained whole to preserve their original
copyright, conditions, disclaimers and modification context. They are notice
archive material; Gyroflow does not compile these copies.

The optional `ocio-runtime` feature links an externally supplied `OCIO_ROOT`.
Tracking these notices does not add or package that library. This packet describes
the identified Mac dependency recipe; another recipe or Windows build needs
notices matching its actual inputs. Apple's Expat and zlib are system libraries
in the Mac candidate, rather than copies included in the OCIO dylib. On Windows,
OCIO's default recipe builds Expat and zlib statically into `OpenColorIO_2_4.dll`
at the versions above, so a Windows package needs their notices. Confirm the
actual Windows prefix used these versions; the stager checks the embedded zlib.

Before distributing a binary with this OCIO build, include the root notice and
this packet in readable package materials and verify their hashes against the
manifest. `_scripts/package_plus.py` copies this packet into `Notices` and
refuses a stage whose files do not match. The earlier private app stage has not
been modified to include them.
Whole-application notices and source obligations for Qt, FFmpeg, OpenCV, MDK,
codecs and other shipped components remain separate packaging checks.
