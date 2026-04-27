# act-13 TODO: Discord通知と信頼性の強化

目的: 長時間実行されるバッチ処理に対してリアルタイムのフィードバックを提供するため、マルチレベルのDiscord通知システムを実装し、システムの信頼性をさらに高める。

## 1. Discord通知システム (優先度: 最重要)
- [x] **設定の拡張**: `NOTIFY_ENABLED`、`NOTIFY_COOLDOWN`、および4つのWebhook URL（`CRITICAL`、`WARNING`、`INFO`、`COMPLETION`）をサポートするように `scout/src/scout/main.py` を更新。
- [x] **通知マネージャー**: Discord WebhookへのPOSTリクエストを処理する `scout/src/scout/notify.py` を作成。
- [x] **スロットリング/クールダウン**: `NOTIFY_COOLDOWN` ウィンドウ内で同じ種類の冗長な通知をスキップするロジックを実装。
- [x] **リッチな埋め込み (Embeds)**: 以下を含む美しいDiscord埋め込みメッセージをデザイン（エラーは赤、警告は黄、完了は緑）：
    - アルバム名とAppID
    - 分類結果（Archive/Review）
    - 処理時間
    - 失敗した理由（ある場合）

## 2. 統合とイベント
- [x] **セマンティック・ラベリング**: LLM フェーズ 1 でデータ異常（SFX混在など）を要約する `semantic_label` を生成するように更新。
- [x] **プログレスバーの同期**: `processor.py` にコールバックを導入し、`main.py` のマルチバー表示と完全同期。
- [x] **完了サマリー**: メインループ終了時に、総合的な「実行サマリー」を `COMPLETION` Webhookに送信。
- [ ] **サーキットブレーカー通知**: LLMの1日あたりの制限（RPD）に達してシステムが停止した場合、`CRITICAL` アラートを送信。

## 3. 信頼性の強化
- [x] **ネイティブ I/O バッファリング**: すべての音声変換と ZIP 圧縮を WSL2 ネイティブ ファイルシステム (ext4) で最初に実行し、その後 Windows マウントに移動 (アトミック移動) します。これにより、「invalid rice order」のような I/O ジッター エラーを排除します。

## 4. ドキュメント
- [ ] チームオンボーディング用の `docs/HANDOVER_act-13.md` を更新。
