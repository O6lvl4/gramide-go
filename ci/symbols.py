"""Structured ranges against Go's own parser; no model calls."""
from pathlib import Path
import json, subprocess, tempfile
BIN = Path(__file__).resolve().parents[1] / 'gramide_go'
def symbols(path):
    p = subprocess.run([str(BIN), 'symbols', str(path)], capture_output=True, text=True, check=True)
    d = json.loads(p.stdout); assert d['schema_version'] == 1 and d['complete'] is True
    return d['symbols']
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    fixture = root / 'ranges.go'
    fixture.write_text('''package sample
// 日本語 before declarations tests UTF-8 byte offsets.
type Box struct { value int }
func (b *Box) Read(
) int {
    text := `}
func phantom() {}`
    _ = text
    return b.value
}
func Other() {
    /* } */
}
''')
    oracle = root / 'oracle'
    subprocess.run(['go', 'build', '-o', str(oracle), str(BIN.parent / 'ci/reference_ranges.go')], check=True)
    expected = json.loads(subprocess.check_output([str(oracle), str(fixture)], text=True))
    actual = [{k: s[k] for k in expected[0]} for s in symbols(fixture) if s['kind'] in ('method', 'function')]
    assert actual == expected, (actual, expected)
    raw = fixture.read_bytes()
    for s in symbols(fixture): assert raw[s['start_byte']:s['end_byte']].strip()
    broken = root / 'broken.go'; broken.write_text('package p\nfunc real() {}\nfunc broken(\n')
    p = subprocess.run([str(BIN), 'symbols', str(broken)], capture_output=True, text=True)
    assert p.returncode != 0 and not p.stdout, (p.returncode, p.stdout, p.stderr)
    # A per-node copy of the complete token stream once made this path quadratic.
    # Keep a generous process deadline: the fixed walk completes in well under a
    # second locally, while the old walk takes tens of seconds on this input.
    large = root / 'many.go'
    large.write_text('package sample\n' + ''.join('func F%d(x int) int { return x + %d }\n' % (i, i) for i in range(2000)))
    result = subprocess.run([str(BIN), 'symbols', str(large)], capture_output=True, text=True, check=True, timeout=15)
    actual = json.loads(result.stdout)['symbols']
    expected = json.loads(subprocess.check_output([str(oracle), str(large)], text=True))
    assert len(actual) == 2000
    assert [{k: s[k] for k in expected[0]} for s in actual] == expected
print('Structured ranges passed: Go parser oracle on UTF-8, raw strings, comments, 2,000 functions, and invalid input')
