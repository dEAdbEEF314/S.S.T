# S.S.T (Steam Soundtrack Tagger) Project Handover

## 1. プロジェクトのゴール (Project Goal)
Steamからダウンロードした多種多様なフォーマット・状態のサウンドトラック音源を自動でスキャンし、**「1トラックにつき最適な1ファイル（最高音質）」**を選定した上で、ローカルの埋め込みタグ・Steam API・MusicBrainzの情報をLLM（Gemini等）を用いて**「推論なしで整理整頓」**し、統一された高精度なメタデータを持つAIFF/MP3ファイルとしてSeaweedFS(S3)にアーカイブ（または人間によるレビュー待ち）すること。

## 2. 現在のアーキテクチャと状態 (Current Architecture & State)
*   **アーキテクチャ**: 以前の「Scout(スキャン) -> S3 -> Prefect(分散タスク管理) -> Worker(処理)」という分散アーキテクチャは**廃止**されました。現在はネットワークI/Oと環境占有を最小化するため、**「Windows(WSL2)上のScoutがローカルで変換からLLMへの問い合わせ、S3への最終アップロードまで全てを一貫して行うローカル完結型（エッジ処理）」**に移行しています。
*   **進捗状態 (Act-9)**:
    *   全コンポーネントのローカル統合（`scout/src/scout/` 配下への集約）が完了。
    *   S3（SeaweedFS）の署名エラー問題を回避するため、Filer API（HTTP POST/PUT）によるアップロードを実装し、安定稼働中。
    *   LLMによるメタデータの整理機能は動作していますが、**「アルバム全曲を1プロンプトで投げると出力が途切れる（1トラックしか返ってこない）」**という致命的な問題が発覚しました。
    *   `metadata.json` や音源ファイルに書き込まれる最終的なタグデータ（Album ArtistやSource、Commentなど）の精度と「真実性」に不備があり、厳格なフォールバックロジックの適用が急務です。

## 3. 参照すべき重要ドキュメント (Key Reference Documents)
*   **`docs/TAGGING_RULE.md` / `docs/TAGGING_RULE_jp.md`**: 音源ファイルの採用優先順位（Lossless -> AIFF, Lossy -> MP3）と、メタデータ（ID3v2等）のマッピングルール、LLMのプロンプトに対する絶対的な制約（ハルシネーション禁止）が記された**バイブル**です。いかなる実装もこのルールに反してはなりません。
*   **`.env.example`**: 動作に必要な環境変数の定義。S3エンドポイント、Filer URL、LLMのAPIキーやレートリミット（RPM, TPM, RPD）、およびタイムゾーン（`TZ`）が定義されています。

## 4. 次にやるべきこと（TODO リスト）
新しいエージェントは、以下の課題を順に解決してください。

### ① Parent Game (親ゲーム) メタデータの取得強化 (`scout/src/scout/scanner.py`)
*   **課題**: `COMM`（Comment）タグには「サウンドトラック」ではなく「元となったゲーム本編」のジャンルやタグを入れる仕様（`TAGGING_RULE.md` 参照）だが、現状はサントラの情報しか取っていない。
*   **タスク**: Steam APIのレスポンスから `fullgame` オブジェクト（親ゲームのAppID）を探し、存在する場合は追加でAPIを叩いて親ゲームの情報を取得・結合する。

### ② LLM処理の「チャットセッション化」と1トラックずつの処理 (`scout/src/scout/llm.py`)
*   **課題**: アルバム全曲の生データを一度に送ると出力が途切れる。
*   **タスク**: LLM APIの `messages` 配列を活用し、`System Prompt` と `Global Album Context` を送った後、**「Track 1のデータ送信 -> JSON受信」「Track 2のデータ送信 -> JSON受信」というように、文脈を保持したままループで1トラックずつ問い合わせる**アーキテクチャに書き換える。
*   **制約**: `.env` のレートリミット（特に `LLM_LIMIT_RPM=30`）に確実に到達するため、`DistributedRateLimiter` によるスリープ（待機）を許容して確実に全曲処理しきる。

### ③ メタデータ確定ロジックと Source の厳格化 (`scout/src/scout/processor.py`)
*   **課題**: Album ArtistなどがSteam APIから取れているのに、LLMが返さなかった時にnullになってしまうなど、フォールバックの適用タイミングがおかしい。
*   **タスク**: 音源ファイルにタグを書き込む**前**に、Steam APIの情報（`Developer | Publisher` など）を確定値として強制適用する。
*   **タスク**: `metadata.json` の `source` フィールドに、そのトラックが最終的にどうやってタグ付けされたか（`LLM Consolidated`, `MusicBrainz Match`, `Embedded Tag Fallback`, `Steam API Fallback`）を正確に記録する。

### ④ 厳格な Review 送り条件とバンドル化 (`scout/src/scout/processor.py`)
*   **課題**: 必須項目が欠落していてもサイレントに `archive/` へ送られてしまう。
*   **タスク**: 最終メタデータにおいて `TIT2` (Title) または `TRCK` (Track Number) が空・不明な場合は、アルバム全体を `review/` ステータスにする。
*   **タスク**: `review/` 行きの場合、ユーザーが後から手作業で修正できるよう、`llm_log.json`（全チャット履歴）と `raw_metadata.json`（全生データソース）を確実に同梱する。

### ⑤ MusicBrainz のデバッグログ出力と Timezone 対応
*   **タスク**: MusicBrainzから取得する情報が乏しい原因をユーザーが調査できるよう、MBへのリクエストクエリと生のJSONレスポンスを `mbz_log.json` として同梱する。
*   **タスク**: `processor.py` 等でタイムスタンプを生成する際、UTCハードコードではなく `os.environ.get("TZ", "UTC")` を用いて、タイムゾーン付きのローカル時間（JST等）で保存する。

---
**エージェントへの指示:** このファイルの内容を理解したら、まずは「① Parent Game メタデータの取得強化」と「② LLM処理のチャットセッション化」から実装を開始してください。
