// SPDX-License-Identifier: GPL-3.0-or-later
#[path = "../../_scripts/ocio_build.rs"]
mod ocio_build;
fn main() {
    if std::env::var_os("CARGO_FEATURE_OCIO_RUNTIME").is_some() {
        ocio_build::build_bridge(&std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap()).join("../.."));
    }
}
