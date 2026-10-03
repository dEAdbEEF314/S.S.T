# S.S.T セキュリティ・プラクティス ガイド

本文書は、S.S.T (Steam Soundtrack Tagger) におけるセキュリティ設計、脆弱性防御、および運用ガイドラインを定めます。

---

## 1. 脅威モデルと防御方針

S.S.T は外部の各種メタデータ（Steam Store API, MusicBrainz, AcoustID, Discord Webhook）およびローカルファイルシステムと連携します。外部から提供されるデータや設定ファイルが侵害された場合でも、ローカル環境および内部ネットワークを保護するため、多層防御を適用しています。

### 主要な防御項目

1. **SSRF (Server-Side Request Forgery) 防御**
2. **パストラバーサル (Path Traversal) 防御**
3. **機密情報の平文露出防止 (Secret Masking / Sanitization)**
4. **元データの完全読み取り専用 (Read-Only) 保護**
5. **設定ファイル (.env) のパーミッション監査**

---

## 2. SSRF 防御 (safe_validate_url / safe_download_image)

### 背景と脅威
外部メタデータ（MusicBrainz や Steam Store）に悪意ある URL（例: `http://169.254.169.254/latest/meta-data/` や `http://127.0.0.1:11434/api/generate`）が含まれていた場合、サーバー内部やクラウドの機密情報が攻撃者に流出したり、内部 API が不正操作される危険があります。

### 実装対策
`src/sst/utils.py` の `safe_validate_url` および `src/sst/processor_support.py` の `safe_download_image` により以下の検査を実施します:

- **スキーム検証**: `http://` および `https://` のみを許可。`file://`, `ftp://`, `javascript:`, `gopher://` 等は即時遮断。
- **プライベート・ループバック IP 検査**: ホスト名を IP アドレスに名前解決し、以下に該当する場合はリクエストを遮断:
  - ループバックアドレス (`127.0.0.0/8`, `::1`, `localhost`)
  - RFC 1918 プライベートアドレス (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
  - リンクローカル / クラウドメタデータ (`169.254.0.0/16`, `fe80::/10`)
  - マルチキャスト / 未指定 / 予約済みアドレス (`0.0.0.0/8` 等)
- **Content-Type 検証**: ダウンロード時、レスポンスの Content-Type が画像（`image/*` 等）であることを確認し、実行可能ファイルや HTML 等の受信を防止。
- **ストリーミング & バイト上限制御**: `IMAGE_DOWNLOAD_MAX_BYTES` (既定: 25MB) を超えるデータを受信した場合は即座に接続を切断し、メモリ枯渇 (DoS) を防止。

---

## 3. パストラバーサル防御 (is_safe_subpath)

### 背景と脅威
アルバム名やステータス文字列（`archive`, `review`）に `../../` 等の相対パスが含まれると、出力先ディレクトリ外（例: `/etc/` やホームディレクトリ）にファイルが書き出される危険があります。

### 実装対策
- `src/sst/utils.py` の `is_safe_subpath(target_path, base_dir)` により、出力先ファイルが必ず基底ディレクトリ配下にあることを `Path.resolve().is_relative_to(...)` で厳格に検証。
- `src/sst/packager.py` において、`clean_status` および `safe_name` を英数字と安全な記号のみに正規化し、検証を通過しないパスへの書き込みを拒否。

---

## 4. 機密情報マスキング (mask_secret / sanitize_log_text)

### 背景と脅威
API キー（`LLM_API_KEY`, `ACOUSTID_API_KEY`）や認証情報（`STEAM_LOGIN_SECURE`）、Discord Webhook URL のトークンが、エラーハンドリング時の例外トレースバックやログファイル、成果物 JSON に平文で残るリスクがあります。

### 実装対策
- `src/sst/utils.py` の `mask_secret`: 表示用の API キー文字列を `sk-1...cdef` のように前後数文字のみ残して伏字化。
- `src/sst/utils.py` の `sanitize_log_text`:
  - Discord Webhook URL (`https://discord.com/api/webhooks/<id>/<token>`) のトークン部分を自動で `[REDACTED_WEBHOOK_TOKEN]` に置換。
  - 既知のシークレット文字列や汎用 API キーパターンを `[REDACTED]` に自動置換。
- `src/sst/notify.py`: 通知送信失敗時の例外メッセージから Webhook トークンを除去してログ出力。

---

## 5. 元データの Read-Only 原則

- Steam ライブラリ内の元ファイル（音声ファイル、VDF キャッシュ、画像等）に対しては、いかなる場合も書き込み・移動・削除操作を行いません。
- すべての変換・タグ付け処理は一時ディレクトリ (`SST_WORKING_DIR`) にコピーした作業用ファイル上で行われます。

---

## 6. 設定ファイル (.env) のパーミッション監査

- `.env` には外部 API キーや認証 Cookie が格納されます。
- S.S.T 起動時に `check_env_security` が `.env` のファイル権限を検査し、他ユーザーからの読み取り権限（World-Readable）がある場合は警告ログを出力して `chmod 600 .env` を推奨します。
