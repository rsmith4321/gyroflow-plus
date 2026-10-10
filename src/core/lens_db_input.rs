// SPDX-License-Identifier: GPL-3.0-or-later
// Build-time lens profile database input, shared by build.rs. It has no Cargo
// or network code so every failure path can be tested offline.

use std::fs::{ self, OpenOptions };
use std::io::{ self, Read, Write };
use std::path::{ Path, PathBuf };
use std::sync::atomic::{ AtomicU32, Ordering };

/// The official database is about 1.5 MB; anything far larger is not it.
pub const MAX_BYTES: u64 = 64 << 20;
/// Bound on the decompressed size checked before publication (decompression bomb guard).
pub const MAX_DECOMPRESSED: u64 = 512 << 20;

#[derive(Debug, Clone, PartialEq)]
pub struct Pin { pub tag: String, pub url: String, pub sha256: String }

/// `key=value` lines; `#` comments. Kept trivial so build_plus.py parses it identically.
pub fn parse_pin(text: &str) -> Result<Pin, String> {
    let (mut tag, mut url, mut sha256) = (None, None, None);
    for line in text.lines().map(str::trim).filter(|x| !x.is_empty() && !x.starts_with('#')) {
        let (key, value) = line.split_once('=').ok_or_else(|| format!("Malformed lens profile pin line: {line:?}"))?;
        let slot = match key.trim() { "tag" => &mut tag, "url" => &mut url, "sha256" => &mut sha256,
                                      other => return Err(format!("Unknown lens profile pin key: {other:?}")) };
        if slot.replace(value.trim().to_string()).is_some() { return Err(format!("Duplicate lens profile pin key: {key:?}")); }
    }
    let pin = Pin { tag: tag.unwrap_or_default(), url: url.unwrap_or_default(), sha256: sha256.unwrap_or_default() };
    if pin.tag.is_empty() || !pin.url.starts_with("https://") || pin.url.contains("/latest/")
        || pin.sha256.len() != 64 || !pin.sha256.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
        return Err("Lens profile pin needs a tag, a versioned https url and a lowercase SHA-256".into());
    }
    Ok(pin)
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Mode { Latest, Pinned }

pub fn parse_mode(value: Option<&str>) -> Result<Mode, String> {
    match value.map(str::trim) {
        None | Some("") | Some("latest") => Ok(Mode::Latest),
        Some("pinned") => Ok(Mode::Pinned),
        Some(other) => Err(format!("GYROFLOW_LENS_PROFILES must be latest or pinned, not {other:?}")),
    }
}

#[derive(Debug, PartialEq)]
pub enum Outcome {
    /// Destination already present (and, when pinned, digest-equal). Includes a
    /// destination another writer published while this build was fetching.
    Existing { sha256: String },
    /// Published from GYROFLOW_LENS_PROFILES_FILE after verification.
    Supplied { sha256: String },
    /// Published from the network after the transfer completed, the gzip stream
    /// decoded and (when pinned) the digest matched.
    Downloaded { url: String, sha256: String },
    /// Latest mode only: nothing published; the reason becomes a cargo warning.
    Unavailable { reason: String },
}

/// Result of a no-clobber publication attempt.
#[derive(Debug, PartialEq)]
pub enum Publication {
    Published { sha256: String },
    /// Another writer created the destination first; it was left untouched.
    Lost,
}

pub struct Request<'a> {
    pub mode: Mode,
    pub destination: &'a Path,
    pub pin: Option<&'a Pin>,
    pub supplied: Option<&'a Path>,
    pub offline: bool,
    pub latest_url: &'a str,
}

pub type Fetch<'a> = dyn FnMut(&str) -> Result<Box<dyn Read>, String> + 'a;
/// Must create `to` atomically and fail with AlreadyExists if it exists.
pub type Link<'a> = dyn FnMut(&Path, &Path) -> io::Result<()> + 'a;

pub fn sha256_hex(data: &[u8]) -> String {
    hex(ring::digest::digest(&ring::digest::SHA256, data).as_ref())
}

fn hex(bytes: &[u8]) -> String { bytes.iter().map(|b| format!("{b:02x}")).collect() }

fn file_sha256(path: &Path) -> Result<String, String> {
    let mut data = Vec::new();
    fs::File::open(path).and_then(|f| f.take(MAX_BYTES + 1).read_to_end(&mut data))
        .map_err(|e| format!("Cannot read {}: {e}", path.display()))?;
    if data.len() as u64 > MAX_BYTES { return Err(format!("{} exceeds {MAX_BYTES} bytes", path.display())); }
    Ok(sha256_hex(&data))
}

/// Decode the first gzip member exactly as the app does
/// (`lens_profile_database.rs` uses `flate2::read::GzDecoder`), so a truncated
/// stream, a bad CRC-32/ISIZE trailer or corrupt deflate data is refused.
/// Only gzip integrity is checked, not the CBOR contents.
pub fn validate_gzip(path: &Path, max_decompressed: u64) -> Result<u64, String> {
    let file = fs::File::open(path).map_err(|e| format!("Cannot read {}: {e}", path.display()))?;
    let mut decoder = flate2::read::GzDecoder::new(file).take(max_decompressed + 1);
    let size = io::copy(&mut decoder, &mut io::sink()).map_err(|e| format!("Lens profile input is not a complete gzip stream: {e}"))?;
    if size > max_decompressed { return Err(format!("Lens profile input decompresses beyond {max_decompressed} bytes")); }
    Ok(size)
}

fn temp_path(destination: &Path) -> Result<PathBuf, String> {
    static COUNTER: AtomicU32 = AtomicU32::new(0);
    let dir = destination.parent().ok_or("Lens profile destination has no parent directory")?;
    let name = destination.file_name().unwrap_or_default().to_string_lossy();
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    Ok(dir.join(format!(".{name}.partial-{}-{nanos}-{}", std::process::id(), COUNTER.fetch_add(1, Ordering::Relaxed))))
}

/// Production no-clobber primitive. `std::fs::hard_link` is link(2)/linkat on Unix
/// and CreateHardLinkW on Windows; both fail with AlreadyExists instead of
/// replacing, and both are atomic on local filesystems that support hard links.
pub fn hard_link_no_clobber(from: &Path, to: &Path) -> io::Result<()> { fs::hard_link(from, to) }

/// Stream into a fresh, uniquely named sibling file, check size bound, digest
/// (when pinned) and full gzip decode, then publish without ever replacing an
/// existing destination. Only this call's own temp file is ever removed.
pub fn publish_with(destination: &Path, source: &mut dyn Read, expected: Option<&str>,
                    max_decompressed: u64, link: &mut Link) -> Result<Publication, String> {
    let dir = destination.parent().ok_or("Lens profile destination has no parent directory")?;
    fs::create_dir_all(dir).map_err(|e| format!("Cannot create {}: {e}", dir.display()))?;
    let temp = temp_path(destination)?;
    // create_new: never adopt (or later delete) a leftover or another writer's partial file.
    let mut file = OpenOptions::new().write(true).create_new(true).open(&temp)
        .map_err(|e| format!("Cannot create {}: {e}", temp.display()))?;
    let result = (|| -> Result<String, String> {
        let mut context = ring::digest::Context::new(&ring::digest::SHA256);
        let (mut total, mut buffer) = (0u64, vec![0u8; 64 * 1024]);
        let mut limited = source.take(MAX_BYTES + 1);
        loop {
            let n = limited.read(&mut buffer).map_err(|e| format!("Lens profile transfer failed after {total} bytes: {e}"))?;
            if n == 0 { break; }
            total += n as u64;
            if total > MAX_BYTES { return Err(format!("Lens profile input exceeds {MAX_BYTES} bytes")); }
            context.update(&buffer[..n]);
            file.write_all(&buffer[..n]).map_err(|e| format!("Cannot write {}: {e}", temp.display()))?;
        }
        let digest = hex(context.finish().as_ref());
        if let Some(expected) = expected {
            if digest != expected { return Err(format!("Lens profile SHA-256 {digest} does not match pinned {expected} ({total} bytes)")); }
        }
        file.sync_all().map_err(|e| format!("Cannot flush {}: {e}", temp.display()))?;
        // A clean EOF can still be a short body; only a full decode proves completeness.
        validate_gzip(&temp, max_decompressed).map_err(|e| format!("{e} ({total} bytes received)"))?;
        Ok(digest)
    })();
    drop(file); // Close before link/remove; required on some Windows sharing modes.
    let outcome = match result {
        Ok(sha256) => match link(&temp, destination) {
            Ok(()) => Ok(Publication::Published { sha256 }),
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => Ok(Publication::Lost),
            Err(e) => Err(format!("No-clobber publication of {} failed ({e}); hard links may be unsupported on this \
                                   filesystem. Nothing was published; use a filesystem that supports hard links, or prepopulate a matching database in a fresh build tree.",
                                  destination.display())),
        },
        Err(e) => Err(e),
    };
    // The destination (if published) is a second link to the same data.
    let _ = fs::remove_file(&temp);
    outcome
}

pub fn resolve(request: &Request, fetch: &mut Fetch) -> Result<Outcome, String> {
    resolve_with(request, fetch, &mut hard_link_no_clobber)
}

pub fn resolve_with(request: &Request, fetch: &mut Fetch, link: &mut Link) -> Result<Outcome, String> {
    let destination = request.destination;
    let publish = |source: &mut dyn Read, expected: Option<&str>, link: &mut Link| publish_with(destination, source, expected, MAX_DECOMPRESSED, link);
    match request.mode {
        Mode::Latest => {
            if request.supplied.is_some() { return Err("GYROFLOW_LENS_PROFILES_FILE requires GYROFLOW_LENS_PROFILES=pinned".into()); }
            // Unchanged developer behaviour: an existing database is reused as is (not re-validated).
            if destination.exists() { return Ok(Outcome::Existing { sha256: file_sha256(destination)? }); }
            if request.offline { return Ok(Outcome::Unavailable { reason: "offline build".into() }); }
            let url = request.latest_url;
            match fetch(url).and_then(|mut body| publish(&mut *body, None, link)) {
                Ok(Publication::Published { sha256 }) => Ok(Outcome::Downloaded { url: url.into(), sha256 }),
                // Another writer won; latest mode reuses whatever is there, as before.
                Ok(Publication::Lost) => Ok(Outcome::Existing { sha256: file_sha256(destination)? }),
                Err(reason) => Ok(Outcome::Unavailable { reason }),
            }
        }
        Mode::Pinned => {
            let pin = request.pin.ok_or("Pinned lens profiles require src/core/lens_profiles.pin")?;
            if let Some(supplied) = request.supplied {
                let sha256 = file_sha256(supplied)?;
                if sha256 != pin.sha256 { return Err(format!("{} SHA-256 {sha256} does not match pinned {} ({})", supplied.display(), pin.sha256, pin.tag)); }
            }
            let existing = || -> Result<Outcome, String> {
                let sha256 = file_sha256(destination)?;
                if sha256 == pin.sha256 { return Ok(Outcome::Existing { sha256 }); }
                // Never overwrite a developer's database implicitly.
                Err(format!("{} has SHA-256 {sha256}, not pinned {} ({}); move it aside for a pinned build",
                            destination.display(), pin.sha256, pin.tag))
            };
            if destination.exists() { return existing(); }
            let published = if let Some(supplied) = request.supplied {
                let mut file = fs::File::open(supplied).map_err(|e| format!("Cannot read {}: {e}", supplied.display()))?;
                publish(&mut file, Some(&pin.sha256), link)?
            } else {
                if request.offline {
                    return Err(format!("Offline pinned build: supply GYROFLOW_LENS_PROFILES_FILE for {} ({})", pin.tag, pin.sha256));
                }
                let mut body = fetch(&pin.url)?;
                publish(&mut *body, Some(&pin.sha256), link)?
            };
            match published {
                Publication::Published { sha256 } if request.supplied.is_some() => Ok(Outcome::Supplied { sha256 }),
                Publication::Published { sha256 } => Ok(Outcome::Downloaded { url: pin.url.clone(), sha256 }),
                // A concurrent writer's file is accepted only if it is the pinned one.
                Publication::Lost => existing(),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::io::Cursor;

    fn gzip(payload: &[u8]) -> Vec<u8> {
        let mut e = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        e.write_all(payload).unwrap();
        e.finish().unwrap()
    }
    fn good() -> Vec<u8> { gzip(b"synthetic lens database bytes") }

    struct Scratch(PathBuf);
    impl Scratch {
        fn new(name: &str) -> Self {
            let dir = std::env::temp_dir().join(format!("lens-db-input-{name}-{}", std::process::id()));
            let _ = fs::remove_dir_all(&dir);
            fs::create_dir_all(&dir).unwrap();
            Self(dir)
        }
        fn destination(&self) -> PathBuf { self.0.join("camera_presets/profiles.cbor.gz") }
        fn leftovers(&self) -> Vec<String> {
            fs::read_dir(self.0.join("camera_presets")).map(|d| d.flatten()
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .filter(|n| n.contains(".partial-") && !n.contains("other-writer")).collect()).unwrap_or_default()
        }
    }
    impl Drop for Scratch { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); } }

    fn pin() -> Pin { Pin { tag: "v41".into(), url: "https://example.invalid/v41/profiles.cbor.gz".into(), sha256: sha256_hex(&good()) } }

    fn request<'a>(mode: Mode, destination: &'a Path, pin: Option<&'a Pin>) -> Request<'a> {
        Request { mode, destination, pin, supplied: None, offline: false, latest_url: "https://example.invalid/latest" }
    }

    fn serve<'a>(bytes: Vec<u8>, calls: &'a Cell<u32>) -> impl FnMut(&str) -> Result<Box<dyn Read>, String> + 'a {
        move |_| { calls.set(calls.get() + 1); Ok(Box::new(Cursor::new(bytes.clone())) as Box<dyn Read>) }
    }

    /// Delivers some bytes, then fails like a dropped connection.
    struct Broken(Vec<u8>);
    impl Read for Broken {
        fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
            if self.0.is_empty() { return Err(io::Error::new(io::ErrorKind::ConnectionReset, "reset")); }
            let n = self.0.len().min(buf.len()); buf[..n].copy_from_slice(&self.0[..n]); self.0.clear(); Ok(n)
        }
    }

    /// Creates the destination during the transfer, after resolve()'s exists() check.
    struct Racing { body: Cursor<Vec<u8>>, destination: PathBuf, competing: Vec<u8>, fired: bool }
    impl Read for Racing {
        fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
            if !std::mem::replace(&mut self.fired, true) { fs::write(&self.destination, &self.competing).unwrap(); }
            let n = buf.len().min(7); self.body.read(&mut buf[..n])
        }
    }
    fn racing<'a>(body: Vec<u8>, destination: &'a Path, competing: &'a [u8]) -> impl FnMut(&str) -> Result<Box<dyn Read>, String> + 'a {
        move |_| Ok(Box::new(Racing { body: Cursor::new(body.clone()), destination: destination.into(), competing: competing.into(), fired: false }) as Box<dyn Read>)
    }

    #[test]
    fn pin_parsing_rejects_mutable_or_malformed_pins() {
        let good = format!("# c\ntag=v41\nurl=https://github.com/gyroflow/lens_profiles/releases/download/v41/profiles.cbor.gz\nsha256={}\n", "a".repeat(64));
        assert!(parse_pin(&good).is_ok());
        assert!(parse_pin(&good.replace("download/v41", "latest/download")).is_err());
        assert!(parse_pin(&good.replace(&"a".repeat(64), &"A".repeat(64))).is_err());
        assert!(parse_pin(&good.replace("tag=v41\n", "")).is_err());
        assert!(parse_pin(&format!("{good}tag=v42\n")).is_err());
        assert!(parse_pin(&format!("{good}size=1\n")).is_err());
        assert!(parse_mode(Some("frozen")).is_err());
        assert_eq!(parse_mode(None), Ok(Mode::Latest));
    }

    #[test]
    fn pinned_download_verifies_then_publishes() {
        let s = Scratch::new("pinned-ok"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        let out = resolve(&request(Mode::Pinned, &d, Some(&p)), &mut serve(good(), &calls)).unwrap();
        assert_eq!(out, Outcome::Downloaded { url: p.url.clone(), sha256: p.sha256.clone() });
        assert_eq!(fs::read(&d).unwrap(), good());
        // A matching existing file is reused without network.
        assert_eq!(resolve(&request(Mode::Pinned, &d, Some(&p)), &mut serve(good(), &calls)).unwrap(), Outcome::Existing { sha256: p.sha256.clone() });
        assert_eq!(calls.get(), 1);
        assert!(s.leftovers().is_empty());
    }

    #[test]
    fn corrupt_download_is_refused_and_leaves_nothing() {
        let s = Scratch::new("corrupt"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        let err = resolve(&request(Mode::Pinned, &d, Some(&p)), &mut serve(gzip(b"different bytes"), &calls)).unwrap_err();
        assert!(err.contains("does not match pinned"), "{err}");
        assert!(!d.exists()); assert!(s.leftovers().is_empty());
    }

    #[test]
    fn transfer_error_is_refused_in_both_modes_and_leaves_nothing() {
        let s = Scratch::new("partial"); let (d, p) = (s.destination(), pin());
        let head = good()[..5].to_vec();
        let mut broken = |_: &str| Ok(Box::new(Broken(head.clone())) as Box<dyn Read>);
        let err = resolve(&request(Mode::Pinned, &d, Some(&p)), &mut broken).unwrap_err();
        assert!(err.contains("transfer failed after 5 bytes"), "{err}");
        assert!(!d.exists()); assert!(s.leftovers().is_empty());
        match resolve(&request(Mode::Latest, &d, None), &mut broken).unwrap() {
            Outcome::Unavailable { reason } => assert!(reason.contains("transfer failed"), "{reason}"),
            other => panic!("{other:?}"),
        }
        assert!(!d.exists()); assert!(s.leftovers().is_empty());
    }

    #[test]
    fn short_clean_eof_is_refused_in_both_modes() {
        // Pinned: the digest catches it. Latest: only the full gzip decode does (v1 published it).
        let s = Scratch::new("short"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        let full = gzip(&(0..4096u32).flat_map(|x| x.to_le_bytes()).collect::<Vec<_>>());
        let short = full[..full.len() / 2].to_vec();
        assert!(resolve(&request(Mode::Pinned, &d, Some(&p)), &mut serve(short.clone(), &calls)).unwrap_err().contains("does not match pinned"));
        match resolve(&request(Mode::Latest, &d, None), &mut serve(short, &calls)).unwrap() {
            Outcome::Unavailable { reason } => assert!(reason.contains("not a complete gzip stream"), "{reason}"),
            other => panic!("{other:?}"),
        }
        assert!(!d.exists()); assert!(s.leftovers().is_empty());
    }

    #[test]
    fn gzip_trailer_and_payload_damage_are_refused_in_latest_mode() {
        let s = Scratch::new("damage"); let (d, calls) = (s.destination(), Cell::new(0));
        let base = gzip(b"lens database payload");
        let mut crc = base.clone(); let i = crc.len() - 8; crc[i] ^= 0xff;     // CRC-32
        let mut isize = base.clone(); let i = isize.len() - 1; isize[i] ^= 0x01; // ISIZE
        let magic_only = b"\x1f\x8bnot actually gzip".to_vec();                     // v1 fixture shape
        for (name, bytes) in [("crc", crc), ("isize", isize), ("magic-only", magic_only), ("html", b"<html>rate limited</html>".to_vec())] {
            match resolve(&request(Mode::Latest, &d, None), &mut serve(bytes, &calls)).unwrap() {
                Outcome::Unavailable { reason } => assert!(reason.contains("gzip"), "{name}: {reason}"),
                other => panic!("{name}: {other:?}"),
            }
            assert!(!d.exists(), "{name}"); assert!(s.leftovers().is_empty(), "{name}");
        }
    }

    #[test]
    fn oversized_input_and_decompression_bombs_are_refused() {
        let s = Scratch::new("shape"); let d = s.destination();
        let mut huge = io::repeat(0x1f).take(MAX_BYTES + 10);
        assert!(publish_with(&d, &mut huge, None, MAX_DECOMPRESSED, &mut hard_link_no_clobber).unwrap_err().contains("exceeds"));
        let bomb = gzip(&vec![0u8; 1 << 20]);
        let err = publish_with(&d, &mut Cursor::new(bomb), None, 1 << 16, &mut hard_link_no_clobber).unwrap_err();
        assert!(err.contains("decompresses beyond"), "{err}");
        assert!(!d.exists()); assert!(s.leftovers().is_empty());
    }

    #[test]
    fn competing_destination_created_mid_transfer_is_never_replaced() {
        let s = Scratch::new("race"); let (d, p) = (s.destination(), pin());
        fs::create_dir_all(d.parent().unwrap()).unwrap();
        let other = d.parent().unwrap().join(".profiles.cbor.gz.partial-other-writer");
        fs::write(&other, b"another writer's partial").unwrap();
        // Pinned, different competing file: preserved, fail closed.
        let competing = gzip(b"developer's concurrent database");
        let err = resolve(&request(Mode::Pinned, &d, Some(&p)), &mut racing(good(), &d, &competing)).unwrap_err();
        assert!(err.contains("move it aside"), "{err}");
        assert_eq!(fs::read(&d).unwrap(), competing);
        // Latest: preserved and reused.
        fs::remove_file(&d).unwrap();
        let out = resolve(&request(Mode::Latest, &d, None), &mut racing(gzip(b"upstream latest"), &d, &competing)).unwrap();
        assert_eq!(out, Outcome::Existing { sha256: sha256_hex(&competing) });
        assert_eq!(fs::read(&d).unwrap(), competing);
        // Pinned, competing writer produced the pinned bytes too: accepted, untouched.
        fs::remove_file(&d).unwrap();
        let out = resolve(&request(Mode::Pinned, &d, Some(&p)), &mut racing(good(), &d, &good())).unwrap();
        assert_eq!(out, Outcome::Existing { sha256: p.sha256.clone() });
        assert_eq!(fs::read(&other).unwrap(), b"another writer's partial");
        assert!(s.leftovers().is_empty());
    }

    #[test]
    fn unsupported_no_clobber_link_fails_closed() {
        let s = Scratch::new("nolink"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        let mut unsupported = |_: &Path, _: &Path| Err(io::Error::new(io::ErrorKind::Unsupported, "hard links not supported"));
        let err = resolve_with(&request(Mode::Pinned, &d, Some(&p)), &mut serve(good(), &calls), &mut unsupported).unwrap_err();
        assert!(err.contains("Nothing was published"), "{err}");
        assert!(matches!(resolve_with(&request(Mode::Latest, &d, None), &mut serve(good(), &calls), &mut unsupported).unwrap(),
                         Outcome::Unavailable { .. }));
        assert!(!d.exists()); assert!(s.leftovers().is_empty());
    }

    #[test]
    fn offline_never_fetches() {
        let s = Scratch::new("offline"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        let mut r = request(Mode::Pinned, &d, Some(&p)); r.offline = true;
        assert!(resolve(&r, &mut serve(good(), &calls)).unwrap_err().contains("Offline pinned build"));
        let mut r = request(Mode::Latest, &d, None); r.offline = true;
        assert!(matches!(resolve(&r, &mut serve(good(), &calls)).unwrap(), Outcome::Unavailable { .. }));
        assert_eq!(calls.get(), 0); assert!(!d.exists());
    }

    #[test]
    fn supplied_input_is_verified_and_works_offline() {
        let s = Scratch::new("supplied"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        let missing = s.0.join("missing.cbor.gz");
        let mut r = request(Mode::Pinned, &d, Some(&p)); r.offline = true; r.supplied = Some(&missing);
        assert!(resolve(&r, &mut serve(good(), &calls)).unwrap_err().contains("Cannot read"));
        let wrong = s.0.join("wrong.cbor.gz"); fs::write(&wrong, gzip(b"wrong")).unwrap();
        r.supplied = Some(&wrong);
        assert!(resolve(&r, &mut serve(good(), &calls)).unwrap_err().contains("does not match pinned"));
        assert!(!d.exists());
        let right = s.0.join("right.cbor.gz"); fs::write(&right, good()).unwrap();
        r.supplied = Some(&right);
        assert_eq!(resolve(&r, &mut serve(good(), &calls)).unwrap(), Outcome::Supplied { sha256: p.sha256.clone() });
        assert_eq!(fs::read(&d).unwrap(), good());
        assert_eq!(fs::read(&right).unwrap(), good(), "supplied file untouched");
        assert_eq!(calls.get(), 0);
        let mut r = request(Mode::Latest, &d, None); r.supplied = Some(&right);
        assert!(resolve(&r, &mut serve(good(), &calls)).is_err());
    }

    #[test]
    fn pinned_mode_never_overwrites_a_different_existing_database() {
        let s = Scratch::new("existing"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        fs::create_dir_all(d.parent().unwrap()).unwrap(); fs::write(&d, b"\x1f\x8bdeveloper's newer db").unwrap();
        let err = resolve(&request(Mode::Pinned, &d, Some(&p)), &mut serve(good(), &calls)).unwrap_err();
        assert!(err.contains("move it aside"), "{err}");
        assert_eq!(fs::read(&d).unwrap(), b"\x1f\x8bdeveloper's newer db");
        // Latest mode keeps reusing whatever the developer has, as before (no re-validation).
        assert!(matches!(resolve(&request(Mode::Latest, &d, None), &mut serve(good(), &calls)).unwrap(), Outcome::Existing { .. }));
        assert_eq!(calls.get(), 0);
    }

    #[test]
    fn other_writers_temp_files_are_never_adopted_or_removed() {
        let s = Scratch::new("stale"); let (d, p, calls) = (s.destination(), pin(), Cell::new(0));
        fs::create_dir_all(d.parent().unwrap()).unwrap();
        let stale = d.parent().unwrap().join(format!(".profiles.cbor.gz.partial-{}", std::process::id()));
        fs::write(&stale, b"\x1f\x8bhalf").unwrap();
        assert!(matches!(resolve(&request(Mode::Pinned, &d, Some(&p)), &mut serve(good(), &calls)).unwrap(), Outcome::Downloaded { .. }));
        assert_eq!(fs::read(&stale).unwrap(), b"\x1f\x8bhalf");
        assert_eq!(fs::read(&d).unwrap(), good());
    }
}
