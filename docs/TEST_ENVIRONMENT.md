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
テストは、以下の代表的な AppID に対して実行することを推奨します：
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
- [ ] `COMM` 欄の新しい書式（`[タグ1/ タグ2]`）の適用。
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
Tests should be run against these representative AppIDs:
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
- [ ] Application of the new `COMM` format (`[tag1/ tag2]`).
- [ ] Correct ID3v2.3 tagging for MP3.
