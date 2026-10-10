# Manual Qt signal-offset reproducer

This standalone executable isolates a failure in the pinned Qt binding. It
does not depend on Gyroflow rendering, FFmpeg, MDK, stabilization or OCIO.
It is a manual diagnostic, **not** part of the ordinary passing test suite.

The exact dependency is AdrianEddy/qmetaobject-rs at
`ff1e23dcdd722a0c335bbd51f7dcfdb722384db2`. Its QObject derive calculates a
signal field offset by forming `&(*null).field`. On the observed arm64 Mac
debug build, connecting one signal aborts with `null reference produced`.
The baseline prints `BEFORE_CONNECT` and does not reach `PASS`.

Use a configured Qt 6.7.3 development environment, including its `QMAKE`,
headers, libraries and runtime search paths, then run:

```sh
cargo run --locked --offline --manifest-path tests/qobject-signal-offset/Cargo.toml
```

The observed baseline uses Rust's debug checks; an optimized run that happens
to finish does not demonstrate that forming a null reference is safe.

## Downstream correction and retained baseline

`candidate.patch` changes only the generated offset calculation to
`std::mem::offset_of!`. Rust documents this macro as stable since 1.77;
Gyroflow's Rust 2024 edition already needs a newer toolchain. This does not
establish compatibility with every upstream qmetaobject consumer's older
toolchain. The root application now uses the retained upstream proc-macro snapshot in
`vendor/qmetaobject-rs/`, with this one-expression correction. The separate
manual workspace deliberately keeps the original Git dependency as a baseline;
it does not inherit the root application's Cargo patch.

To test it, copy the pinned upstream `qmetaobject_impl` crate into a private
directory and apply the patch there. Keep the cached/shared dependency source
unchanged. Add a **private** Cargo override for
`patch."https://github.com/AdrianEddy/qmetaobject-rs.git".qmetaobject_impl.path`
pointing to that copy, resolve a private lockfile, and run the same executable.
The expected result is one delivered callback, successful disconnect, no
second callback, and `PASS`. Do not edit the baseline lockfile or treat a
dependency override as proof that the canonical application adopted that private override; inspect
the root manifest and vendored pin for the actual source integration.

The observed private candidate passes that test with the same executable
source. A current OCIO app using that candidate and a settings-directory
test seam also completed the scoped PNG/EXR cases described in
[the integration notes](../../docs/OPENCOLORIO-INTEGRATION.md). The app's
production rendering sources were unchanged. The source integration and app follow-through are recorded in the integration
notes. Current Windows and the entire upstream binding suite remain unverified.

The copied upstream MIT notice is retained in `UPSTREAM-LICENSE`. Source:
[pinned offset implementation](https://github.com/AdrianEddy/qmetaobject-rs/blob/ff1e23dcdd722a0c335bbd51f7dcfdb722384db2/qmetaobject_impl/src/qobject_impl.rs#L901),
[Rust field-offset macro](https://doc.rust-lang.org/std/mem/macro.offset_of.html).


## Pinned upstream signal tests

`tests/upstream_signals.rs` preserves three test functions verbatim from the
same pinned upstream revision, with their MIT header:

- `connect_rust_signal`: two distinct typed signals, argument delivery and
  disconnect behavior.
- `connect_cpp_signal`: an existing C++ QObject signal.
- `with_life_time`: compilation of QObject derives with lifetime/type parameters;
  this upstream test does not instantiate those generic objects.

Run this additional manual diagnostic with the same configured Qt environment:

```sh
cargo test --locked --offline --manifest-path tests/qobject-signal-offset/Cargo.toml --test upstream_signals -- --test-threads=1
```

On the observed baseline, the C++ signal test passes and the Rust typed-signal
test aborts with `null reference produced`; Cargo exits 101. With the existing
private `qmetaobject_impl` override, all three tests pass, with zero failed,
ignored or filtered tests. The test functions are byte-identical between the
observed baseline and candidate. This adds typed-signal and generic compilation
coverage; it does not establish the entire upstream suite, instantiated generic
signal delivery or Windows acceptance. The baseline diagnostic remains outside
the normal passing suite and the original Git baseline remains separate from the patched application.
