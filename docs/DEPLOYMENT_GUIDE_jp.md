# S.S.T 導入手順

## 1. 前提

S.S.T は Linux 上でのローカル実行を前提とします。

必要要素:

- Python 3.12+
- uv
- ffmpeg
- Steam ライブラリへのアクセス
- Steam ストア参照に必要な cookie / API 情報
- MusicBrainz / AcoustID / LLM の接続情報

## 2. セットアップ

### 2.1 依存関係の導入

```bash
uv sync
```

### 2.2 環境変数の準備

`.env.example` を基に `.env` を作成し、少なくとも次を埋めます。

- STEAM_INSTALL_PATH
- STEAM_LOGIN_SECURE
- STEAM_PICS_BRIDGE_URL
- SST_OUTPUT_DIR
- SST_WORKING_DIR
- SST_DB_PATH
- LLM_BACKEND
- LLM_BASE_URL
- LLM_API_KEY
- LLM_MODEL
- MBZ_CONTACT
- ACOUSTID_API_KEY

### 2.3 外部依存の確認

- `ffmpeg -version` が通ること
- LLM バックエンドへ疎通できること
- Steam PICS Bridge へアクセスできること

## 3. 実行

```bash
./sst --limit 10
```

必要に応じて処理件数や対象範囲を絞って段階的に確認してください。

## 4. 出力ディレクトリ

`SST_OUTPUT_DIR` 配下に少なくとも次を出力します。

- archive/
- review/

元の Steam ライブラリの音声ファイルは更新しません。

## 5. 導入時の確認観点

- Steam 商品情報が取得できるか
- ストアトラック一覧を復元できるか
- AcoustID / MusicBrainz に問い合わせできるか
- review に落ちた際に理由を追跡できるか

## 6. 運用上の注意

- API キーや cookie は `.env` で管理し、ハードコードしない
- LLM は判断補助であり、生成系の自由記述を許さない
- 旧仕様文書ではなく [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md) を正本として扱う