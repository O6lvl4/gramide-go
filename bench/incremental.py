"""The cost of one edit: gramide's incremental re-read against tree-sitter's
incremental parse, in-process, the same edit sequence for both (a 31-bit
LCG seeds positions; every edit types or deletes one letter six letters
into a word of thirteen or more, so the file stays what it was
syntactically). gramide is checked against a whole parse every --verify
edits. Writes the evidence the README cites.

    python3 bench/incremental.py --gramide ./gramide_go --tree-sitter /tmp/ts-go \\
        --edits 1000 --seed 7 --out docs/evidence/incremental-<file>.json FILE...

tree-sitter's side is bench/tree_sitter_ranges.c built for the grammar
(`--edits N --seed S FILE`); gramide's is `reparse-bench`."""
from pathlib import Path
import argparse, hashlib, json, platform, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("--gramide", type=Path, required=True)
ap.add_argument("--tree-sitter", type=Path, required=True)
ap.add_argument("--edits", type=int, default=1000)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--verify", type=int, default=50)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("files", nargs="+", type=Path)
args = ap.parse_args()
gramide, sitter = args.gramide.resolve(), args.tree_sitter.resolve()

rows = []
for f in args.files:
    f = f.resolve()
    g = subprocess.run([str(gramide), "reparse-bench", str(f), "--edits", str(args.edits), "--seed", str(args.seed), "--verify", str(args.verify)], capture_output=True, text=True)
    t = subprocess.run([str(sitter), "--edits", str(args.edits), "--seed", str(args.seed), str(f)], capture_output=True, text=True)
    if g.returncode or t.returncode:
        rows.append({"path": str(f), "error": (g.stderr + t.stderr).strip()[:500]}); continue
    rows.append({"path": str(f), "bytes": f.stat().st_size, "gramide": json.loads(g.stdout.strip().splitlines()[-1]), "tree_sitter": json.loads(t.stdout.strip().splitlines()[-1])})

report = {"platform": platform.platform(), "edits": args.edits, "seed": args.seed, "verify_every": args.verify,
          "gramide_sha256": hashlib.sha256(gramide.read_bytes()).hexdigest(), "tree_sitter_harness_sha256": hashlib.sha256(sitter.read_bytes()).hexdigest(),
          "files": rows}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(report, indent=1) + "\n")
for r in rows:
    if "error" in r: print(r["path"], "ERROR", r["error"][:200]); continue
    g, t = r["gramide"], r["tree_sitter"]
    print(f'{Path(r["path"]).name}: gramide median {g["median_us"]} us (p90 {g["p90_us"]}, fallbacks {g["fallbacks"]}, mismatches {g["mismatches"]}, whole {g["whole_parse_median_us"]} us) | tree-sitter median {t["median_us"]} us (p90 {t["p90_us"]})')
