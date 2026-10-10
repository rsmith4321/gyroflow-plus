#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-point the Windows native notices at the slim Gyroflow+ FFmpeg bundle.

The slim bundle (docs/WINDOWS-FFMPEG-SLIM.md) is built from the same BtbN and
FFmpeg pins as the full BtbN bundle, so its components are a subset of the
rows already recorded in ffmpeg/provenance/ffmpeg-components.tsv and their
notice texts are already in the tree. This script:

- keeps only the component rows (and notice directories) the slim build links;
- keeps the Rust crates rav1e links (cargo tree at its pin) or whose source
  paths are embedded in the slim DLLs, adding notice texts for linked crates
  the full-bundle scan missed;
- records the slim archive, its DLL hashes and its configuration;
- replaces the seven staged FFmpeg DLL entries with the slim archive members;
- rewrites MANIFEST.json member, component and gap records to match.

Standard library only. Run from the repository root:
  python3 -I _scripts/notices/slim_ffmpeg_notices.py --zip <slim.zip>
      --url <where the archive is kept> --buildconf <buildconf.txt>
      --rav1e-linked <crate-version list> --add-crates <dir> --add-crates-json <json>
Then run verify_native_notices.py and update the README pin.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path("resources/notices/native/windows-x64")
FF = ROOT / "ffmpeg"
PROV = FF / "provenance"
# Rows of ffmpeg-components.tsv the slim build compiles in (or is built by).
KEEP_ROWS = {
    "ffmpeg", "btbn-ffmpeg-builds", "mingw-std-threads", "mingw-w64", "gcc", "rust-std",
    "zlib", "vmaf", "vulkan-headers", "vulkan-shim-loader", "shaderc", "glslang",
    "spirv-tools", "spirv-headers-shaderc", "abseil-cpp-shaderc", "re2-shaderc",
    "spirv-cross", "spirv-headers", "amf", "aom", "dav1d", "nv-codec-headers",
    "libvpl", "rav1e", "svt-av1", "x264", "x265",
}
# Vendored or registry source paths left in panic messages; on the full bundle
# this reproduces the 87 crates in ffmpeg-dll-embedded-rust-crate-paths.tsv.
CRATE_PATH = re.compile(rb"[/\\](?:vendor|registry[/\\]src[/\\][^/\\]+)[/\\]"
                        rb"([A-Za-z0-9_\-]+?-\d+\.\d+\.\d+[A-Za-z0-9.+\-]*)[/\\]")
REMOVED_PROVENANCE = ["librsvg-Cargo.lock.txt"]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--buildconf", required=True)
    parser.add_argument("--rav1e-linked", required=True,
                        help="name-version per line: cargo tree -e normal,no-proc-macro at rav1e's pin")
    parser.add_argument("--add-crates", required=True, help="directory of <crate-version>/ notice files")
    parser.add_argument("--add-crates-json", required=True, help="confirmation records for --add-crates")
    args = parser.parse_args()

    archive = Path(args.zip).read_bytes()
    zf = zipfile.ZipFile(io.BytesIO(archive))
    dlls = {Path(n).name: zf.read(n) for n in zf.namelist()
            if n.split("/")[-2:-1] == ["bin"] and n.endswith(".dll")}
    exes = {Path(n).name: zf.read(n) for n in zf.namelist()
            if n.split("/")[-2:-1] == ["bin"] and n.endswith(".exe")}
    top = zf.namelist()[0].split("/")[0]
    manifest = json.loads((ROOT / "MANIFEST.json").read_text())
    staged_ff = [s for s in manifest["staged_inventory"] if s["component"] == "ffmpeg"]
    if sorted(s["path"] for s in staged_ff) != sorted(dlls):
        raise SystemExit(f"Slim DLL names differ from the staged FFmpeg names: {sorted(dlls)}")

    # Component rows and their notice directories.
    tsv = (PROV / "ffmpeg-components.tsv").read_text().splitlines()
    header, rows = tsv[0], [line.split("\t") for line in tsv[1:]]
    names = {row[0] for row in rows}
    if KEEP_ROWS - names:
        raise SystemExit(f"Unknown component rows: {sorted(KEEP_ROWS - names)}")
    kept = [row for row in rows if row[0] in KEEP_ROWS]
    dropped = sorted(names - KEEP_ROWS)
    (PROV / "ffmpeg-components.tsv").write_text(
        "\n".join([header] + ["\t".join(row) for row in kept]) + "\n")
    keep_dirs = set()
    for row in kept:
        prefix = row[0] + "-"
        keep_dirs.update(d.name for d in (FF / "components").iterdir()
                         if d.name.startswith(prefix) and re.fullmatch(r"[0-9a-f]{12}|r\d+|v[\d.]+", d.name[len(prefix):]))
    for directory in (FF / "components").iterdir():
        if directory.name not in keep_dirs:
            shutil.rmtree(directory)

    # Rust crates embedded in the slim DLLs.
    embedded = {}
    for name, data in sorted(dlls.items()):
        for crate in sorted({m.group(1).decode() for m in CRATE_PATH.finditer(data)}):
            embedded.setdefault(crate, []).append(name)
    crates_dir = FF / "rust-crates"
    added = json.loads(Path(args.add_crates_json).read_text())
    for record in added:
        name = f"{record['crate']}-{record['version']}"
        shutil.copytree(Path(args.add_crates) / name, crates_dir / name)
    linked = {line.strip() for line in Path(args.rav1e_linked).read_text().splitlines() if line.strip()}
    # rav1e itself and its ivf workspace member are covered by the rav1e component.
    linked -= {"rav1e-0.8.0", "ivf-0.1.4"}
    present = {d.name for d in crates_dir.iterdir()}
    wanted = linked | set(embedded)
    missing = sorted(wanted - present)
    if missing:
        raise SystemExit(f"Linked or embedded crates without notices: {missing}")
    for crate in sorted(present - wanted):
        shutil.rmtree(crates_dir / crate)
    (PROV / "ffmpeg-dll-embedded-rust-crate-paths.tsv").write_text(
        "".join(f"{dll}\t{crate}\n" for crate, found in sorted(embedded.items()) for dll in found))
    confirmed = json.loads((PROV / "ffmpeg-rust-crates-confirmed.json").read_text()) + added
    confirmed = sorted((r for r in confirmed if f"{r['crate']}-{r['version']}" in wanted),
                       key=lambda r: (r["crate"], r["version"]))
    (PROV / "ffmpeg-rust-crates-confirmed.json").write_text(json.dumps(confirmed, indent=1) + "\n")
    for removed in REMOVED_PROVENANCE:
        (PROV / removed).unlink(missing_ok=True)

    # Archive member hashes and configuration of the slim build.
    (PROV / "ffmpeg-archive-bin-sha256.tsv").write_text("".join(
        f"{sha256(data)}\t{len(data)}\tbin/{name}\n" for name, data in sorted({**dlls, **exes}.items())))
    avutil = dlls["avutil-61.dll"]
    match = re.search(rb"--prefix=[^\x00]*", avutil)
    if not match:
        raise SystemExit("No configuration string in avutil-61.dll")
    configuration = match.group(0).decode()
    (PROV / "ffmpeg-configuration-from-avutil-61.txt").write_text(configuration + "\n")
    buildconf = Path(args.buildconf).read_text()
    (PROV / "ffmpeg-buildconf-relayed-flags.txt").write_text(buildconf if buildconf.endswith("\n") else buildconf + "\n")
    enabled = sorted(flag for flag in configuration.split() if flag.startswith("--enable-"))

    provenance = json.loads((FF / "PROVENANCE.json").read_text())
    full_archive = provenance["archive"]
    provenance["component"] = "FFmpeg (Gyroflow+ slim build of BtbN win64 gpl-shared)"
    provenance["archive"] = {
        "url": args.url,
        "name": top + ".zip",
        "bytes": len(archive),
        "sha256": sha256(archive),
        "built_by": ".github/workflows/windows-ffmpeg-slim.yml with _scripts/ffmpeg-windows/slim-btbn.sh and slim.pin",
        "pinned_in_public_source": "common.just (pin) and windows.just (download and hash check)",
        "bin_member_hashes": "provenance/ffmpeg-archive-bin-sha256.tsv",
    }
    provenance["replaces_archive"] = full_archive
    provenance["configure_enable_flags"] = enabled
    provenance.pop("owner_observations", None)
    provenance["components"] = {
        "rows": len(kept), "collected": len(kept), "gaps": 0,
        "index": "provenance/ffmpeg-components.tsv (slim subset of v3 rows at the same pins)",
        "dropped_with_the_full_bundle": dropped,
    }
    provenance.pop("rust_crates_confirmed_in_avcodec", None)
    provenance["rust_crates"] = {
        "count": len(wanted),
        "embedded_paths_in_slim_dlls": len(embedded),
        "basis": ("rav1e 31435de9 links these crates (cargo tree -e normal,no-proc-macro --target "
                  "x86_64-pc-windows-gnu --features capi, default features on, at rav1e's Cargo.lock); "
                  "the full-bundle scan of embedded source paths found only some of them, so "
                  f"{len(added)} notice sets were added from the checksum-verified .crate files"),
        "records": "provenance/ffmpeg-rust-crates-confirmed.json",
    }
    gaps = [g for g in provenance.get("gaps", []) if g["id"] != "ffmpeg-texts"]
    for gap in gaps:
        if gap["id"] == "ffmpeg-source":
            gap["text"] = ("GPL-3.0-or-later build: the corresponding source of FFmpeg 46d8f462, the BtbN "
                           "9acad4a9 build scripts, the Gyroflow+ trim script and every statically linked "
                           f"dependency at its pin ({len(kept)} rows) must accompany or be offered with the package.")
    provenance["gaps"] = gaps
    (FF / "PROVENANCE.json").write_text(json.dumps(provenance, indent=1) + "\n")

    # Manifest: members, component record, staged inventory.
    component = manifest["components"]["ffmpeg"]
    component["name"] = provenance["component"]
    component["identity"] = {"archive_sha256": sha256(archive), "archive_bytes": len(archive),
                             "ffmpeg_commit": provenance["ffmpeg_commit"],
                             "btbn_commit": provenance["btbn_commit"],
                             "replaces_archive_sha256": full_archive["sha256"]}
    release = component["release_provenance"]
    release["gaps"] = [g for g in release["gaps"] if g["id"] != "ffmpeg-texts"]
    for gap in release["gaps"]:
        if gap["id"] == "ffmpeg-source":
            gap["text"] = next(g["text"] for g in gaps if g["id"] == "ffmpeg-source")
    release["resolved"] = [r for r in release["resolved"] if r["id"] != "ffmpeg-staged"]
    release["resolved"].insert(0, {
        "id": "ffmpeg-staged", "class": "resolved",
        "text": "All 7 staged FFmpeg DLL entries are the slim archive members byte for byte "
                "(ffmpeg/provenance/ffmpeg-archive-bin-sha256.tsv)."})
    release["resolved"].append({
        "id": "ffmpeg-texts-slim", "class": "resolved",
        "text": f"The slim build compiles in {len(kept)} recorded rows, all with notice texts at their pins. "
                "xvidcore and the other dropped components are no longer shipped: " + ", ".join(dropped) + "."})
    release["status"] = "INCOMPLETE" if any(g["class"] in ("blocker", "obligation") for g in release["gaps"]) else "COMPLETE"

    for entry in staged_ff:
        data = dlls[entry["path"]]
        entry["bytes"], entry["sha256"] = len(data), sha256(data)
        entry["mapping_basis"] = "bytes equal the pinned slim archive member (ffmpeg/provenance/ffmpeg-archive-bin-sha256.tsv)"
    manifest["staged_inventory_source"]["ffmpeg_entries"] = (
        "The 7 FFmpeg entries are the slim archive members, not the frozen stage's BtbN DLLs; "
        "a stage built from the current pin has these bytes.")

    old = {m["path"]: m for m in manifest["members"]}
    members = []
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name != "MANIFEST.json"):
        rel = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        member = dict(old.get(rel) or {"path": rel, "component": "ffmpeg",
                                       "role": "provenance" if rel.startswith("ffmpeg/provenance/") else "notice"})
        member["bytes"], member["sha256"] = len(data), sha256(data)
        members.append(member)
    manifest["members"] = members
    present_paths = {m["path"] for m in members}
    component["notice_members"] = [p for p in component["notice_members"] if p in present_paths]
    component["provenance_members"] = [p for p in component["provenance_members"] if p in present_paths]
    listed = set(component["notice_members"]) | set(component["provenance_members"])
    for m in members:
        if m["component"] == "ffmpeg" and m["path"] not in listed:
            (component["provenance_members"] if m["role"] == "provenance" else component["notice_members"]).append(m["path"])
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"rows_kept": len(kept), "rows_dropped": len(dropped),
                      "crates_kept": len(wanted), "crates_added": len(added),
                      "crates_removed": len(present - wanted),
                      "archive_sha256": sha256(archive), "members": len(members)}, indent=1))


if __name__ == "__main__":
    main()
