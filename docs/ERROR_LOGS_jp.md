# S.S.T エラーログとデバッグ履歴

このファイルは、開発およびテスト中に発生した重要なエラー、その根本原因、および解決策を記録します。

## [2026-04-17] Prefect 3.x API 変更 - デプロイメントエラー
**フェーズ:** 10アルバム本番テスト（Core 実行）
**エラー:** `prefect.exceptions.PrefectImportError: 'prefect.deployments:Deployment' has been removed.`
**コンテキスト:** `run_production_test.py` の実行中、Core コンテナがメインフローを登録するために `prefect.deployments` から `Deployment` をインポートしようとしました。
**根本原因:** `uv` 経由でインストールされた `prefect` パッケージがバージョン 3.x（最新）でした。Prefect 3.x では、古い `Deployment.build_from_flow()` API は完全に削除され、`flow.deploy()` または `flow.serve()` が推奨されています。
**解決策:** 
- 不要になった `from prefect.deployments import Deployment` のインポートを削除。
- `core/src/core/main.py` の `deploy()` 関数を、`sst_main_flow.serve(name="sst-decentralized-deployment")` を使用するように更新。

## [2026-04-17] Worker Prefect タスクでの NameError
**フェーズ:** 10アルバム本番テスト（Worker 実行）
**エラー:** `NameError: name 'SteamMetadata' is not defined`
**コンテキスト:** `process_single_album_task` マップドタスクが、`WorkerInput` 用の `SteamMetadata` オブジェクトを初期化しようとした際にすべて失敗しました。
**根本原因:** Worker コードを Prefect に直接 `@task` として公開するリファクタリング中に、`.models` からのインポート文が切り詰められ、`SteamMetadata` クラスが漏れていました。
**解決策:** 
- `worker/src/worker/main.py` の `from .models import ...` 文に `SteamMetadata` を再追加。

## [2026-04-17] 10アルバム本番テスト成功
**フェーズ:** 全本番パイプラインテスト
**結果:** `Success: 9, Review: 0`（10アルバム制限中、1つはスキップ/キャッシュ）。
**メモ:** `PrefectImportError` と `SteamMetadata` の `NameError` を解決した後、パイプラインは大容量の新しいサウンドトラックを並列で正常に処理しました。Scout、Worker、Core コンポーネントの分離は、負荷がかかった状態でも完璧に機能しました。

## [2026-04-18] Prefect 3.x 移行 - .serve() 仕様
**エラー:** `TypeError: Flow.serve() got an unexpected keyword argument 'work_pool_name'`
**根本原因:** Prefect 3.x において、`.serve()` はフローを直接ホストし、`work_pool_name` 引数をサポートしていません。
**解決策:** `core/src/core/main.py` の `.serve()` 呼び出しから `work_pool_name` を削除。

## [2026-04-18] Starlette/FastAPI TemplateResponse 互換性
**エラー:** UI アクセス時の `TypeError: unhashable type: 'dict'`
**根本原因:** 新しいバージョンの Starlette では、`TemplateResponse` の第1引数に `request` オブジェクトを渡すか、キーワード引数として明示する必要があります。
**解決策:** `ui/src/ui/main.py` を更新し、キーワード引数を使用するように変更：`templates.TemplateResponse(request=request, name="index.html")`。

## [2026-04-18] Steam API 429 レート制限
**エラー:** 大量スキャン中の HTTP 429 Too Many Requests
**根本原因:** メタデータ取得のために Steam ストア API に対して短時間に連続したリクエストが発生。
**解決策:**
- `scout.scanner.SteamScanner` に指数関数的バックオフ（1分、3分、5分、10分）を実装。
- 重複する API コールを最小限にするため、ローカルキャッシュ（`scout_cache.json`）を追加。

## [2026-04-18] Prefect トリガーのシリアライズエラー
**エラー:** `Exception triggering Prefect flow: Object of type datetime is not JSON serializable`
**根本原因:** `scout_result` オブジェクトに `datetime` フィールドが含まれており、`requests.post` で使用される標準の `json` ライブラリで自動的にシリアライズできませんでした。
**解決策:** `scout/src/scout/main.py` を更新し、`datetime` などの複雑な型を JSON 互換の文字列に変換する `model_dump(mode='json')` を使用するように変更。
