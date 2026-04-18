# 環境変数設定ガイド (.env.example)

S.S.Tシステムを動作させるために必要な外部要素の設定項目を解説します。

### 1. ストレージ (SeaweedFS / S3)
システムはS3互換のオブジェクトストレージを使用してデータをやり取りします。
- `S3_ENDPOINT_URL`: ストレージサーバーのURL（SeaweedFSの場合はデフォルト 8333 ポート）。
- `S3_BUCKET_NAME`: データの保存先バケット名。

### 2. オーケストレーション (Prefect)
ワークフローの状態を管理する Prefect Core との通信設定です。
- `PREFECT_API_URL`: Prefect サーバーのAPIエンドポイント。
- `PREFECT_FLOW_NAME`: 実行するフローの名前（デフォルト: `SST-Production-Pipeline`）。CoreとScoutで一致させる必要があります。

### 3. AI / LLM (OpenAI互換)
音楽タイトルの正規化や判定の検証に使用します。
- `LLM_API_KEY`: 使用するAIモデルのAPIキー。
- `LLM_BASE_URL`: OpenAI以外のプロバイダー（Anthropic, Local LLM 等）を使用する場合に変更します。

### 4. 外部音楽データベース
楽曲の識別に使用する外部サービスの設定です。
- `ACOUSTID_API_KEY`: 音響フィンガープリント照合に必須です。
- `MUSICBRAINZ_USER_AGENT`: MusicBrainz APIの規約に従い、連絡先を含む文字列を指定します。

### 5. Steamライブラリ (Scout Container)
Steamで購入した楽曲ファイルをスキャンするためのローカルパスです。
- `STEAM_LIBRARY_PATH`: `steamapps/common` ディレクトリを含むルートパスを指定します。

---

## 注意事項
- `.env` ファイルは機密情報を含むため、**絶対に Git にコミットしないでください**。
- 本リポジトリには `.env.example` をテンプレートとして含めています。
