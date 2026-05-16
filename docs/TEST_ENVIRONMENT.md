# S.S.T テスト環境仕様書

このドキュメントは、S.S.T のスタンドアロン CLI ロジックおよび API 統合を検証するための標準的なテスト環境を定義します。

## 1. コア・スタック
- **OS**: WSL2 (Ubuntu 22.04以上)
- **ランタイム**: `uv` によって管理された Python 3.12以上。
- **メディアエンジン**: FFmpeg (WSL の `PATH` 内で利用可能であること)。
- **データベース**: SQLite 3。

## 2. インフラストラクチャ (Local Docker)
「究極データ取得モード」の検証には、ローカル PICS ブリッジが稼働している必要があります：
- **コンテナ**: `steamcmd/api:latest`
- **公開ポート**: `8080` (内部ポート `8000` からマップ)。
- **エンドポイント**: `http://localhost:8080/v1/info/{AppID}`

## 3. データソース (検証ターゲット)
テストは、以下の代表的な AppID に対して実行することを推奨します：
1.  **1027880** (A Dance of Fire and Ice OST): モダンな PICS トラックリストと MusicBrainz 直接リンクの検証。
2.  **1113510** (Hellsinker): 深いディレクトリ構造と、レガシー/手動レビューケースの検証。
3.  **1167720** (Artifact Adventure): 異なる品質（AIFF/MP3）の混在に対する重複排除ロジックの検証。

## 4. 環境変数 (.env)
有効なテスト環境には以下が必須です：
- `STEAM_WEB_API_KEY`: `IStoreBrowseService` 用のアクティブなキー。
- `STEAM_PICS_BRIDGE_URL`: `http://localhost:8080/v1/info/` に設定。
- `LLM_BACKEND`: `GEMINI`, `OLLAMA` (非推奨), または `OPENAI_COMPATIBLE` (Docker llama-server を使用する場合に推奨)。

## 5. 検証チェックリスト
- [ ] Windows 側での自動 ZIP 展開（ネイティブ `tar.exe` 経由）。
- [ ] MP3 に対する正確な ID3v2.3 タグ付け。
- [ ] 一時作業バッファ（`buffer_*`）の確実な削除。
- [ ] SQLite `steam_store_data` への PICS データの永続化。

---

# S.S.T Test Environment Specification

This document defines the standard test environment for validating S.S.T's standalone CLI logic and API integrations.

## 1. Core Stack
- **OS**: WSL2 (Ubuntu 22.04+)
- **Runtime**: Python 3.12+ managed by `uv`.
- **Media Engine**: FFmpeg (must be available in WSL `PATH`).
- **Database**: SQLite 3.

## 2. Infrastructure (Local Docker)
For the "Ultimate Data Mode", a local PICS bridge must be active:
- **Container**: `steamcmd/api:latest`
- **Exposed Port**: `8080` (mapped to internal `8000`).
- **Endpoint**: `http://localhost:8080/v1/info/{AppID}`

## 3. Data Sources (Validation Targets)
Tests should be run against these representative AppIDs:
1.  **1027880** (A Dance of Fire and Ice OST): Modern PICS tracklist + Direct MBZ links.
2.  **1113510** (Hellsinker): Deep directory structure + Legacy/Manual Review case.
3.  **1167720** (Artifact Adventure): Mixed quality formats (AIFF/MP3) for deduplication testing.

## 4. Environment Variables (.env)
A valid test environment MUST have:
- `STEAM_WEB_API_KEY`: Active key for `IStoreBrowseService`.
- `STEAM_PICS_BRIDGE_URL`: Set to `http://localhost:8080/v1/info/`.
- `LLM_BACKEND`: `GEMINI`, `OLLAMA` (Legacy), or `OPENAI_COMPATIBLE` (Recommended for local Docker llama-server).

## 5. Verification Checklist
- [ ] Automatic ZIP extraction on Windows (via native `tar.exe`).
- [ ] Correct ID3v2.3 tagging for MP3.
- [ ] Clean temporary buffer removal.
- [ ] PICS data persistence in SQLite `steam_store_data`.
