# gramide-go

Go for [gramide-cli](https://github.com/O6lvl4/gramide-cli): the lexer spec, the
grammar as a value, that grammar compiled, and the rules that say which of its
nodes declare a name — one Almide package, `gramide_go`, depending on
[gramide](https://github.com/O6lvl4/gramide) and on nothing else.
The `gramide` command ([gramide-cli](https://github.com/O6lvl4/gramide-cli)) ships it; this repository is where it is tested, measured and
released on its own.

[日本語](README_ja.md)

```
almide build cli/main.almd -o gramide_go     # gramide over .go alone
./gramide_go check $(go env GOROOT)/src/go/parser/*.go
./gramide_go outline main.go                 # `L5-5 method Shape.Area`: a method named with its receiver
./gramide_go gen-table > src/table.almd      # after any change to the grammar
```

## What it covers

Every `.go` file under `GOROOT/src` of Go 1.27 — 8,077 files: standard
library, compiler and toolchain, `testdata` included:

| files | result |
|---|---|
| 8,042 files | all parse |
| 35 files, all under `testdata` | rejected; `gofmt -e` rejects every one of them |
| 11 `testdata` files that `gofmt -e` rejects | parse (gramide is more permissive than `gofmt` here) |

The guarantee runs one way: a file this package rejects is broken for `gofmt`
too. The 11 it accepts fail counting or character rules the grammar does not
enforce: more than two expressions in a `range` clause, an empty
type-parameter list `[]`, an empty type-argument list, a parameter list mixing
named and unnamed parameters, `go` with a non-call or parenthesized
expression, and a non-ASCII character (`☹`) that the lexer accepts as an
identifier.

Declaration ranges are checked against Go's own parser: `ci/reference_ranges.go`
reads `ast.FuncDecl` positions independently of gramide, and at Go commit
`e51216de8e26247ee0f3d2cfa576233b0d29f542` the 38 files under `src/go/ast`,
`src/go/parser` and `src/go/token` match on all 551 function and method
names, line ranges and byte ranges
([evidence](docs/evidence/go-ranges.json)); CI runs the same oracle on
fixtures and on 2,000 generated functions.

Whole-corpus `check` — 7,702 files, 90.2 MB — takes **0.695 s** (130 MB/s) in
one process, eight byte-balanced slices in parallel; the largest file,
`cmd/compile/internal/ssa/opGen.go` at 96,689 generated lines, takes 64 ms
alone ([evidence](docs/evidence/corpus-check-go.json)). Against `gofmt -e`,
which is the fair comparison — a hand-written recursive descent parser for
the same language — 1,500 files and 25.5 MB take 1.30 s to gramide's 2.74 s
on one core, and 0.38 s to 0.70 s as each ships. Against tree-sitter-go, a
structured read of 800 generated functions takes **0.78x its time**, 400
take 0.90x and 100 take 0.86x — fresh processes, startup included, on the
same machine in the same minute ([evidence](docs/evidence/symbol-walk-lexer.json),
`bench/symbols.py`).
When this package was extracted the same read took 8.2, 18.7 and 33.7 ms
([then](docs/evidence/symbol-walk-benchmark.json)); the difference is the
engine's row rendering, its packed lexer, and this grammar's expression
ladder, below.

One keystroke re-reads one item: the engine keeps a parsed file as its
recover items (here, every top-level declaration and every statement inside
a block) and re-reads the smallest one an edit touched
([how](https://github.com/O6lvl4/gramide/blob/main/docs/incremental.md)).
The same 1,000 edits on `net/http/server.go` (140 KB), each a letter typed or
deleted six letters into a word of thirteen or more, in-process, for
gramide's `reparse-bench` and for tree-sitter-go at `2346a3a` through
`ts_tree_edit` + reparse in the C harness of
[gramide-javascript](https://github.com/O6lvl4/gramide-javascript/blob/main/bench/tree_sitter_ranges.c)
built with `-DLANG=tree_sitter_go`; every fiftieth result checked against a
whole parse ([evidence](docs/evidence/incremental-go-net-http-server.json),
`bench/incremental.py`):

| `net/http/server.go` | gramide | tree-sitter |
|---|---:|---:|
| median | 13 µs | 156 µs |
| 90th percentile | 22 µs | 181 µs |
| a whole parse, for scale | 1.5 ms | |

Over `GOROOT/src`, ten random edits in each of the 5,911 files that hold a
long enough word outside `testdata` (59,110 edits, every one checked token
for token and node for node against a whole parse of the same text) gave no
difference; one edit was read as a whole file ([evidence](docs/evidence/incremental-corpus-goroot-src.json)).
`ci/incremental_check.py` runs this; `reparse --edit START:OLD_END:NEW_END --new FILE`
is the one-edit command.

### A broken file

An editor's file is broken more often than not. `bench/recovery.py` breaks every
file of the corpus in four ways, one at a time — a `{` typed at the start of a
word, a `}` deleted, a `)` deleted, a `(` typed — and compares what each tool
still lists (gramide's `outline`, which reads the recovered parse; tree-sitter's
tree through the same harness, `--recover`) with its own listing of the whole
file, by kind, name and start line. A declaration whose lines hold the break is
expected to go; a break is *clean* when nothing else is lost and nothing new
appears ([evidence](docs/evidence/recovery-goroot-src.json), [how it recovers](https://github.com/O6lvl4/gramide/blob/main/docs/recovery.md)):

| Go `src/`: 8,010 files, 30,927 breaks | gramide | tree-sitter |
|---|---:|---:|
| declarations kept, all breaks | 99.7% | 91.1% |
| clean breaks (nothing lost beyond the break, nothing invented) | 99.2% | 82.9% |
| clean breaks, `insert {` | 98.8% | 91.6% |
| clean breaks, `delete }` | 99.4% | 48.2% |
| clean breaks, `delete )` | 99.7% | 92.3% |
| clean breaks, `insert (` | 98.8% | 97.0% |

gramide is ahead on every kind of break; a `}` deleted is the large one. The
next `func` is where gramide resumes, so one function is lost, where
tree-sitter's cost model nests the rest of the file into the open body.

## How it is written

- **`src/lexer.almd`** — 32 lines of `Spec`: keywords, operators, `//` and
  `/* */`, hex floats and imaginaries, backtick raw strings, and `NL_SEMI`,
  which is Go's semicolon insertion — a newline is a separator only after an
  identifier, a literal, one of `break continue fallthrough return`, or
  `++ -- ) ] }`, a block comment with a newline counting as one.
- **`src/grammar.almd`** — written against the Go language specification.
  The one place Go's grammar depends on context is the composite literal:
  `T{…}` is an expression everywhere except in the header of `if`, `for` and
  `switch`, where `if x == T{}` would swallow the block, so the expression
  rules are generated twice from one function, with and without a trailing
  `{`. The five binary levels are one `prec` ladder, lowest first: written as
  nested folds, reaching an operand cost a rule visit per level, and folding
  them took the whole of `GOROOT/src` from 132 to 154 MB/s with the same 32
  files rejected ([evidence](docs/evidence/corpus-check-go-ladder.json)), and
  the engine's packed lexer took it on to 211 MB/s
  ([evidence](docs/evidence/corpus-check-go-lexer.json)). A
  `decl_head` rule keeps the kind and name of a half-typed declaration.
- **`src/symbols.almd`** — functions, methods, interface method signatures,
  types, vars, consts and fields declare names; a method is owned by the type
  in its `receiver` field, which is not where it is written.
- **`src/table.almd`** — generated by `gen-table`; CI fails if it is stale.

## Checks

`bash ci/check.sh`: `almide test` (50 tests), the table check, the binary's
smoke test, and the Go parser oracle on UTF-8 offsets, raw strings, comments,
2,000 functions and invalid input ([ci/README.md](ci/README.md)). Go must be
installed for the oracle.

## License

MIT or Apache-2.0, at your option.
