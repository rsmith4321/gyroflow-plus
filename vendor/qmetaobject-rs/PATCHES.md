# Pinned Qt derive dependency

This directory retains the `qmetaobject_impl` crate, README and MIT license from
AdrianEddy/qmetaobject-rs at `ff1e23dcdd722a0c335bbd51f7dcfdb722384db2`.
`UPSTREAM.json` records each original and retained file hash.

The only upstream source change is in `src/qobject_impl.rs`: QObject signal
lookup uses `std::mem::offset_of!` rather than forming `&(*null).field`.
The standard macro computes the actual Rust field offset without a null
reference. Signal indexes, signatures, layout and delivery code are unchanged.
Generated consumer code needs Rust 1.77 or newer; Gyroflow's Rust 2024 edition
already requires Rust 1.85 or newer. No older upstream-consumer support is claimed.

The root Cargo patch replaces only this proc-macro crate. `qmetaobject` and
`qttypes` still use the original pinned Git revision; all other lockfile
packages keep their prior identities. This is a small downstream correction,
not an upstream release. The original baseline remains reproducible through
the separate manual workspace in `tests/qobject-signal-offset/`.

The source retains its original headers. Distribution stages include this
MIT license, patch description and pin record; the complete vendored source is
included in the corresponding Git source archive.
