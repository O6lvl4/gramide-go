"""Exercise the package's own binary; no network, no model."""
from pathlib import Path
import subprocess, tempfile

BIN = Path(__file__).resolve().parents[1] / "gramide_go"

def run(*args, code=0):
    p = subprocess.run([str(BIN), *map(str, args)], capture_output=True, text=True, timeout=30)
    assert p.returncode == code, (args, p.returncode, p.stdout, p.stderr)
    return p.stdout

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = root / "valid.go"
    source.write_text('package main\nfunc real() {}\n')
    run("check", source)
    assert "function real" in run("outline", source)
    broken = root / "broken.go"
    broken.write_text('package main\nfunc real() {}\n}\n')
    run("check", broken, code=1)
    assert run("version").splitlines()[0].startswith("gramide_go ")
    assert '"id":"go"' in run("languages")
print("CLI smoke passed: outline, syntax rejection, version and discovery")
