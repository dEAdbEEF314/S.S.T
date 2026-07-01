# S.S.T テスト環境仕様書

このドキュメントは、S.S.T のスタンドアロン CLI ロジックおよび API 統合を検証するための標準的なテスト環境を定義します。

## 1. コア・スタック
- **OS**: Windows 11 + WSL2 (Ubuntu 24.04推奨)
- **ランタイム**: `uv` によって管理された Python 3.12以上。
- **メディアエンジン**: FFmpeg (WSL の `PATH` 内で利用可能であること)。
- **データベース**: SQLite 3。

## 2. インフラストラクチャ (Local Environment)
「究極データ取得モード」の検証には、以下のコンポーネントが稼働している必要があります：
- **PICS Bridge (Docker)**: `steamcmd/api:latest` (Port 8080)。
- **LLMサービス**: ユーザー各自で用意した環境 (Gemini, Ollama, OpenAI互換API) が稼働し、`.env` で設定されていること。

## 3. データソース (検証ターゲット)
テストは、以下の代表的な AppID に対して実行することを推奨します。これらは運用上有用だった**代表例**であり、システムや自動テストにハードコードされた必須ケースではありません：
1.  **1027880** (A Dance of Fire and Ice OST): モダンな PICS トラックリストと MusicBrainz 直接リンクの検証。
2.  **1586580** (Narita Boy): 複雑なファイル名からのトラック番号補完 (`override_track`) の検証。
3.  **1270860** (Exit the Gungeon): FFmpeg 警告（invalid rice order）が発生するケースの検証。

## 4. 環境変数 (.env)
有効なテスト環境には以下が必須です：
- `STEAM_WEB_API_KEY`: コミュニティタグ取得用。
- `STEAM_PICS_BRIDGE_URL`: `http://localhost:8080/v1/info/` に設定。
- `LLM_BACKEND`: `GEMINI`, `OLLAMA` (Native Ollama 推奨) または `OPENAI_COMPATIBLE`。

## 5. 検証チェックリスト
- [ ] ローカル出力先（`./output` 等）への正しい ZIP アーカイブの生成と保存（展開なし）。
- [ ] `COMM` 欄に `親ゲーム名, [タグ1/ タグ2]..., AppID, URL` の情報が連結されていること。既存の埋め込みコメントがある場合は、その先頭保持も確認する。
- [ ] MP3 に対する正確な ID3v2.3 タグ付け。

---

# S.S.T Test Environment Specification

This document defines the standard test environment for validating S.S.T's standalone CLI logic and API integrations.

## 1. Core Stack
- **OS**: Windows 11 + WSL2 (Ubuntu 24.04 recommended).
- **Runtime**: Python 3.12+ managed by `uv`.
- **Media Engine**: FFmpeg (must be available in WSL `PATH`).
- **Database**: SQLite 3.

## 2. Infrastructure (Local Environment)
For the "Ultimate Data Mode", the following components must be active:
- **PICS Bridge (Docker)**: `steamcmd/api:latest` (Port 8080).
- **LLM Service**: Your own LLM environment (Gemini, Ollama, OpenAI-compatible APIs) running and configured in `.env`.

## 3. Data Sources (Validation Targets)
Tests should be run against these representative AppIDs. These are **recommended examples** from past validation runs, not hard-coded mandatory fixtures in the system or automated tests:
1.  **1027880** (A Dance of Fire and Ice OST): Modern PICS tracklist + Direct MBZ links.
2.  **1586580** (Narita Boy): Track number completion (`override_track`) from complex filenames.
3.  **1270860** (Exit the Gungeon): Handling cases with FFmpeg warnings (e.g., invalid rice order).

## 4. Environment Variables (.env)
A valid test environment MUST have:
- `STEAM_WEB_API_KEY`: For official community tag retrieval.
- `STEAM_PICS_BRIDGE_URL`: Set to `http://localhost:8080/v1/info/`.
- `LLM_BACKEND`: `GEMINI`, `OLLAMA` (Native Ollama recommended), or `OPENAI_COMPATIBLE`.

## 5. Verification Checklist
- [ ] Correct generation and preservation of the ZIP archive to the local output directory (e.g., `./output`) without extraction.
- [ ] The `COMM` field contains appended `Parent Name, [tag1/ tag2]..., AppID, URL` information. If an embedded comment already exists, verify that it is preserved at the front.
- [ ] Correct ID3v2.3 tagging for MP3.
