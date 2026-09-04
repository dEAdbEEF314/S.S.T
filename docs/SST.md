# S.S.T 仕様概要

## 1. 位置づけ

S.S.T は、Steam で購入したサウンドトラック商品を対象に、ローカル環境だけで音源整理・タグ付け・アーカイブ化を行う CLI ツールです。

本システムの最重要原則は以下です。

- STEAM を構造の絶対的な正とする。
- LLM は既存シグナルの整列判断のみを担い、新しいメタデータを創作しない。
- 元の Steam ライブラリ内ファイルは書き換えない。
- 判定不能なものは黙って通さず Review へ隔離する。

## 2. 正式な仕様書の優先順位

現行仕様は次の文書を正本とします。

1. [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md)
2. [docs/LOGIC.md](docs/LOGIC.md)
3. [docs/TAGGING_RULE.md](docs/TAGGING_RULE.md)
4. [docs/configuration.md](docs/configuration.md)
5. [docs/error_handling.md](docs/error_handling.md)

[docs/archive/old](docs/archive/old) と [docs/archive/v0.1](docs/archive/v0.1) はバックアップ専用です。現行仕様の判断材料として使いません。

## 3. 安全なローカル運用

- Steamライブラリの元音源は読み取り専用で扱う。Linuxではソース領域を `ro` マウントする運用を推奨する。
- `INFO`（既定）では処理完了後に `SST_WORKING_DIR` の `final_<AppID>_*` / `buffer_<AppID>_*` を削除する。
- `DEBUG` または `--dev` では診断のため中間生成物を保持する。プロンプト、LLM応答、ローカルパス、タグ情報を含み得るため、共有前に確認する。
- `.env`の認証情報はログレベルに関係なく出力しない。
- Steam説明文は不信データとして扱い、LLM出力はJSON契約と決定論的な参照範囲検証を通す。
- FFmpegの非ゼロ終了、出力欠落、変換失敗、音声警告はArchiveせずReviewへ送る。
- Archive前に `final_<AppID>_*` の成果物を再検証し、ZIP化された成果物との内容・タグ整合性を確認する。

## 4. システム境界

### 4.1 入力

- Steam 商品情報
- Steam ストア上のトラックリスト
- ローカル音声ファイル
- 埋め込みタグ
- AcoustID / MusicBrainz の補助情報

### 4.2 出力

- archive 判定された成果物の ZIP
- review 判定された成果物の ZIP
- 監査用レポートと処理ログ

### 4.3 非対象

- 元ファイルの上書き更新
- 分散ストレージやクラウド常駐ワーカー
- LLM によるタイトル生成・補完創作
- 仮想アルバム同士の比較を中心とした旧来アーキテクチャ

## 5. 現行アーキテクチャ

S.S.T は次の 7 段で処理します。

1. AppID から STEAM アルバムメタデータセットを構築する。
2. ローカル全ファイルからシグナルを収集する。
3. ファストトラック条件を判定する。
4. 条件未達なら LLM アライメントを行う。
5. 各 STEAM スロットで変換元ファイルを機械的に選ぶ。
6. フィールド定義に従って最終タグを構築する。
7. confidence / data quality を評価して archive または review へ送る。

詳細は [docs/LOGIC.md](docs/LOGIC.md) を参照してください。

## 6. 情報ソースの扱い

S.S.T が扱う情報ソースは、信頼度の根拠により次の 6 分類です。

- STEAM
- ACOUSTID
- MBZ_RELEASE
- MBZ_SEARCH
- EMBED
- LOCAL

この分類と各フィールドの採用順序は [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md) に従います。

## 7. 廃止された概念

以下は現行仕様では使いません。

- Virtual Album を中心にした設計
- track_grouper による事前のフォーマット統合
- Phase 1 / Phase 1.5 / Phase 2 という旧来の多段 LLM 設計
- TPUB を最終タグとして保持する運用
- LLM による変換元ファイル選択

これらが記載された文書はバックアップ扱いであり、現行仕様では参照しません。

## 8. 関連文書

- 処理フロー: [docs/LOGIC.md](docs/LOGIC.md)
- タグ仕様: [docs/TAGGING_RULE.md](docs/TAGGING_RULE.md)
- 導入手順: [docs/DEPLOYMENT_GUIDE_jp.md](docs/DEPLOYMENT_GUIDE_jp.md)
- 設定値: [docs/configuration.md](docs/configuration.md)
- テスト方針: [docs/TEST_ENVIRONMENT.md](docs/TEST_ENVIRONMENT.md)
- 例外と隔離: [docs/error_handling.md](docs/error_handling.md)
- フロー図: [docs/data_flow_diagram.md](docs/data_flow_diagram.md)
- 外部 API 運用: [docs/api_rate_limit.md](docs/api_rate_limit.md)