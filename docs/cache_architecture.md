# Cache Architecture & Two-Phase Pipeline Specification

## 1. 概要 (Overview)
現在のS.S.Tは、アルバムの処理フロー（波形計算 → AcoustID通信 → MBZ通信 → LLM推論）をワーカーごとに直列で実行しています。この方式では、ネットワークI/Oや `fpcalc` 実行待ちの間に、高価なLLMサーバーのリソースが遊んでしまうというボトルネックが存在しました。
これを解消するため、外部データの取得を「事前フェッチ（Phase 1）」として完全に分離し、収集したデータをSQLiteキャッシュに保存してから、LLM推論（Phase 2）へ一気に流し込む「Two-Phase Pipeline」アーキテクチャを導入します。

## 2. キャッシュ層の仕様 (Persistent Cache Specification)
SQLite (`sst_local_state.db`) にキャッシュ用テーブルを追加し、外部API応答を永続化します。これにより、我々および相手先サーバー双方の負担を軽減します。

### 2.1 AcoustID キャッシュ
- **テーブル名**: `acoustid_cache`
- **キー**: `fingerprint_hash` (fpcalc の出力ハッシュ) またはファイルパス＋更新日時をキーとする等
- **バリュー**: AcoustID API の JSON レスポンス
- **有効期限 (TTL)**: 30日。期限内であればAPIを叩かずキャッシュを即座に返却。

### 2.2 MusicBrainz キャッシュ
- **テーブル名**: `mbz_cache`
- **キー**: `query_hash` (リクエストURLまたはパラメータのハッシュ)
- **バリュー**: MBZ API の JSON レスポンス
- **有効期限 (TTL)**: 30日。

### 2.3 Steam PICS キャッシュ
- 現在はJSONベース（`sst_cache.json`）で機能していますが、将来的にSQLiteへ統合することを視野に入れます。

## 3. Two-Phase Pipeline アーキテクチャ
処理を以下の2つのフェーズに分割します。

### Phase 1: Data Gathering & Pre-Fetch (非同期・多重化)
LLMの `JobRunner` 起動前に、対象となるすべてのアルバムに対して、ネットワークI/OとCPU（fpcalc）に特化した多重ワーカーでデータを収集・キャッシュします。
- 全オーディオファイルの `fpcalc` （波形指紋）生成。
- キャッシュ未ヒット時の AcoustID API / MusicBrainz API への問い合わせ。
- 各APIのレートリミットを遵守しつつ、並列化による高速化を図ります。

### Phase 2: LLM Processing (推論フル稼働)
すべての外部データがローカルキャッシュに揃った状態で、既存の `JobRunner` を起動します。
- `processor.py` および `virtual_album_builder` はAPI通信待ちを一切行わず、DBキャッシュから即座にデータを読み出します。
- LLMはI/Oにブロックされることなく、限界速度で推論のみに専念できます。

---

## 4. 実装計画 (Implementation Plan) - 引継ぎ用タスクリスト

段階的に実装とテストを行います。他のエージェントに引き継ぐ場合は、以下のチェックリストを参考に進捗を確認してください。

- [ ] **Step 1: DBキャッシュ層の追加**
  - `src/sst/db.py` に `acoustid_cache` と `mbz_cache` テーブル（`query_key`, `response_data`, `fetched_at` カラムを持つ）を追加。
  - `DatabaseManager` に `get_api_cache(service, key, ttl_days)` と `set_api_cache(service, key, data)` メソッドを追加。

- [ ] **Step 2: APIクライアントのキャッシュ対応**
  - `src/sst/ident/acoustid.py` を改修し、通信前に `get_api_cache` を確認、通信後に `set_api_cache` を呼び出す。
  - `src/sst/ident/mbz.py` も同様にキャッシュ対応させる。

- [ ] **Step 3: Pre-Fetch ランナーの実装**
  - 新規ファイル `src/sst/prefetcher.py` を作成。
  - 処理対象のサウンドトラックを受け取り、全オーディオファイルの指紋生成とメタデータ検索をマルチスレッド（または asyncio）で一気に実行する `DataGatherer` クラスを実装。

- [ ] **Step 4: メイン処理フローへの組み込み**
  - `src/sst/main.py` を改修し、`JobRunner` にデータを渡す前に `DataGatherer.run()` を呼び出して事前キャッシュを完了させるフローを確立。
  - 全体を通した動作確認とパフォーマンス測定を実施。
