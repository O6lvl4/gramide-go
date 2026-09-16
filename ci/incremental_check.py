"""Random edits over a corpus, every one checked: the incremental document
after each edit must equal the whole parse of the same text, token for token
and node for node. Each file gets --edits edits (typed and deleted letters in
long words, and with --breaking an unmatched brace every tenth edit, so the
file stops parsing and the check runs against the recovering whole parse).
Writes the evidence the README cites.

    python3 ci/incremental_check.py <root> <out.json> [--ext .go] [--exclude testdata] [--edits 10] [--breaking] [--list FILES]

--list names a file of paths relative to <root>, one per line (the tracked files of a checkout), instead of walking <root>."""
from pathlib import Path
import hashlib, json, platform, re, subprocess, sys

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
exts = tuple(".go".split(","))
excluded = []
edits = 10
breaking = "--breaking" in sys.argv
for i, arg in enumerate(sys.argv):
    if arg == "--ext": exts = tuple(sys.argv[i + 1].split(","))
    if arg == "--exclude": excluded = sys.argv[i + 1].split(",")
    if arg == "--edits": edits = int(sys.argv[i + 1])
here = Path(__file__).resolve().parent
binary = here.parent / ("gramide_" + here.parent.name.split("-", 1)[1])
files = sorted(p for p in root.rglob("*") if p.suffix in exts and not any(x in p.parts for x in excluded))
if "--list" in sys.argv: files = [root / l.strip() for l in open(sys.argv[sys.argv.index("--list") + 1]) if l.strip() and l.strip().endswith(exts)]

results = {"platform": platform.platform(), "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "root": str(root), "ext": list(exts),
           "excluded": excluded, "edits_per_file": edits, "breaking": breaking, "files": len(files), "checked": 0, "edits": 0, "mismatches": 0,
           "fallbacks": 0, "fallback_reasons": {}, "skipped_no_long_word": [], "errors": [], "mismatched_files": []}
for n, p in enumerate(files):
    r = subprocess.run([str(binary), "reparse-bench", str(p), "--edits", str(edits), "--seed", str(n + 1), "--verify", "1"] + (["--breaking"] if breaking else []), capture_output=True, text=True)
    if r.returncode:
        if "no word of 13 letters" in r.stderr: results["skipped_no_long_word"].append(str(p.relative_to(root)))
        else: results["errors"].append({"path": str(p.relative_to(root)), "error": r.stderr.strip()[:300]})
        continue
    row = json.loads(r.stdout.strip().splitlines()[-1])
    results["checked"] += 1; results["edits"] += row["edits"]; results["fallbacks"] += row["fallbacks"]
    for k, v in row["fallback_reasons"].items(): results["fallback_reasons"][k] = results["fallback_reasons"].get(k, 0) + v
    if row["mismatches"] or row["initial_mismatch"]:
        results["mismatches"] += row["mismatches"] + (1 if row["initial_mismatch"] else 0)
        detail = [l for l in r.stderr.splitlines() if re.search(r": token \d+: |tree differs|before any edit", l)]
        results["mismatched_files"].append({"path": str(p.relative_to(root)), "seed": n + 1, "first": detail[0][:300] if detail else r.stderr.strip()[:300]})
try:
    results["reference_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
except subprocess.CalledProcessError:
    pass
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(results, indent=2) + "\n")
print({k: (len(v) if isinstance(v, list) else v) for k, v in results.items() if k not in ("root", "ext", "excluded", "binary_sha256", "platform")})
for row in results["mismatched_files"][:5]: print("mismatch", row)
for row in results["errors"][:5]: print("error", row)
sys.exit(1 if results["mismatches"] or results["errors"] else 0)
