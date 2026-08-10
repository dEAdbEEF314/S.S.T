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

## 3. 安全なマウントと実行プロファイル

S.S.Tはローカル単一ユーザー運用を前提とします。Steamライブラリの元音源は読み取り専用で扱い、出力先、`SST_WORKING_DIR`、ログ、DBは別領域に配置してください。Linuxでは、Steamライブラリを可能な限り読み取り専用マウント（`ro`）で提供してください。これはアプリケーションのパス検証を置き換えるものではなく、誤操作時の最終安全弁です。

- 通常運用（`LOG_LEVEL=INFO`、既定値）: 処理完了後に `SST_WORKING_DIR` の中間生成物を削除します。
- 診断運用（`--dev` または `LOG_LEVEL=DEBUG`）: `final_<AppID>_*` と `buffer_<AppID>_*` を保持します。中間生成物にはローカルパス、LLM入出力、タグ情報が含まれ得るため、共有前に確認してください。
- `.env` の認証情報は、ログレベルに関係なくログへ出力しません。
- Steam説明文など外部由来のテキストは不信データとして扱い、LLM出力はJSON契約・参照範囲・重複・未割当を機械的に検証します。

## 4. 実行

```bash
./sst --limit 10
```

必要に応じて処理件数や対象範囲を絞って段階的に確認してください。

## 5. 出力ディレクトリ

`SST_OUTPUT_DIR` 配下に少なくとも次を出力します。

- archive/
- review/

元の Steam ライブラリの音声ファイルは更新しません。

## 6. 導入時の確認観点

- Steam 商品情報が取得できるか
- ストアトラック一覧を復元できるか
- AcoustID / MusicBrainz に問い合わせできるか
- review に落ちた際に理由を追跡できるか

## 7. 運用上の注意

- API キーや cookie は `.env` で管理し、ハードコードしない
- LLM は判断補助であり、生成系の自由記述を許さない
- 旧仕様文書ではなく [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md) を正本として扱う