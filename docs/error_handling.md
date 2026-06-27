# Error Handling Specification

## 1. 概要 (Overview)
S.S.T (Steam Soundtrack Tagger) は、何千ものサウンドトラックを連続して自律処理する「バッチ処理システム」として設計されています。そのため、一部のアルバムやAPIの障害によってプロセス全体が停止しないよう、**フェイルソフト（機能を縮退して稼働を継続する）** および **フェイルセーフ（安全側に倒す）** の原則に基づいたエラーハンドリングを実装しています。

## 2. バッチ継続性 (Batch Continuity)
メイン処理を司る `src/sst/processor.py` の `process_album` メソッドでは、最上位に包括的な `try-except Exception` ブロックが設けられています。

* **動作**: 特定の `app_id` の処理中に予期せぬ例外（ファイルの読み取り権限エラー、予期せぬJSONパースエラー、ディスク容量不足など）が発生した場合、その例外はキャッチされてエラーログ（`logger.error`）に記録されます。その後、システムはプロセスを停止することなく、次の `app_id` の処理へ移行します。
* **状態記録**: 例外により処理が完了しなかったアルバムはDBに「Review」または「Error」として記録され、安全な場所に隔離されます。

## 3. 外部API通信のエラー制御
MusicBrainzやAcoustID、Steam PICSといった外部APIへの通信は、ネットワーク障害やサーバーダウンのリスクが常に伴います。

* **タイムアウトとリトライ**: `src/sst/ident/acoustid.py` や `mbz.py` などの外部通信モジュールには明示的な `timeout`（例: 10秒）が設定されています。
* **Graceful Degradation (緩やかな縮退)**: APIがタイムアウトやHTTPエラー（503等）を返した場合、システムは例外を投げてクラッシュするのではなく、空のデータ（`None` や `{}`）を返します。
* **リカバリー**: FINGERPRINT（波形データ）の取得に失敗した場合でも、LLMは残されたSTEAM公式データとローカルファイルの情報のみを用いて推論を続行します（`STEAM-TRUST PATH` 等によるリカバリー）。

## 4. LLM推論のエラーとタイムアウト
LLM（ローカルまたはクラウド）の推論プロセスは、最も時間がかかり不安定になりやすいポイントです。

* **リトライ機構**: `src/sst/llm.py` における推論リクエストは、通信タイムアウト（デフォルト `600秒`）や、LLMが不正なJSONフォーマットを返却した場合に備え、最大3回のリトライが行われます。
* **推論失敗時のフォールバック**: リトライ上限に達しても有効な応答が得られなかった場合（Phase 2 タイムアウト等）、推論結果は `None` としてプロセッサに返却されます。
* **Reviewへの降格**: プロセッサは推論結果が `None` または空辞書であること検知すると、処理を中止し、該当のアルバムを未処理状態のまま `Review` ディレクトリへ送ります（Discord連携が有効な場合は通知はスキップされ、静かに隔離されます）。
* **切断検知 (`done_reason`)**: OLLAMA応答で `done_reason=length|max_tokens` を検知した場合、`response_truncated` として扱い、通常のJSONパース失敗とは分離して記録されます。
* **チャンク自動縮小リトライ**: 切断が検知されたチャンクは、その場でチャンクサイズを半分にして再試行されます。これにより、長文応答による欠落をランタイムで縮退回復します。

## 4.1 LLM可変設定（運用チューニング）

LLM切断再発時は `.env` で以下を調整し、再発率を比較します。

* `LLM_OLLAMA_NUM_CTX`
* `LLM_OLLAMA_NUM_PREDICT`
* `LLM_CHUNK_SIZE_VIRTUAL`
* `LLM_CHUNK_SIZE_METADATA_OLLAMA`
* `LLM_CHUNK_SIZE_METADATA_CLOUD`
* `LLM_CHUNK_ADAPTIVE`
* `LLM_CHUNK_OUTPUT_TOKENS_PER_TRACK`
* `LLM_CHUNK_OUTPUT_SAFETY_RATIO`

## 5. Validatorによる論理エラーの安全装置 (Fail-safe)
Pythonの例外（Exception）としてシステムが落ちるわけではありませんが、LLMが「論理的に破綻したメタデータ（例: Track番号の重複、タグのゴミ）」を生成してしまった場合のエラーハンドリングです。

* **動作**: `src/sst/validator.py` が最終チェックを行い、論理エラーを検知した場合は `issues` リストに内容を追記します。
* **降格処理**: `issues` が1つでも存在する場合、システムは「Archive」プロセスを即座に破棄し、「Review」へとステータスをダウングレードさせます。これにより、破壊されたタグ情報のままライブラリに書き込まれる事故（データ汚染）を物理的に防ぎます。

## 5.1 判定しきい値

* **通常パス**: `identity_confidence >= 100` かつ `integrity_quality >= 95`
* **STEAM-TRUST パス**: `identity_confidence >= 100` の場合、品質しきい値を `75` まで緩和

## 5.2 Review診断トレース

`process_album` は `diagnostics` を DB 保存メタデータに付与し、Review根因の追跡を可能にします。

* `diagnostics.trace`
* `diagnostics.review_cause_code`
* `diagnostics.upstream_cause_code`
* `diagnostics.packager_invoked`

分析は `Maintenance/analyze_processing_results.py` で集計し、原因分布や DB/出力整合を確認できます。

## 6. 通知レベルとの連動
* **WARNING**: Validatorによって論理エラーとしてReviewに降格した場合、Discord Webhookを通じて理由と共に警告が送信されます。
* **CRITICAL**: ディスク容量枯渇やデータベース書き込み障害など、システム全体の継続が困難な致命的例外が発生した場合に送信されるように設計されています。
