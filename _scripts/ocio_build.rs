// SPDX-License-Identifier: GPL-3.0-or-later
// Shared app/fixture build configuration. The caller checks the Cargo feature.
pub fn build_bridge(repository: &std::path::Path) {
    use std::{env, path::PathBuf};
    for name in ["OCIO_ROOT", "OCIO_LINK_NAME", "OCIO_RPATH"] {
        println!("cargo:rerun-if-env-changed={name}");
    }
    let root = PathBuf::from(
        env::var("OCIO_ROOT")
            .expect("ocio-runtime requires a pinned OpenColorIO 2.4.2 install prefix in OCIO_ROOT"),
    );
    let source = repository.join("src/rendering/ocio");
    for file in ["grade.hpp", "bridge.h", "bridge.cpp"] {
        println!("cargo:rerun-if-changed={}", source.join(file).display());
    }
    let mut config = cc::Build::new();
    config
        .cpp(true)
        .std("c++17")
        .include(root.join("include"))
        .file(source.join("bridge.cpp"));
    if env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc") {
        // OCIO errors must unwind C++ objects before the C ABI catches them.
        config.flag("/EHsc");
        // The bridge uses dllimport declarations; a static OCIO prefix would need
        // OpenColorIO_SKIP_IMPORTS and its private dependencies at link time.
        let dll = root.join("bin/OpenColorIO_2_4.dll");
        assert!(dll.is_file(), "ocio-runtime on MSVC requires a shared OpenColorIO 2.4.2 prefix: {} is missing", dll.display());
    }
    config.compile("gyroflow_ocio_bridge");
    println!(
        "cargo:rustc-link-search=native={}",
        root.join("lib").display()
    );
    println!(
        "cargo:rustc-link-lib={}",
        env::var("OCIO_LINK_NAME").unwrap_or("OpenColorIO".into())
    );
    if env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos")
        || env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux")
    {
        // Development builds find the prepared prefix. Portable builds can
        // instead resolve the same library inside their packaged runtime.
        let rpath = match env::var_os("OCIO_RPATH") {
            None => root.join("lib").to_string_lossy().into_owned(),
            Some(value) => value.into_string().expect("OCIO_RPATH must be UTF-8"),
        };
        // The compiler driver splits -Wl, at each comma.
        assert!(!rpath.is_empty() && !rpath.contains(['\r', '\n', ',']),
            "OCIO_RPATH must be a non-empty runtime library path without commas or line breaks");
        println!(
            "cargo:rustc-link-arg=-Wl,-rpath,{}",
            rpath
        );
    }
}
