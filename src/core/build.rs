// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2023 Adrian <adrian.eddy at gmail>

#[path = "lens_db_input.rs"]
mod lens_db_input;

use lens_db_input::{ Mode, Outcome, Request };
use std::{ env, io::Read, path::PathBuf, time::Duration };

const LATEST_URL: &str = "https://github.com/gyroflow/lens_profiles/releases/latest/download/profiles.cbor.gz";

fn fetch(url: &str) -> Result<Box<dyn Read>, String> {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(120)))
        .build()
        .into();
    let response = agent.get(url).call().map_err(|e| format!("{url}: {e}"))?;
    Ok(Box::new(response.into_body().into_reader()))
}

fn truthy(name: &str) -> bool {
    env::var(name).map(|x| matches!(x.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes")).unwrap_or(false)
}

fn main() {
    // Lens profile database: `latest` (default) keeps the developer behaviour;
    // `pinned` is the explicit release/portable input checked against lens_profiles.pin.
    // Fresh downloads are gzip-decoded before publication, which never replaces an
    // existing file: a database another writer creates meanwhile is kept as is.
    // Cargo's --offline flag is not visible to build scripts; set GYROFLOW_BUILD_OFFLINE=1
    // (or CARGO_NET_OFFLINE=true in the environment) to forbid this script's network access.
    for name in ["GYROFLOW_LENS_PROFILES", "GYROFLOW_LENS_PROFILES_FILE", "GYROFLOW_BUILD_OFFLINE", "CARGO_NET_OFFLINE"] {
        println!("cargo:rerun-if-env-changed={name}");
    }
    let project_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let pin_path = project_dir.join("lens_profiles.pin");
    let destination = project_dir.join("../../resources/camera_presets/profiles.cbor.gz");
    for path in [project_dir.join("build.rs"), project_dir.join("lens_db_input.rs"), pin_path.clone()] {
        println!("cargo:rerun-if-changed={}", path.display());
    }

    let mode = lens_db_input::parse_mode(env::var("GYROFLOW_LENS_PROFILES").ok().as_deref()).unwrap_or_else(|e| panic!("{e}"));
    let pin = match mode {
        Mode::Pinned => Some(std::fs::read_to_string(&pin_path)
            .map_err(|e| format!("Cannot read {}: {e}", pin_path.display()))
            .and_then(|text| lens_db_input::parse_pin(&text))
            .unwrap_or_else(|e| panic!("{e}"))),
        Mode::Latest => None,
    };
    let supplied = env::var_os("GYROFLOW_LENS_PROFILES_FILE").filter(|x| !x.is_empty()).map(PathBuf::from);
    let request = Request {
        mode, destination: &destination, pin: pin.as_ref(), supplied: supplied.as_deref(),
        offline: truthy("GYROFLOW_BUILD_OFFLINE") || truthy("CARGO_NET_OFFLINE"),
        latest_url: LATEST_URL,
    };
    let resolved = lens_db_input::resolve(&request, &mut fetch);
    // Watch the database only once it exists: Cargo treats a missing rerun-if-changed
    // path as always stale, which would rerun this script (and retry the fetch) and
    // rebuild this crate on every build while the database is unavailable.
    if destination.is_file() {
        println!("cargo:rerun-if-changed={}", destination.display());
    }
    match resolved {
        Ok(Outcome::Unavailable { reason }) => {
            let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
            if matches!(target_os.as_str(), "android" | "ios") || env::var_os("CARGO_FEATURE_BUNDLE_LENS_PROFILES").is_some() {
                panic!("This build embeds the lens profile database, which is unavailable: {reason}");
            }
            println!("cargo:warning=Lens profile database not fetched: {reason}");
        }
        Ok(Outcome::Downloaded { url, sha256 }) if mode == Mode::Latest => {
            println!("cargo:warning=Fetched unpinned lens profile database {url} (SHA-256 {sha256})");
        }
        Ok(_) => { }
        Err(e) => panic!("{e}"),
    }
}
