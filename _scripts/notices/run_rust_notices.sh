#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Task C rust-dependency-notices-v3: fail-fast notices generation for one shipped
# target set and an explicit Cargo feature selection. v2's runner with three
# additions: the feature selection is an argument (v2 hard-coded the default
# features plus ocio-runtime), crates that must be absent are checked in every
# graph and output, and each cargo step is time-bounded.
#
#   run_rust_notices.sh [--no-default-features] [--features a,b,dep/c] [--absent crate]...
#                       <checkout> <recipe-dir> <out-dir> <work-dir> <triple> [<triple> …]
#
# Windows: one triple (x86_64-pc-windows-msvc). Mac: aarch64-apple-darwin, plus
# x86_64-apple-darwin only for a lipo'd universal binary. Pass the same feature
# flags the release cargo build uses. Needs `cargo about` 0.9.2 on PATH, installed with:
#   cargo install cargo-about --version =0.9.2 --locked --features cli
# (the binary requires the `cli` feature; without it cargo builds and installs nothing).
# Crates must already be fetched (`cargo fetch --locked`); every step runs --frozen.
# STEP_TIMEOUT (seconds, default 300) bounds each cargo step.
# <out-dir> is what goes to package_plus.py --licenses. It receives no JSON:
# cargo-about's JSON and cargo metadata carry this machine's absolute paths and
# stay in <work-dir>.
set -euo pipefail

# This metadata collector is supported on Linux with Bash >=4.4 and GNU timeout.
# Do not reach array expansion on older Bash versions (including macOS /bin/bash).
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4) )); then
    echo 'need Bash 4.4 or newer; run this collector in the documented Linux environment' >&2
    exit 2
fi
command -v timeout >/dev/null || { echo 'need GNU timeout' >&2; exit 2; }

usage() { sed -n '9,22p' "$0" >&2; exit 2; }
nodefault=0; features=; absent=()
while [ $# -gt 0 ]; do
    case $1 in
        --no-default-features) nodefault=1; shift ;;
        --features) [ $# -ge 2 ] || usage; features=$2; shift 2 ;;
        --absent) [ $# -ge 2 ] || usage; absent+=("$2"); shift 2 ;;
        --*) usage ;;
        *) break ;;
    esac
done
[ $# -ge 5 ] || usage
repo=$(cd "$1" && pwd); recipe=$(cd "$2" && pwd); final=$3; work=$4; shift 4
# Everything is written to <out-dir>.partial and renamed only after the gate passes,
# so a failed run never leaves a directory that looks like notices.
out=$final.partial
[ ! -e "$final" ] && [ ! -e "$out" ] || { echo "refusing existing $final or $out" >&2; exit 2; }
[ -z "$(git -C "$repo" status --porcelain)" ] || { echo "checkout is not clean" >&2; exit 2; }
[ "$(cargo about --version)" = "cargo-about 0.9.2" ] || { echo "need cargo-about 0.9.2" >&2; exit 2; }
mkdir -p "$out" "$work"
out=$(cd "$out" && pwd); work=$(cd "$work" && pwd); final=$(dirname "$out")/$(basename "$final")
step() { timeout -k 10 "${STEP_TIMEOUT:-300}" "$@"; }

# One selection for every cargo command. cargo-about documents --features as a
# space-separated list; cargo accepts either.
sel=(); about_sel=()
[ $nodefault -eq 1 ] && { sel+=(--no-default-features); about_sel+=(--no-default-features); }
[ -n "$features" ] && { sel+=(--features "$features"); about_sel+=(--features "${features//,/ }"); }

targets=(); metadata=(); linked=()
for t in "$@"; do
    targets+=(--target "$t")
    # Raw output goes to a file first, so cargo's exit status is the step's status.
    (cd "$repo" && step cargo tree --frozen -e normal,no-proc-macro --target "$t" "${sel[@]}" \
        --prefix none --no-dedupe -f '{p}|{l}') > "$work/tree-$t.raw"
    sed 's/ (\*)$//' "$work/tree-$t.raw" | sort -u > "$work/linked-$t.txt"
    [ -s "$work/linked-$t.txt" ] || { echo "empty crate graph for $t" >&2; exit 1; }
    (cd "$repo" && step cargo metadata --frozen --format-version 1 --filter-platform "$t" "${sel[@]}") > "$work/metadata-$t.json"
    metadata+=(--metadata "$work/metadata-$t.json"); linked+=(--linked "$work/linked-$t.txt")
done

about=(step cargo about generate --frozen --fail --manifest-path "$repo/Cargo.toml" "${about_sel[@]}"
       "${targets[@]}" -c "$recipe/about.toml")
"${about[@]}" --format json -o "$work/cargo-about.json"
"${about[@]}" -o "$out/RUST-THIRD-PARTY-NOTICES.txt" "$recipe/rust-notices.txt.hbs"
[ -s "$out/RUST-THIRD-PARTY-NOTICES.txt" ] || { echo "empty notices text" >&2; exit 1; }

rc=0
python3 "$recipe/rust_notices_check.py" --about-json "$work/cargo-about.json" "${linked[@]}" \
    "${metadata[@]}" --supplement "$recipe/supplement.json" --out-dir "$out" > "$work/gate.log" || rc=$?
if [ $rc -ne 0 ]; then grep -v '^info:' "$work/gate.log" >&2; echo "gate failed ($rc); do not ship $out" >&2; exit $rc; fi

# Shipped crate lists, with the checkout's absolute path replaced.
for t in "$@"; do
    python3 - "$repo" "$work/linked-$t.txt" "$out/linked-crates-$t.txt" <<'PY'
from pathlib import Path
import sys
repo, source, target = sys.argv[1:]
Path(target).write_text(Path(source).read_text(encoding='utf-8').replace('(' + repo, '(<checkout>'), encoding='utf-8')
PY
done
python3 - "$repo" "$recipe" "$out" "$work" "$nodefault" "$features" "${#absent[@]}" "${absent[@]}" "$@" <<'PY'
import hashlib, json, os, subprocess, sys
repo, recipe, out, work, nodefault, features, n = sys.argv[1:8]
absent, triples = sys.argv[8:8 + int(n)], sys.argv[8 + int(n):]
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
about = json.load(open(work + '/cargo-about.json'))
notice_names = {c['package']['name'] for c in about['crates']}
text = open(out + '/RUST-THIRD-PARTY-NOTICES.txt', encoding='utf-8').read()
supplement = os.listdir(out + '/SUPPLEMENT') if os.path.isdir(out + '/SUPPLEMENT') else []
resolved, problems = {}, []
for t in triples:
    meta = json.load(open('%s/metadata-%s.json' % (work, t)))
    pkgs = {p['id']: p for p in meta['packages']}
    nodes = {n['id']: n for n in meta['resolve']['nodes']}
    root = meta['resolve']['root']
    names = {pkgs[i]['name'] for i in nodes}
    linked = {l.split(' ', 1)[0] for l in open('%s/linked-%s.txt' % (work, t))}
    resolved[t] = {pkgs[i]['name']: sorted(nodes[i]['features']) for i in nodes
                   if pkgs[i]['name'] in ('gyroflow', 'ffmpeg-next', 'ffmpeg-sys-next', 'gyroflow-core')}
    resolved[t]['gyroflow'] = sorted(nodes[root]['features'])
    for a in absent:
        where = [w for w, hit in (('cargo metadata resolve', a in names), ('cargo tree linked', a in linked),
                                  ('cargo-about crates', a in notice_names), ('notices text', a in text),
                                  ('supplement', any(f.startswith(a + '-') for f in supplement))) if hit]
        if where:
            problems.append('%s present for %s in: %s' % (a, t, ', '.join(where)))
if problems:
    print('\n'.join('ERROR: ' + p for p in problems), file=sys.stderr)
    sys.exit(1)
receipt = dict(commit=subprocess.run(['git', '-C', repo, 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip(),
               targets=triples, no_default_features=nodefault == '1', features=[f for f in features.split(',') if f],
               resolved_features=resolved, absent_checked=absent,
               tool=subprocess.run(['cargo', 'about', '--version'], check=True, capture_output=True, text=True).stdout.strip(),
               cargo_lock_sha256=sha(repo + '/Cargo.lock'), cargo_toml_sha256=sha(repo + '/Cargo.toml'),
               about_toml_sha256=sha(recipe + '/about.toml'), template_sha256=sha(recipe + '/rust-notices.txt.hbs'),
               gate_sha256=sha(recipe + '/rust_notices_check.py'), supplement_sha256=sha(recipe + '/supplement.json'),
               notices_txt_sha256=sha(out + '/RUST-THIRD-PARTY-NOTICES.txt'))
open(out + '/RUST-NOTICES-RECEIPT.json', 'w').write(json.dumps(receipt, indent=1) + '\n')
PY
mv "$out" "$final"
echo "notices for $* in $final (gate log $work/gate.log)"
