# S.S.T (Steam Soundtrack Tagger) 技術引き継ぎドキュメント [Act-17 完了時点]

## 1. プロジェクト概要
S.S.T は、Steam上のサウンドトラックに高精度なメタデータを自動付与し、DJ機材互換のクリーンなファイルとしてアーカイブするローカルCLIツールである。
「一度のアーカイブで、一生の信頼を」を理念とし、疑わしいデータはすべて `Review` 判定とし、`Archive` には100%の信頼性を担保する。

## 2. 現在のアーキテクチャ (Ultimate Data Mode)
以下の「3層APIアーキテクチャ」によりメタデータを収集・統合している。

*   **階層1 (Official Store API)**: `appdetails` から日本語のアルバム名、公式ジャンル、リリース日を取得。
*   **階層2 (Local PICS Bridge)**: Cloudflareの制限を回避するため、Dockerを用いたローカルのSteamCMD APIブリッジ (`steamcmd/api:latest`) を経由し、Steamの内部DB (PICS) から極めて正確なトラックリストやクレジット情報を抽出。
*   **階層3 (Steam Web API / User Tags)**: Web APIを利用してユーザータグを取得し、公式ジャンルを補完。

## 3. 重要な技術仕様と直近の改善点 (Act-17)
1.  **LLM推論バックエンドの Docker `llama-server` への移行**:
    - 16GB VRAM (RTX 4090 Laptop) 環境において、Ollamaの「`OLLAMA_NUM_PARALLEL` > 1 設定時に `num_ctx` が 4096 トークンに強制制限される」というハードコードされた仕様（防壁）が判明。
    - 巨大なサウンドトラック（100曲以上など）の処理精度が著しく低下する問題を根本解決するため、推論バックエンドを公式の Docker コンテナ `ghcr.io/ggml-org/llama.cpp:server-cuda` へ完全移行した。
    - これにより、16GB VRAM 環境でも **32768 トークンの広大なコンテキストと複数並列処理を両立** させることが可能となった。
2.  **Adaptive LLM Router（動的ルーティング機能）の実装**:
    - `scout/src/scout/runner.py` および `processor.py` に、アルバムの曲数に応じたモデルの使い分けと並列数制御を実装。
    - **Small (<=50曲)**: 並列ワーカー（デフォルト: 2）で高速処理。
    - **Medium (51-100曲) / Large (>100曲)**: VRAMのオーバーフローを防ぐため、**単一ワーカー**で広大なコンテキスト（16K / 32K）を確保して安全に処理。
3.  **並列ワーカー数算出バグの修正**:
    - 外部API（`OPENAI_COMPATIBLE`）利用時に、ローカル推論であっても過剰なスレッド（10ワーカー等）が生成されるバグを修正。`.env`の `MAX_PARALLEL_ALBUMS` を厳格に遵守するよう改善した。
4.  **精度の劇的向上**:
    - コンテキスト制限の撤廃により、100件のテストデータにおいて Archive 成功数が 54件 から **73件** へと大幅に向上。システムの「100% 信頼できるアーカイブ」の目標に大きく前進した。

## 4. 実行環境
*   **OS**: Windows 11 / WSL2 (Ubuntu 24.04)
*   **CPU**: Core i9-14900HX
*   **Memory**: 64GB
*   **dGPU**: NVIDIA GeForce RTX 4090 Laptop (16GB)
*   **Platform**: Python 3.12+ (uv 経由)
*   **LLM 推論**: Docker `llama-server` (`ghcr.io/ggml-org/llama.cpp:server-cuda`) + OpenAPI 互換通信
*   **モデル管理**: Ollama (ダウンローダーとしてのみ使用)
*   **DB/メタデータ**: SQLite / FFmpeg / Mutagen

## 5. 現在のディレクトリ構造 (主要部分)
```text
S.S.T/
├── .env                  (秘匿情報・各種設定, LLM_BACKEND=OPENAI_COMPATIBLE)
├── sst                   (起動シェルスクリプト, データベースリセット等)
├── Models/
│   ├── LLM_setup.sh      (Docker llama-server を用いたセットアップスクリプトに更新済み)
│   └── blobs/            (Ollamaからシンボリックリンクまたはコピーされた.ggufファイル群)
├── scout/                (Pythonコアロジック)
│   ├── pyproject.toml
│   └── src/scout/
│       ├── main.py       (エントリポイント, Config定義)
│       ├── runner.py     (JobRunner: Adaptive LLM Router とバリア同期ロジック)
│       ├── processor.py  (LocalProcessor: メイン処理フロー, 動的コンテキストサイズ切替)
│       ├── llm.py        (LLMOrganizer: OpenAI互換APIでの動的 num_ctx パラメータの付与)
│       └── ...
├── docs/                 (環境構築ガイド・マニュアル等)
└── output/               (処理完了後のZIPファイル格納先)
```

## 6. 次に着手すべきタスク
1.  **実運用環境での大規模テスト**:
    - アーキテクチャが劇的に変化したため、残りの全ライブラリに対して一括処理（`./sst --all`）を行い、エラーや VRAM 溢れ（Docker 側のOOMクラッシュ等）が発生しないか長期安定性を確認する。
2.  **Review データの消化と `--finalize` の動作確認**:
    - 抽出された Review 対象の ZIP を展開し、MP3tag 等で手動修正を行った後、`./sst --finalize` が正しく DB に情報を書き戻すかの運用フローを通しでテストする。
3.  **モデルラインナップの最終決定**:
    - 現在は `qwen2.5:7b-instruct` をベースにテストを行ったが、`qwen3.5:9b` や `phi-4:14b` など、より高精度なモデルを 16GB VRAM 内でどこまで詰め込めるか、必要に応じて微調整を行う。
4.  **MTP (Multi-Token Prediction) の動向注視**:
    - 今回は Ollama の制限により見送ったが、今後推論エンジンが安定して MTP に対応した場合、導入することでさらなる高速化（2倍〜3倍）が見込めるため、アップデートをチェックしておくこと。