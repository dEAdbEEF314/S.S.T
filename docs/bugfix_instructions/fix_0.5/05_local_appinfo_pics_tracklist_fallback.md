# 修正作業指示書 fix_0.5-05: ローカル appinfo.vdf PICS トラックリストフォールバック規約

## 1. 課題と目的

### 現状の課題
- Steam Web API の Store 詳細ページ（`appdetails`）にはトラックリスト構造（曲名、トラック番号、再生時間）が含まれない場合がある。
- 外部の PICS Bridge サーバー（HTTP）が未起動またはオフラインの環境では、Store API Tier 2 の PICS 問い合わせが失敗する。
- さらにストア詳細説明文（HTML prose）にもテキストトラックリストが記載されていない場合、トラックリストが空（`store_tracklist = []`）となり、`PRE_ALIGNMENT_REVIEW_GATE: Steam Tracklist Missing` として即時 Review 送りとなっていた（例: `870530`, `1270860`, `1611170`, `1796120`, `2392620`, `2966860` の 6件）。
- しかし実際には、Steam クライアントがローカルに保持している `appcache/appinfo.vdf` のバイナリデータ内に、Steam 公式の `albummetadata`（トラック番号、曲名、再生時間、アーティスト・作曲者等）が完全にキャッシュされている。
- `scanner.py` は起動時に `appinfo.vdf` を読み込んで `self.appinfo_dict` に保持しているにもかかわらず、`_get_local_metadata` では `albummetadata` を抽出しておらず、この最重要データが未活用のまま死蔵されていた。

### 目的
- ローカル `appinfo.vdf` からパースされた `self.appinfo_dict` 内の `albummetadata` を、Steam 正本 PICS トラックリストおよびクレジット情報の信頼できるフォールバック（およびローカル一次情報）として統合する。
- 外部 PICS Bridge の稼働状況に依存せず、ローカル Steam キャッシュから公式 PICS トラックリスト（`source = "STEAM_PICS"`）を確実に抽出し、正常なアライメントとアーカイブ化を可能にする。

---

## 2. 判定規約と仕様

### データ優先度とフォールバック規約
Steam 公式メタデータ（PICS トラックリスト）の取得フローを以下のように定義する：

1. **ローカル PICS の最優先抽出**:
   - `scanner.py` の `_get_local_metadata(app_id)` において、`self.appinfo_dict[app_id]` に `albummetadata` が存在する場合、`SteamWebClient.parse_pics_tracks(album_meta)` を実行してトラックリスト（`source = "STEAM_PICS"`）を抽出する。
   - 同時に `albummetadata.get("metadata", {})` からアーティスト、作曲者、レーベル（`store_credits`）を抽出する。
2. **Web API エンリッチメントとの連動**:
   - `SteamWebClient.fetch_web_enrichment` において、外部 Bridge API が空または接続失敗となった場合、引数またはコンテキストとして渡されたローカル `albummetadata` をフォールバックとして使用する。
   - 抽出されたトラックリストおよびクレジットは SQLite DB（`store_cache`）に `source = "STEAM_PICS"` として正しく永続化される。
3. **完全性の保証**:
   - 既存の `sanitize_corrupted_pics_tracks` パイプラインをそのまま通過させることで、PICS 特有のカンマ区切り汚染やディスク番号異常も自動的にサニタイズされる。

---

## 3. 実装方針

1. **`src/sst/steam_web_api.py`**:
   - `SteamWebClient.fetch_web_enrichment(app_id, force=False, local_album_meta=None)`:
     - Tier 2 の PICS Bridge API 失敗時、`local_album_meta` が与えられていればその `albummetadata` からトラックリストおよびクレジットを抽出する。
2. **`src/sst/scanner.py`**:
   - `_get_local_metadata(app_id, force=False)`:
     - `data.get("albummetadata")` から PICS トラックリストおよびクレジットを直接抽出し、`metadata["store_tracklist"]` および `metadata["store_credits"]` に格納する。
     - `fetch_web_enrichment` 呼び出し時にも `local_album_meta=data.get("albummetadata")` を渡し、Web 取得失敗時にもローカル PICS が確実にフォールバックするようにする。
3. **回帰テスト**:
   - `tests/test_operational_improvements.py` において、ローカル `albummetadata` からのトラックリスト抽出およびクレジット抽出が正しく行われることを検証する。

---

## 4. 影響範囲と安全性

- `docs/METADATA_SOURCE_SPEC.md` において、PICS は最高位の正本（構造決定権を持つ正本）として定められている。
- ローカル `appinfo.vdf` の `albummetadata` は Steam 公式クライアントが保持する PICS そのものであるため、外部 Bridge API から取得した PICS と完全に等価であり、仕様の整合性を 100% 遵守する。
- これにより、`PRE_ALIGNMENT_REVIEW_GATE: Steam Tracklist Missing` で停止していたアルバムが、本来の Steam 公式トラックリストに基づいて正常にアライメントされるようになる。

