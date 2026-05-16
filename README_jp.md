# S.S.T (Steam Soundtrack Tagger)

S.S.T は、Steamで購入したサウンドトラックを自動的に識別し、メタデータを補完してタグ付けを行う、高精度なスタンドアロンCLIツールです。
Steam API、MusicBrainz、およびローカルの埋め込みタグからの情報を、LLM（大規模言語モデル）を用いた「事実に基づくメタデータ整理」によって統合します。

## 🚀 システムアーキテクチャ: スタンドアロン・エッジ処理

S.S.T は **ローカル完結型エッジプロセッサ** です。音声変換、LLMによる統合、タグ付けを含むすべての重い処理は、Steamライブラリが存在するローカルマシン（WSL2/Windows等）上で実行されます。これにより、ネットワークI/Oを最小限に抑え、プライバシーと制御を最大限に確保します。

### コア・パイプライン
1.  **スキャン**: Steamライブラリをスキャンし、ローカルのSQLiteデータベースを参照して処理済みアルバムを特定します。
2.  **情報補完 (3層APIアーキテクチャ)**:
    - 階層1 (Official Store API): 日本語のアルバム名、公式ジャンル、リリース日。
    - 階層2 (Local PICS Bridge): SteamCMD経由での極めて正確なトラックリスト。
    - 階層3 (MusicBrainz / Embedded): 音楽DBと既存のタグ情報。
3.  **統合 (三権分立によるメタデータ評価)**:
    - ユーザー（立法）が定めた `METADATA_SOURCE_PRIORITY` に従い、LLM（司法）が情報を比較・推論し、システム（行政）が物理的なクリーンネスを強制検閲します。
4.  **処理**: 音声を変換（Lossless -> AIFF, Lossy -> MP3）し、DJ機材互換の厳格な ID3v2.3 タグを書き込みます。
5.  **パッケージ化**: 音声ファイルと詳細な処理ログ（`BASIS_for_CLASSIFICATION.md` 等）をZIPアーカイブにまとめ、`output/` ディレクトリに出力します。

## ✨ 主な機能 (Act-18 アップデート)

-   **Adaptive LLM Router**: 曲数に応じてモデルとコンテキストサイズ（8K/16K/32K）を動的に切り替え、巨大なアルバムでも VRAM を溢れさせずに安全に並列処理します。
-   **三権分立ロジック**: 
    - LLMは音楽的文脈から最適な曲名を推論しますが、最終的なタグ付けはシステムの厳格な「Dirty Tags 排除ルール」によって検閲されます。
    - いかなる公式ソースであっても、DJ機材での視認性を損なうトラック番号（例: `01. Title`）は強制的にクリーニングされます。
-   **Fast-Track**: ソース間で情報が完全に一致している場合、LLMの推論をバイパスして決定論的に高速処理します。
-   **ローカル状態管理**: SQLiteデータベースを使用してすべての処理履歴を追跡し、無駄なAPIコールを防止します。

## 🛠️ 技術スタック

-   **言語**: Python 3.12+
-   **パッケージマネージャー**: [uv](https://github.com/astral-sh/uv) (必須)
-   **AI**: Docker + `llama-server` (16GB VRAM 環境での OpenAI互換 API を推奨)
-   **音声処理**: FFmpeg, Mutagen
-   **データベース**: SQLite

## 🏗️ セットアップ

### 1. 事前準備
-   **LLM 推論環境**: `Models/LLM_setup.sh` を参照し、Docker と `llama-server` を用いた環境を構築してください。
-   **Local PICS Bridge**: Steam内部DBにアクセスするためのブリッジを起動します。
    ```bash
    docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
    ```
-   `.env` を設定してください（`.env.example` を参照。`METADATA_SOURCE_PRIORITY` が最重要です）。
-   `uv` を使用して依存関係をインストールします：
    ```bash
    cd scout && uv sync
    ```

### 2. 実行
```bash
# uv run を使用した実行
uv run scout/src/scout/main.py --limit 10

# または、ラップされたシェルスクリプトを使用
./sst --limit 10
```

## ⚠️ 整合性とレビューのルール

-   **失敗の隔離**: 必須タグの欠落、LLMの確信度不足、システムによる強制クリーニングの発動などがあった場合、自動的に `output/review/` に振り分けられます。
-   **透明性の確保**: レビューに回された理由はすべて `BASIS_for_CLASSIFICATION.md` に明記され、「なぜシステムが却下したのか（System Decision Reason）」が即座に確認できます。
-   **Finalize**: レビュー対象をMP3tag等で手動修正した後、`./sst --finalize` を実行することでDBを更新します。

## 📄 ライセンス
TBD
