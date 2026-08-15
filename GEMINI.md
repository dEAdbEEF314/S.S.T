# S.S.T Project Instructions

## Critical Rules

1. Steam ライブラリ内の元ファイルは常に Read-Only で扱うこと。
2. 現行仕様の正本は [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md) であり、設計判断は必ずこれに従うこと。
3. STEAM を構造の絶対的な正とし、その不備に対してのみ他ソースと LLM を使うこと。
4. LLM はファイルを STEAM スロットに割り当てる判断者であり、タイトル生成やタグ値創作をしてはならない。
5. 確証不足の結果は archive ではなく review に送ること。
6. 変更を加えた場合は [CHANGE_HISTORY.md](CHANGE_HISTORY.md) の先頭（注記の直後）へ新しい順（時系列降順）に日本語で追記すること。

## Engineering Standards

- Tech Stack: Python 3.12, uv, FFmpeg, SQLite3
- Execution: Prefer `uv run` for scripts and tests
- Metadata policy: Field-level source precedence is fixed by the spec and must not be overridden casually
- Historical docs: `docs/archive/old/` and `docs/archive/v0.1/` are backup-only and must not be treated as current spec

## Active Layout

- `src/sst/`: Core implementation
- `docs/`: Active specifications and operations docs
- `docs/archive/v0.1/`: Retired documents and plans
- `data/`: Local DB and caches
- `tests/`: Tests and verification code
