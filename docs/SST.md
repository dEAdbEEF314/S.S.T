# S.S.T (Steam Soundtrack Tagger) - コア・アーキテクチャ

このドキュメントは、S.S.T プロジェクトの設計思想、システム構成、およびデータフローを定義します。具体的な判定ロジックについては `LOGIC.md` を、タグ付けの詳細仕様については `TAGGING_RULE.md` を参照してください。

---

## 1. 根本原理: 「一度のアーカイブで、一生の信頼を」

- **目標**: 高精度かつメンテナンスフリーな音楽ライブラリの自動構築。
- **ポリシー**: 100% の信頼性を担保できるもののみを `ARCHIVE` とし、少しでも疑念がある場合は `REVIEW` フォルダへ振り分け、人間による最終確認を必須とします。

---

## 2. 三権分立アーキテクチャ

S.S.T は AI の柔軟な推論とプログラムの厳格性を両立するため、以下の「三権分立」モデルを採用しています。

- **立法 (User/Config)**: `.env` や `Config` クラスを通じて、信頼するソースの優先順位（Constitution）を定義します。
- **司法 (LLM/Auditor)**: 提示された複数のソースを比較し、文脈に基づいて最適なメタデータを推論（判決）します。
- **行政 (System/Executor)**: LLM の出力が物理的なクリーンネス基準を満たしているか検閲し、タグの書き込みとアーカイブを執行します。

---

## 3. システム構成とデータフロー

### 3.1 3層 API 統合
スクレイピングを排除し、信頼性の高いデータを得るために 3 つの階層で情報を取得します。
1. **Official Store API**: 日本語の基礎情報（名称、ジャンル）を取得。
2. **PICS Bridge (Docker)**: Steam 内部 DB から正確なトラックリストと多言語クレジットを取得。
3. **Local VDF**: ローカルの `appinfo.vdf` からコミュニティ定義のタグを取得。

### 3.2 処理パイプライン
1. **Scan**: ライブラリを走査し、未処理の AppID を特定。
2. **Identify**: MusicBrainz および Steam API から候補を収集し、スコアリング。
3. **Consolidate**: LLM がマッピングとクリーニングを推論。
4. **Transform**: 
   - **バッファリング**: `/tmp/sst-work/buffer_*` で安全に処理。
   - **変換**: FFmpeg による AIFF/MP3 への変換。
   - **タギング**: ID3v2.3 規格に準拠した書き込み。
5. **Package**: Ubuntu（WSL）側で ZIP アーカイブ化を行い、指定の出力先ディレクトリへ保存。Windows側への一括転送・展開はユーザが手動で行う（将来的に自動一括転送機能を実装予定）。

---

## 4. ディレクトリ構造

- `src/sst/`: コアアプリケーション・ロジック（モジュール化済み）。
- `data/`: SQLite データベース、タグキャッシュ、ユーザーデータ。
- `logs/`: 実行ログ（デバッグモードでは詳細なトレースを出力）。
- `output/`: 成果物（Archive および Review）。
- `docs/`: 技術仕様書、判定ロジック、タギング・ルール。

---

# S.S.T (Steam Soundtrack Tagger) - Core Architecture

This document defines the design philosophy, system architecture, and data flow of the S.S.T project. For detailed decision logic, see `LOGIC.md`. For tagging specifications, see `TAGGING_RULE.md`.

---

## 1. Core Principle: "Archive once, trust forever"

- **Goal**: Automated construction of a high-precision, zero-maintenance music library.
- **Policy**: Only items with 100% reliability are marked as `ARCHIVE`. Any doubt routes the item to the `REVIEW` folder for manual human verification.

---

## 2. Separation of Powers Architecture

S.S.T balances AI's flexible reasoning with programmatic rigor using a "Three Branches of Power" model:

- **Legislative (User/Config)**: Defines metadata source priority (Constitution) via `.env` or the `Config` class.
- **Judiciary (LLM/Auditor)**: Compares multiple sources and infers the best metadata based on context (Judgment).
- **Executive (System/Executor)**: Censors LLM output for physical cleanliness and executes tagging and archiving.

---

## 3. System Components & Data Flow

### 3.1 3-Tier API Integration
Avoids scraping and ensures data depth via three layers:
1. **Official Store API**: Basic localized info (Name, Genre).
2. **PICS Bridge (Docker)**: Accurate tracklists and credits directly from Steam's internal DB.
3. **Local VDF**: Community-defined tags extracted from local `appinfo.vdf`.

### 3.2 Processing Pipeline
1. **Scan**: Scans the library to identify unprocessed AppIDs.
2. **Identify**: Collects and scores candidates from MusicBrainz and Steam APIs.
3. **Consolidate**: LLM infers mapping and cleaning.
4. **Transform**: 
   - **Buffering**: Processed safely in `/tmp/sst-work/buffer_*`.
   - **Conversion**: FFmpeg conversion to AIFF/MP3.
   - **Tagging**: Writes metadata following the ID3v2.3 standard.
5. **Package**: Packaged as a ZIP archive and saved to the designated output directory on Ubuntu. Bulk transfer and extraction to Windows are handled manually by the user (Automated bulk transfer is planned for the future).
