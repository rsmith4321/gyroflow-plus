// SPDX-License-Identifier: GPL-3.0-or-later

use std::{ffi::OsString, io, path::{Path, PathBuf}};

/// Resolve an explicitly selected profile without consulting the normal user profile.
/// Invalid overrides fail rather than silently using the user's saved settings.
pub fn from_override(value: Option<OsString>) -> io::Result<Option<PathBuf>> {
    let Some(value) = value else { return Ok(None); };
    let path = PathBuf::from(value);
    if !path.is_absolute() {
        return Err(io::Error::new(io::ErrorKind::InvalidInput,
            "GYROGRADE_DATA_DIR must be a nonempty absolute directory path"));
    }
    std::fs::create_dir_all(path.join("lens_profiles"))?;
    Ok(Some(path))
}

/// Give a new profile the settings and lens profiles saved under the app's previous name,
/// a sibling folder. Runs only while the new profile does not exist; the old one is left as is.
pub fn adopt_previous(path: &Path, previous_name: &str) {
    let Some(old) = path.parent().map(|parent| parent.join(previous_name)) else { return; };
    if path.exists() || !old.join("settings.json").is_file() { return; }
    if let Err(e) = copy_profile(&old, path) {
        ::log::error!("Failed to copy settings from {old:?} to {path:?}: {e:?}");
    }
}

fn copy_profile(old: &Path, path: &Path) -> io::Result<()> {
    std::fs::create_dir_all(path)?;
    std::fs::copy(old.join("settings.json"), path.join("settings.json"))?;
    if old.join("lens_profiles").is_dir() { copy_dir(&old.join("lens_profiles"), &path.join("lens_profiles"))?; }
    Ok(())
}

fn copy_dir(from: &Path, to: &Path) -> io::Result<()> {
    std::fs::create_dir_all(to)?;
    for entry in std::fs::read_dir(from)? {
        let entry = entry?;
        let target = to.join(entry.file_name());
        if entry.file_type()?.is_dir() { copy_dir(&entry.path(), &target)?; } else { std::fs::copy(entry.path(), target)?; }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    struct Scratch(PathBuf);
    impl Scratch {
        fn new() -> Self {
            static NEXT: AtomicUsize = AtomicUsize::new(0);
            let id = NEXT.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!("gyroflow-profile-test-{}-{}-{id}",
                std::process::id(), std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
            std::fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Scratch {
        fn drop(&mut self) { let _ = std::fs::remove_dir_all(&self.0); }
    }

    #[test]
    fn unset_preserves_default_selection() {
        assert_eq!(from_override(None).unwrap(), None);
    }

    #[test]
    fn empty_and_relative_paths_fail_before_creating_anything() {
        for value in ["", "profile", "../profile"] {
            assert_eq!(from_override(Some(value.into())).unwrap_err().kind(), io::ErrorKind::InvalidInput);
        }
        #[cfg(windows)]
        for value in [r"C:profile", r"\profile"] {
            assert_eq!(from_override(Some(value.into())).unwrap_err().kind(), io::ErrorKind::InvalidInput);
        }
    }

    #[test]
    fn absolute_profile_creates_lens_directory_and_keeps_existing_settings() {
        let scratch = Scratch::new();
        let profile = scratch.0.join("profile with spaces & [brackets]");
        assert_eq!(from_override(Some(profile.clone().into_os_string())).unwrap(), Some(profile.clone()));
        assert!(profile.join("lens_profiles").is_dir());
        let settings = profile.join("settings.json");
        std::fs::write(&settings, b"saved user grade").unwrap();
        from_override(Some(profile.into_os_string())).unwrap();
        assert_eq!(std::fs::read(settings).unwrap(), b"saved user grade");
    }

    #[test]
    fn file_in_place_of_profile_or_lens_directory_fails_without_truncation() {
        let scratch = Scratch::new();
        let file = scratch.0.join("profile-file");
        std::fs::write(&file, b"preserve").unwrap();
        assert!(from_override(Some(file.clone().into_os_string())).is_err());
        assert_eq!(std::fs::read(&file).unwrap(), b"preserve");
        let profile = scratch.0.join("profile");
        std::fs::create_dir(&profile).unwrap();
        let lens = profile.join("lens_profiles");
        std::fs::write(&lens, b"preserve lens").unwrap();
        assert!(from_override(Some(profile.into_os_string())).is_err());
        assert_eq!(std::fs::read(lens).unwrap(), b"preserve lens");
    }

    #[test]
    fn renamed_profile_copies_previous_settings_once() {
        let scratch = Scratch::new();
        let old = scratch.0.join("Gyroflow Plus");
        std::fs::create_dir_all(old.join("lens_profiles").join("user")).unwrap();
        std::fs::write(old.join("settings.json"), b"saved user grade").unwrap();
        std::fs::write(old.join("lens_profiles").join("user").join("lens.json"), b"lens").unwrap();
        let new = scratch.0.join("GyroGrade");
        adopt_previous(&new, "Gyroflow Plus");
        assert_eq!(std::fs::read(new.join("settings.json")).unwrap(), b"saved user grade");
        assert_eq!(std::fs::read(new.join("lens_profiles").join("user").join("lens.json")).unwrap(), b"lens");
        std::fs::write(new.join("settings.json"), b"changed later").unwrap();
        adopt_previous(&new, "Gyroflow Plus");
        assert_eq!(std::fs::read(new.join("settings.json")).unwrap(), b"changed later");
        assert_eq!(std::fs::read(old.join("settings.json")).unwrap(), b"saved user grade");
    }

    #[test]
    fn renamed_profile_without_previous_settings_stays_absent() {
        let scratch = Scratch::new();
        std::fs::create_dir(scratch.0.join("Gyroflow Plus")).unwrap();
        let new = scratch.0.join("GyroGrade");
        adopt_previous(&new, "Gyroflow Plus");
        assert!(!new.exists());
    }

    #[cfg(unix)]
    #[test]
    fn non_utf8_path_is_not_silently_replaced() {
        use std::os::unix::ffi::OsStringExt;
        let scratch = Scratch::new();
        let profile = scratch.0.join(OsString::from_vec(b"profile-\xff".to_vec()));
        let result = from_override(Some(profile.clone().into_os_string()));
        // macOS filesystems reject invalid UTF-8; Linux commonly accepts it.
        // Either outcome must preserve the OS path rather than use a lossy name.
        match result {
            Ok(Some(path)) => {
                assert_eq!(path, profile);
                assert!(path.join("lens_profiles").is_dir());
            }
            Err(_) => assert!(!profile.exists()),
            Ok(None) => panic!("Explicit path silently selected the default profile"),
        }
        assert!(!scratch.0.join("profile-\u{fffd}").exists());
    }
}
