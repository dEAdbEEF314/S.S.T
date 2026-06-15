# S.S.T (Steam Soundtrack Tagger) 詳細仕様書

## 1. プロジェクト概要
- **プロジェクト名**: S.S.T (Steam Soundtrack Tagger)
- **バージョン**: 1.0.0
- **目的**: Steam上で配信されているサウンドトラックやDLC音源に対して、公式・非公式のデータベースから高品質なメタデータを取得し、LLMによる知的推論を交えてタグ付け・整理を自動化するシステム。
- **実行環境**: Python 3.12 (uv 管理環境)、FFmpeg、SQLite3。WSL2 環境での動作を想定。

## 2. アーキテクチャと依存関係
- **ディレクトリ構造**: 
  - `src/sst/`: コアロジック (scanner, processor, llm, tagger, db, etc.)
  - `output/`: 処理結果 (`archive`, `review` フォルダへ振り分け)
  - `data/`: SQLite DB (`sst_local_state.db`) やキャッシュファイル
- **主要な外部依存**:
  - `requests`: 各種 Web API 通信
  - `mutagen`: MP3 (ID3v2.3) / AIFF メタデータ読み書き
  - `rich`: CUI コンソール描画
  - `pydantic`, `pydantic-settings`: 設定管理・データバリデーション
- **システム構成**:
  - 設定の源泉 (Legislative): `.env` ファイルおよび `src/sst/config.py`
  - 判定と推論 (Judicial): `src/sst/llm.py` (Gemini API などの LLM バックエンド)
  - 実行ロジック (Executive): `src/sst/processor.py` や `src/sst/tagger.py` などの各コンポーネント
- **排除済みの依存関係**: boto3, minio, gevent, eventemitter, VGMdb統合モジュール、Discogs統合モジュール等、過去の構想や不要機能は完全に排除され、軽量化されています。

## 3. コアワークフロー
1. **スキャン (`scanner.py`)**:
   - `libraryfolders.vdf` や各 `appmanifest_*.acf` を解析し、対象のサントラフォルダを検出。
2. **情報収集 (`builder.py`, `steam_vdf.py`, `ident/*`)**:
   - Steam Store API, PICS Bridge API, MusicBrainz, AcoustID (指紋) からデータを収集。
   - 物理ファイル構成 (Local) と公式情報 (Steam), 外部DB情報 (MBZ) の「3つのVirtual Album」を構築。
3. **LLM推論 (`llm.py`)**:
   - System Prompt を通じて「Identity Confidence (同一性)」と「Integrity Quality (品質)」を判定。
   - 複数ソースから正しい曲名・タグ情報をトラックごとに推論・マッピング。
4. **タグ付け・エンコード (`tagger.py`)**:
   - 判定結果に基づき、FFmpeg を用いて音源を変換。
   - **仕様**: アップサンプリングは行わない。MP3 への変換時は `CBR 320kbps` (`-b:a 320k`) に固定。ID3v2.3 フォーマットを使用。
5. **パッケージングとDB記録 (`packager.py`, `db.py`)**:
   - `archive` (高品質・確実) または `review` (確認が必要) ディレクトリに振り分け。
   - 処理結果を SQLite データベースに記録。
6. **レポートと通知 (`report_generator.py`, `notify.py`)**:
   - HTML 形式のバッチレポートを生成。
   - 設定に応じて Discord Webhook (Critical/Warning/Info/Completion) へ状態を通知。

## 4. メタデータ優先順位とクレンジング
- **全体優先順位**: `MBZ > PICS_API > STEAM_STORE > STEAM_TAGS > EMBEDDED`
- **フィールド別優先順位**:
  - `TIT2 (曲名)`: MBZ > PICS_API > FILE > EMBED > VDF
  - `TPE1 (アーティスト)`: MBZ > PICS_API > EMBED
  - `TRCK (トラック番号)`: PICS_API > MBZ > FILE > EMBED
  - `TPUB (パブリッシャー)`: MBZ > PICS_API
  - `APIC (カバーアート)`: MBZ > PICS_API > WEB_API > EMBED
- **クレンジング規則**: トラック名先頭の不要な連番（例: "01. "）は、`MBZ` または `PICS_API` などの信頼済みソース (TITLE_CLEANING_TRUSTED_SOURCES) でない限り LLM 側で削除されます。

## 5. ドキュメントとコードの現状の整合性
- **プロジェクト名称の統一**: 過去 `scout` と呼ばれていたコードベースやパッケージ名は、すべて `sst` にリネームされ、`S.S.T` として統一済みです。
- **LLM モデルの実装**: 独自モデル (`*-sst`) を使用する方式から、コード内 (`llm.py`) で System Prompt やパラメータを動的に注入する一般的な方式へと移行済みです。
- **不要機能の廃止**: VGMdb 連携、Discogs 連携、S3(minio)連携などはコードベースおよび設定ファイルから完全に排除されており、矛盾はありません。
- **通知仕様**: Discord への Webhook 通知機能が実装されており、`.env.example` の設定項目とも一致しています。

以上の通り、すべてのコード・ドキュメント間の矛盾やズレは本仕様書作成の過程で解消されています。
