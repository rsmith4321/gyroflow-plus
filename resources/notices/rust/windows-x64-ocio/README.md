# Windows Rust dependency notices

This retained packet was generated from application commit
`0b5ba007bfad303f88c143615a9d2baf384de4cb` by the reviewed notice recipe.
Its original receipt and text are unchanged. It selects Windows x64, disables
default features, and enables `opencv,ocio-runtime`. The selected runtime graph
contains 331 crates and excludes the optional Breakpad dependency.

The collected notice text is deliberately overinclusive: it also retains build
dependencies. Its historical heading does not mean every listed crate is present
in the final executable. The linked-crate list records the selected runtime graph.
Canonical SPDX text and additional upstream notices are identified in the packet.

For application source `ab680a27d75d1f109e92935b360c33e2d421758b`, Cargo.toml
and Cargo.lock match the original receipt byte for byte, with the same target and
features. This packet is reused on that basis; it was not regenerated from the
later source. `REUSE.json` records the hashes and the unchanged original receipt.
Recheck those inputs before reusing it for a different build.

Include this directory alongside the native dependency notices when preparing
a Windows package. It does not replace Qt, FFmpeg and codecs, OpenCV, MDK,
OpenColorIO, Microsoft runtime notices, or corresponding-source obligations.
This directory contains notice material, not a portable application or a public
release approval. The notice recipe is in `_scripts/notices/`.

Reviewed upstream notice bytes, including their original whitespace and line
endings, are retained exactly. The local attributes disable newline conversion.
