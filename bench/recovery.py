#!/usr/bin/env python3
"""Error recovery compared: what each parser still reports after one break.

Every file of a corpus is broken in four ways, one at a time — a `{` typed at
the start of a word, a `}` deleted, a `)` deleted, a `(` typed at the start of
a word — none of which changes the line count. The declarations each tool
lists for the broken file are compared with what the same tool listed for the
whole file: a declaration is kept when the same kind, name and start line
come back; lost otherwise; spurious when it was not there before. A lost
declaration whose lines hold the break is expected (`lost_touching`); one
whose lines do not is collateral (`lost_collateral`), and that is the quality
of the recovery. Only files both tools parse whole without error take part.

    python3 bench/recovery.py --gramide BIN --tree-sitter HARNESS \
        --ts-kinds function_declaration=function,class_declaration=class,method_definition=method \
        [--kinds function,class,method] [--gramide-map method=function] \
        [--ext .js,.mjs,.cjs] [--exclude testdata] [--breaks 4] [--seed 7] [--limit N] [--out JSON] ROOT

--kinds names the declaration kinds counted, after the two maps: --ts-kinds
takes tree-sitter's node kinds to those names, --gramide-map renames gramide's
outline kinds where a language's package spells one differently (Python's
methods are `method` for gramide and function_definition for tree-sitter).

gramide's `outline` (which reads the recovered parse) and the harness's
`--recover KINDS FILE` (tree-sitter's tree, ERROR and MISSING nodes included)
are the two listings. A gramide method `Widget.render` or `Type::method` is
compared by its last name part, as tree-sitter names it. The JSON written by --out holds the
totals, the per-break-kind split and the ten worst breaks of each tool.
"""
import json, os, random, re, subprocess, sys, tempfile, time

def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name); v = sys.argv[i + 1]; del sys.argv[i:i + 2]; return v
    return default

gramide = arg("--gramide"); harness = arg("--tree-sitter"); ts_kinds = arg("--ts-kinds")
exts = tuple(arg("--ext", ".js,.mjs,.cjs").split(",")); breaks = int(arg("--breaks", "4"))
seed = int(arg("--seed", "7")); limit = int(arg("--limit", "0")); out = arg("--out")
exclude = arg("--exclude", "").split(",") if arg("--exclude", "") else []
kinds = set(arg("--kinds", "function,class,method").split(","))
g_map = dict(kv.split("=") for kv in arg("--gramide-map", "").split(",") if kv)
if not (gramide and harness and ts_kinds) or len(sys.argv) != 2:
    print(__doc__); sys.exit(2)
root = sys.argv[1]
ts_map = dict(kv.split("=") for kv in ts_kinds.split(","))
BREAK_KINDS = ["insert {", "delete }", "delete )", "insert ("]

def files_of(root):
    found = []
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in exclude)
        for n in sorted(names):
            if n.endswith(exts): found.append(os.path.join(d, n))
    return found[:limit] if limit else found

LINE = re.compile(r"^\s*L(\d+)-(\d+) (\S+) (\S+)")
def gramide_list(path):
    r = subprocess.run([gramide, "outline", path], capture_output=True, text=True)
    decls, skipped = set(), 0
    for l in (r.stdout + "\n" + r.stderr).splitlines():
        m = LINE.match(l)
        if m:
            kind = g_map.get(m.group(3), m.group(3))
            if kind in kinds: decls.add((kind, re.split(r"\.|::", m.group(4))[-1], int(m.group(1)), int(m.group(2))))
        m = re.search(r"\[recovered, (\d+) part", l)
        if m: skipped = int(m.group(1))
    return decls, r.returncode, skipped

def ts_list(path):
    r = subprocess.run([harness, "--recover", ",".join(ts_map), path], capture_output=True, text=True)
    decls, errors = set(), 0
    for l in r.stdout.splitlines():
        o = json.loads(l)
        if o["kind"] in ("ERROR", "MISSING"): errors += 1
        elif ts_map[o["kind"]] in kinds: decls.add((ts_map[o["kind"]], o["name"], o["start"], o["end"]))
    return decls, r.returncode, errors

def key(d): return d[:3]

def word_starts(text):
    return [m.start() for m in re.finditer(r"(?<![A-Za-z0-9_])[A-Za-z_]", text)]

def broken(text, kind, rng):
    if kind == 0 or kind == 3:
        ws = word_starts(text)
        if not ws: return None, None
        p = rng.choice(ws); return text[:p] + ("{" if kind == 0 else "(") + text[p:], p
    ch = "}" if kind == 1 else ")"
    ps = [i for i, c in enumerate(text) if c == ch]
    if not ps: return None, None
    p = rng.choice(ps); return text[:p] + text[p + 1:], p

def stats():
    return {"breaks": 0, "baseline": 0, "kept": 0, "lost_touching": 0, "lost_collateral": 0, "spurious": 0, "clean_breaks": 0, "no_error_reported": 0, "error_nodes": 0}

report = {"root": root, "kinds": sorted(kinds), "files": 0, "skipped_not_clean": 0, "breaks_per_file": breaks, "seed": seed, "break_kinds": BREAK_KINDS,
          "gramide": {"total": stats(), "by_break": [stats() for _ in BREAK_KINDS], "worst": []},
          "tree_sitter": {"total": stats(), "by_break": [stats() for _ in BREAK_KINDS], "worst": []},
          "both_lost_collateral": 0, "only_gramide_lost_collateral": 0, "only_tree_sitter_lost_collateral": 0}

def score(tool, base, got, rc, errs, line, k, path, pos):
    t = report[tool]["total"]; b = report[tool]["by_break"][k]
    bk = {key(d): d for d in base}; gk = {key(d) for d in got}
    kept = sum(1 for d in bk if d in gk)
    lost_touch = sum(1 for d, full in bk.items() if d not in gk and full[2] <= line <= full[3])
    lost_coll = sum(1 for d, full in bk.items() if d not in gk and not (full[2] <= line <= full[3]))
    spurious = sum(1 for d in gk if d not in bk)
    for s in (t, b):
        s["breaks"] += 1; s["baseline"] += len(bk); s["kept"] += kept; s["lost_touching"] += lost_touch
        s["lost_collateral"] += lost_coll; s["spurious"] += spurious; s["error_nodes"] += errs
        if lost_coll == 0 and spurious == 0: s["clean_breaks"] += 1
        if rc == 0: s["no_error_reported"] += 1
    w = report[tool]["worst"]; w.append((lost_coll, spurious, os.path.relpath(path, root), BREAK_KINDS[k], pos, line))
    w.sort(reverse=True); del w[10:]
    return lost_coll

t0 = time.time()
for n, path in enumerate(files_of(root)):
    text = open(path, encoding="utf-8", errors="surrogateescape").read()
    g_base, g_rc, _ = gramide_list(path); t_base, t_rc, _ = ts_list(path)
    if g_rc != 0 or t_rc != 0:
        report["skipped_not_clean"] += 1; continue
    report["files"] += 1
    rng = random.Random(seed * 1000003 + n)
    ext = os.path.splitext(path)[1]
    for k in range(breaks):
        kind = k % len(BREAK_KINDS)
        new, pos = broken(text, kind, rng)
        if new is None: continue
        line = text.count("\n", 0, pos) + 1
        with tempfile.NamedTemporaryFile("w", suffix=ext, delete=False, encoding="utf-8", errors="surrogateescape") as f:
            f.write(new); tmp = f.name
        try:
            g_got, g_rc, g_skipped = gramide_list(tmp); t_got, t_rc, t_errs = ts_list(tmp)
        finally:
            os.unlink(tmp)
        gl = score("gramide", g_base, g_got, g_rc, g_skipped, line, kind, path, pos)
        tl = score("tree_sitter", t_base, t_got, t_rc, t_errs, line, kind, path, pos)
        if gl and tl: report["both_lost_collateral"] += 1
        elif gl: report["only_gramide_lost_collateral"] += 1
        elif tl: report["only_tree_sitter_lost_collateral"] += 1
report["seconds"] = round(time.time() - t0, 1)

def line_of(name, s):
    b = s["baseline"] or 1
    return f"{name:12} breaks {s['breaks']:5}  kept {s['kept']/b:6.1%}  lost touching {s['lost_touching']:5}  collateral {s['lost_collateral']:5}  spurious {s['spurious']:5}  clean {s['clean_breaks']/max(s['breaks'],1):6.1%}  error nodes/parts {s['error_nodes']/max(s['breaks'],1):.2f}"
print(f"{report['files']} files ({report['skipped_not_clean']} skipped: not clean in both), {breaks} breaks each, {report['seconds']}s")
for tool in ("gramide", "tree_sitter"):
    print(line_of(tool, report[tool]["total"]))
    for k, bk in enumerate(BREAK_KINDS): print("  " + line_of(bk, report[tool]["by_break"][k]))
print(f"collateral loss: both {report['both_lost_collateral']}, only gramide {report['only_gramide_lost_collateral']}, only tree-sitter {report['only_tree_sitter_lost_collateral']}")
if out:
    with open(out, "w") as f: json.dump(report, f, indent=1)
