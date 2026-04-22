# 環境変数設定ガイド (.env.example)

このガイドでは、S.S.T (Steam Soundtrack Tagger) をスタンドアロンCLIツールとして動作させるために必要な設定項目を解説します。

## 1. Steam 設定
- `STEAM_LIBRARY_PATH`: Steamライブラリのローカルパス（例: `/mnt/e/SteamLibrary`）。`steamapps/common` ディレクトリが含まれている必要があります。
- `STEAM_LANGUAGE`: メタデータ取得時の優先言語（例: `japanese`, `english`）。

## 2. ローカル処理設定
- `SST_WORKING_DIR`: 音声変換やタグ付け作業を行うための一時ディレクトリ。高速なストレージ（NVMe/SSD）を推奨します。
- `SST_DB_PATH`: 処理済みアルバムの追跡と重複実行のスキップに使用されるSQLiteデータベース (`sst_local_state.db`) のパス。

## 3. メタデータソース優先順位
- `METADATA_SOURCE_PRIORITY`: 信頼する情報の優先順位をカンマ区切りで指定します。
    - `MBZ`: MusicBrainz (トラックリストの高精度な情報源)。
    - `STEAM`: Steam Store API (デベロッパー/パブリッシャーの正本)。
    - `EMBEDDED`: 音声ファイル内の既存タグ。
    - *デフォルト*: `MBZ,STEAM,EMBEDDED`

## 4. AI / LLM (OpenAI互換)
「事実に基づくメタデータ整理」（正規化と競合解決）に使用します。
- `LLM_API_KEY`: プロバイダー（Gemini, OpenAI等）のAPIキー。
- `LLM_BASE_URL`: APIエンドポイント。OpenAI互換のプロバイダーであればすべてサポートします。
- `LLM_MODEL`: 使用するモデル名（例: `gemini-1.5-pro`）。
- **レート制限**:
    - `LLM_LIMIT_RPM`: 分間リクエスト数。
    - `LLM_LIMIT_TPM`: 分間トークン数。
    - `LLM_LIMIT_RPD`: 日間リクエスト数。

## 5. 外部API詳細
- `MUSICBRAINZ_USER_AGENT`: MusicBrainz APIの利用規約で必須です。形式: `AppName/Version (ContactURL)`。

---

## 注意事項
- **セキュリティ**: `.env` ファイルには機密性の高いAPIキーが含まれます。**絶対に Git にコミットしないでください。**
- **テンプレート**: `.env.example` を `.env` にコピーして設定を開始してください。
