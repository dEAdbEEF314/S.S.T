# Discord Integration Specification

## 1. 概要 (Overview)
S.S.T (Steam Soundtrack Tagger) は、長時間のバッチ処理が想定されるため、処理の進捗や手動介入が必要なイベント（Reviewへの降格等）をユーザーへ非同期に通知するための Discord Webhook 連携機能を備えています。

本ドキュメントでは、通知機能の仕様、環境変数の設定方法、および各通知レベルの振る舞いについて定義します。

## 2. 実装モジュール
コアロジックは `src/sst/notify.py` の `NotificationManager` クラスとして実装されており、設定（`config.py`）に基づいて自動的に初期化・ルーティングされます。

## 3. 設定項目 (Environment Variables)
連携機能を有効にするには、`.env` ファイルに以下の環境変数を設定します。Webhook URLは通知レベル（重要度）ごとに別々のチャンネル（または同一チャンネル）に分割して割り当てることが可能です。

| 環境変数名 | 型 | デフォルト値 | 説明 |
| :--- | :--- | :--- | :--- |
| `NOTIFY_ENABLED` | bool | `False` | 通知機能自体の ON/OFF を制御します。 |
| `NOTIFY_COOLDOWN` | int | `60` | 同一メッセージの連続送信をブロックするクールダウン秒数。 |
| `DISCORD_WEBHOOK_CRITICAL` | str | `None` | システムクラッシュや致命的なエラー発生時のWebhook URL。 |
| `DISCORD_WEBHOOK_WARNING` | str | `None` | `Review` 送り等、手動確認が必要な警告発生時のWebhook URL。 |
| `DISCORD_WEBHOOK_INFO` | str | `None` | `Archive` への処理完了など、一般的な情報通知のWebhook URL。 |
| `DISCORD_WEBHOOK_COMPLETION` | str | `None` | バッチ処理の完走など、マイルストーン到達時のWebhook URL。 |

## 4. 通知レベルと Embed フォーマット
Discordの「Embed（埋め込み）」形式を使用し、視覚的にわかりやすい色分けとアイコンを付与して送信されます。

| レベル | メソッド名 | アイコン | テーマカラー | 主な用途 |
| :--- | :--- | :--- | :--- | :--- |
| **CRITICAL** | `notify_critical()` | 🚨 | 赤 (`0xe74c3c`) | プロセスの強制終了、APIの完全なブロック、DB障害など |
| **WARNING** | `notify_warning()` | ⚠️ | 黄 (`0xf1c40f`) | ValidatorによるArchiveからの降格（Review Required）など |
| **INFO** | `notify_info()` | ℹ️ | 青 (`0x3498db`) | 各アルバムのArchive処理完了通知（※大量発生を避けるため要約して送信するか検討） |
| **COMPLETION** | `notify_completion()` | 🏁 | 緑 (`0x2ecc71`) | 指定された全バッチ処理の完了通知、サマリーの報告など |

### 4.1. ペイロード構造 (Payload Structure)
送信されるJSONペイロードは以下の構造を含みます。
- `title`: 通知のタイトル（アイコン付き）
- `description`: 発生した事象の詳細メッセージ
- `color`: レベルに応じた16進数カラーコード
- `fields`: 追加の情報（AppID、処理された曲数、LLMの判定スコア、決定の理由など）を格納するキー・バリューの配列。
- `timestamp`: 発生時刻（UTC）
- `footer`: `"S.S.T (Steam Soundtrack Tagger)"`

## 5. Cooldown 制御の仕組み (Anti-Spam)
短時間に大量のエラーが発生したり、再試行ループに入った際に、DiscordのAPI Rate Limit（レート制限）に抵触したり、チャンネルがスパム状態になるのを防ぐため、内部で「Cooldown（冷却）」制御を行っています。

- **判定キー**: `"{level}:{title}"` (例: `warning:⚠️ Review Required: FlatOut 4`)
- **ロジック**: 前回送信時刻から `NOTIFY_COOLDOWN` 秒（デフォルト60秒）が経過していない場合、その通知リクエストはログ（DEBUGレベル）に記録された上で **破棄（Suppressed）** されます。

## 6. ユースケース (現行の動作)
現在のバッチ処理（実戦テスト）では、主に以下のタイミングで通知が行われています。

1. **バッチ実行完了 (Completion)**
   - 全てのキューを消化し、正常にプログラムが終了したタイミングで1度だけ送信されます。
2. **Reviewへの降格警告 (Warning)**
   - `validator.py` で物理チェック（タグのゴミや重複）に引っかかった際、その理由（Issues）やLLMのスコア（Decision Ratio）を `fields` に添付して送信されます。
   - ※LLMがフェーズ1で明確に「低信頼度」と判断して早期リジェクトしたケースについては、想定内の動作であるためDiscord通知はスキップ（非通知でReview退避のみ）する仕様としています。これにより不要な通知ノイズを削減しています。
