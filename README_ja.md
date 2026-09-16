# gramide-go

[gramide-cli](https://github.com/O6lvl4/gramide-cli) の Go。字句解析の spec、値としての文法、その文法を
コンパイルした表、そしてどのノードが名前を宣言するかの規則。ひとつの Almide パッケージ
`gramide_go` で、依存は [gramide](https://github.com/O6lvl4/gramide) だけです。
`gramide` コマンド（[gramide-cli](https://github.com/O6lvl4/gramide-cli)）はこれを出荷し、このリポジトリはこれ単体をテスト・計測・リリースする場所です。

[English](README.md)

```
almide build cli/main.almd -o gramide_go     # .go だけの gramide
./gramide_go check $(go env GOROOT)/src/go/parser/*.go
./gramide_go outline main.go                 # `L5-5 method Shape.Area`: メソッドはレシーバの型付きで
./gramide_go gen-table > src/table.almd      # 文法を変えたら
```

## カバー範囲

Go 1.27 の `GOROOT/src` 配下の全 `.go` ファイル — 標準ライブラリ・コンパイラ・ツールチェーン、
`testdata` 込みで 8,077 ファイル:

| ファイル | 結果 |
|---|---|
| 8,042 ファイル | すべてパース |
| 35 ファイル（すべて `testdata`） | 拒否。いずれも `gofmt -e` も拒否する |
| `gofmt -e` が拒否する `testdata` 11 ファイル | パースは通る（ここでは gramide のほうが寛容） |

保証は一方向です。このパッケージが拒否するファイルは `gofmt` にとっても壊れている。受理する 11 は
文法が強制しない個数や文字の規則に反するものです: `range` 節に 3 つ以上の式、空の型パラメータ
リスト `[]`、空の型引数リスト、名前付きと無名を混ぜたパラメータリスト、呼び出しでない式や
括弧付きの式への `go`、字句解析器が識別子として受理する非 ASCII 文字（`☹`）。

宣言の範囲は Go 自身のパーサと照合しています。`ci/reference_ranges.go` は gramide と独立に
`ast.FuncDecl` の位置を読み、Go のコミット `e51216de8e26247ee0f3d2cfa576233b0d29f542` で
`src/go/ast`・`src/go/parser`・`src/go/token` 配下の 38 ファイルの関数・メソッド 551 個すべてで
名前・行範囲・byte 範囲が一致します（[証拠](docs/evidence/go-ranges.json)）。CI は同じオラクルを
フィクスチャと生成した 2,000 関数に対して走らせます。

コーパス全体の `check`（7,702 ファイル、90.2 MB）は 1 プロセス、byte 量で均した 8 スライドの
並列で **0.695 秒**（130 MB/s）。最大の `cmd/compile/internal/ssa/opGen.go`（生成 96,689 行）
単体で 64 ミリ秒（[証拠](docs/evidence/corpus-check-go.json)）。公平な比較対象である `gofmt -e`
（同じ言語の手書き再帰下降パーサ）に対しては、1,500 ファイル・25.5 MB で 1 コアなら 1.30 秒
対 gramide 2.74 秒、それぞれの出荷状態なら 0.38 秒対 0.70 秒。tree-sitter-go に対しては、
生成した 800 関数の構造化読み取りが **tree-sitter の 0.78 倍の時間**、400 関数で 0.90 倍、
100 関数で 0.86 倍 — 新規プロセス、起動込み、同じ機械の同じ 1 分間の計測です
（[証拠](docs/evidence/symbol-walk-lexer.json)、`bench/symbols.py`）。
このパッケージを切り出した時点では同じ読み取りが 8.2・18.7・33.7 ミリ秒でした
（[当時](docs/evidence/symbol-walk-benchmark.json)）。差はエンジンの行生成と pack した字句解析器、
そして下記のこの文法の式の梯子です。

キー入力 1 回は item 1 つを読み直すだけです。エンジンはパース済みのファイルを recover item
（ここでは先頭レベルの各宣言と、ブロック内の各文）の入れ子として持ち、編集が触れた最小の item を
読み直します（[仕組み](https://github.com/O6lvl4/gramide/blob/main/docs/incremental.md)）。
`net/http/server.go`（140 KB）に同じ 1,000 編集（13 文字以上の単語の 6 文字目に 1 文字打つ・消す）を、
gramide の `reparse-bench` と、tree-sitter-go `2346a3a` の `ts_tree_edit`＋再パース
（[gramide-javascript](https://github.com/O6lvl4/gramide-javascript/blob/main/bench/tree_sitter_ranges.c) の
C ハーネスを `-DLANG=tree_sitter_go` で組んだもの）にプロセス内で与え、50 回に 1 回は丸ごとのパースと
照合しました（[証拠](docs/evidence/incremental-go-net-http-server.json)、`bench/incremental.py`）。

| `net/http/server.go` | gramide | tree-sitter |
|---|---:|---:|
| 中央値 | 12 µs | 151 µs |
| 90 パーセンタイル | 19 µs | 176 µs |
| 丸ごとのパース（目安） | 1.5 ms | |

`GOROOT/src` の `testdata` 以外で十分長い単語を持つ 5,911 ファイルに各 10 回のランダム編集
（59,110 回、毎回トークンとノードを丸ごとのパースと照合）で差はゼロ。ファイル全体を読んだのは 1 回
（[証拠](docs/evidence/incremental-corpus-goroot-src.json)）。`ci/incremental_check.py` がこれを回し、
1 回の編集は `reparse --edit START:OLD_END:NEW_END --new FILE` です。

## 書き方

- **`src/lexer.almd`** — 32 行の `Spec`。キーワード、演算子、`//` と `/* */`、16 進浮動小数と
  虚数、バッククォートの raw 文字列、そして Go のセミコロン挿入である `NL_SEMI` — 改行が区切りに
  なるのは識別子・リテラル・`break continue fallthrough return`・`++ -- ) ] }` の後だけで、改行を
  含むブロックコメントも改行に数えます。
- **`src/grammar.almd`** — Go 言語仕様に沿って書いた文法。Go の文法が文脈に依存する唯一の箇所は
  複合リテラルです。`T{…}` は `if`・`for`・`switch` のヘッダ以外では式で、ヘッダでは
  `if x == T{}` がブロックを飲み込むため、式の規則を末尾 `{` あり・なしの 2 通り、1 つの関数から
  生成しています。二項演算子の 5 段は 1 つの `prec` 梯子です。入れ子の畳み込みで書くと被演算子に
  届くまで段ごとに規則を 1 回訪ねていて、畳んだことで `GOROOT/src` 全体が 132 から 154 MB/s に、
  拒否する 32 ファイルはそのままでした（[証拠](docs/evidence/corpus-check-go-ladder.json)）。エンジンの
  pack した字句解析器でさらに 211 MB/s になっています（[証拠](docs/evidence/corpus-check-go-lexer.json)）。
  `decl_head` 規則は書きかけの宣言の種類と名前を残します。
- **`src/symbols.almd`** — 関数・メソッド・インタフェースのメソッドシグネチャ・型・var・const・
  field が名前を宣言し、メソッドの所有者は書かれた場所ではなく `receiver` フィールドの型です。
- **`src/table.almd`** — `gen-table` の生成物。古ければ CI が落ちます。

## 検査

`bash ci/check.sh`: `almide test`（50 テスト）、表の一致検査、バイナリのスモーク、UTF-8 オフセット・
raw 文字列・コメント・2,000 関数・不正入力に対する Go パーサのオラクル
（[ci/README.md](ci/README.md)）。オラクルには Go が必要です。

## ライセンス

MIT または Apache-2.0、お好みで。
