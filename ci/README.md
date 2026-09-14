# Reproducible checks

Run `bash ci/check.sh` from a checkout with Almide and Go installed, or set
`ALMIDE_BIN` to an absolute compiler path. This runs the package's tests,
builds its own binary from `cli/main.almd`, fails if `src/table.almd` is not
what the grammar compiles to, drives the binary through temporary fixtures,
and compares `symbols` ranges with `ci/reference_ranges.go`, an oracle over
Go's own `go/parser` that knows nothing of gramide — on a UTF-8 fixture with
raw strings and comments, and on 2,000 generated functions under a 15-second
deadline that once caught a quadratic walk. No model API or credentials are
used.

`python3 ci/reference_corpus.py /path/to/go /tmp/go-ranges.json` runs the same
oracle over every non-`testdata` file under `src/go` of a Go checkout and
writes the evidence the README cites. `bench/symbols.py` is the structured-read
comparison against tree-sitter-go; its header says how to build the reference.

CI pins Almide to `dff9a458f2e581631bb6537c856a7974036e4153` and Rust to
`1.94.0`. Upgrade these deliberately and rerun the checks together.
