# S.S.T AI向けコードベース要約

## 概要

S.S.T は、Steam で購入したサウンドトラック商品を対象に、ローカル環境で整列・タグ付け・アーカイブ化を行う CLI ツールです。

現行仕様の正本は [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md) です。AI が設計判断を行う場合は、この文書を最優先で参照してください。

## 最重要ルール

- Steam ライブラリ内の元ファイルは読み取り専用です。
- 構造の正は STEAM です。
- LLM は既存シグナルの整列判断だけを担い、新しいメタデータを創作しません。
- 確証不足の結果は archive せず review に送ります。
- 変更を加えた場合は [CHANGE_HISTORY.md](CHANGE_HISTORY.md) の末尾へ追記します。

## 現行アーキテクチャ

1. AppID から STEAM アルバムメタデータセットを構築する。
2. ローカル全ファイルからシグナルを収集する。
3. ファストトラック条件を満たすか判定する。
4. 条件未達時のみ LLM が各ファイルを STEAM スロットに割り当てる。
5. 各スロット内で最高 Tier のファイルを変換元として機械的に選ぶ。
6. フィールド定義に従って最終タグを組み立てる。
7. 閾値判定により archive または review へ送る。

## 情報ソースの優先順位

現行仕様で扱う情報ソースは次の 6 種です。

- STEAM
- ACOUSTID
- MBZ_RELEASE
- MBZ_SEARCH
- EMBED
- LOCAL

フィールドごとの正ソース、異常検知、フォールバック順、LLM 介入条件は [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md) に固定されています。

## 実装上の注意

- 変換元ファイルの選択は LLM に委ねません。
- APIC や既存 COMM は、同一 STEAM スロットに割り当てられた別フォーマットから拾える前提です。
- TPUB は最終タグとしては廃止されています。
- 旧来の Virtual Album、track_grouper 中心設計、Phase 1 / 1.5 / 2 といった概念は現行仕様では使いません。

## 主要ディレクトリ

- `src/sst/`: コア実装
- `docs/`: 現行仕様と運用文書
- `data/`: ローカル DB とキャッシュ
- `tests/`: テスト
- `docs/archive/v0.1/`: 旧資料の退避先
