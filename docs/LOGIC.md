# S.S.T (Steam Soundtrack Tagger) 内部実装・判定ロジック仕様書

本書は、実際の Python ソースコードおよび設定ファイル (`.env.example`) から抽出された「実装の真実」を詳細に記述するものである。S.S.T がどのようにしてメタデータを収集・評価し、最終的な判定を下すのか、開発者が各モジュールの挙動を完全に理解するための究極のリファレンスとなることを目的とする。

---

## 1. 構成管理と環境変数 (`config.py`, `.env`)

システムの挙動は `src/scout/config.py` 内の `Config` クラス（Pydantic Settings）によって制御される。

### 1.1 パス解決ロジック
- **`STEAM_INSTALL_PATH`**: Windows形式 (`C:\...`) または WSL形式 (`/mnt/...`) を許容。内部で `utils.ensure_wsl_path` を通じて WSL ネイティブパスに正規化される。
- **`SST_WORKING_DIR`**: デフォルト `/tmp/sst-work`。音声変換や一時バッファに使用される。
- **`SST_OUTPUT_DIR`**: 最終成果物の出力先。内部に `archive/` および `review/` フォルダが自動生成される。

### 1.2 メタデータ優先順位 (分離の三権分立)
LLM（司法）への「憲法」として、以下の変数がプロンプトに注入される。
- **`METADATA_SOURCE_PRIORITY`**: アルバム全体の同定に使用（デフォルト: `VGMDB,MBZ,DISCOGS,STEAM_PICS,STEAM_STORE,STEAM_TAGS,EMBEDDED`）。
- **個別タグ優先順位 (`PRIORITY_*`)**:
    - `TIT2` (曲名): `FILE,EMBED,VDF,VGMDB,MBZ,DISCOGS,PICS_API`
    - `TPE1` (アーティスト): `EMBED,VGMDB,MBZ,DISCOGS,PICS_API`
    - `TRCK` (トラック番号): `VGMDB,PICS_API,MBZ,DISCOGS,FILE,EMBED`
    - `TPOS` (ディスク番号): `VGMDB,PICS_API,EMBED,MBZ,DISCOGS`
    - `TYER` (発売年): `EMBED,VGMDB,MBZ,DISCOGS,WEB_API`

---

## 2. ライブラリ走査と情報取得層 (`scanner.py`, `steam_vdf.py`)

### 2.1 ライブラリ発見ロジック
- **`SteamLibraryDiscovery.discover`**: `libraryfolders.vdf` をパースし、全ドライブの `path` を抽出。
- **ACF走査**: 各ライブラリの `steamapps/appmanifest_{AppID}.acf` を取得し、`AppState` セクションから `name` および `installdir` を特定。
- **パーソナライズ (`STEAM_LOGIN_SECURE`)**: クッキーが設定されている場合、`https://store.steampowered.com/dynamicstore/userdata/` から所有権情報を含む `userdata.json` を取得・更新する。

### 2.2 3層 API 取得アルゴリズム (`_fetch_web_enrichment`)
1.  **Tier 1 (Official Store API)**: `https://store.steampowered.com/api/appdetails?appids={app_id}&l={language}`
2.  **Tier 2 (PICS Bridge via Docker)**: `http://localhost:8080/v1/info/{app_id}`
    - 失敗時は指数バックオフ（2s, 4s, 8s）を伴う最大3回のリトライ。
3.  **Tier 3 (Official Tags via Steam Web API)**: `IStoreBrowseService` 経由で 20件のタグを取得。

### 2.3 VGMdb CDDB 連携ロジック (`vgmdb.py`)
MusicBrainz での同定後、以下の優先順位で DiscID を算出し、VGMdb に問い合わせを行う。
1.  **物理 DiscID**: MBZ に記録されている実際のセクタオフセット情報を使用。
2.  **理論的 DiscID (MBZベース)**: MBZ の各トラック再生時間から擬似的な TOC を構成。
3.  **理論的 DiscID (Localベース)**: ローカルファイルの再生時間から擬似的な TOC を構成（MBZに時間情報がない場合の最終手段）。
- **取得データ**: 日本語（UTF-8）、英語、ローマ字のタイトルをそれぞれのエンドポイント（`/ja.utf8`, `/en`, `/ja-Latn`）から取得。

---

## 3. 音声解析と論理トラック統合層 (`track_grouper.py`)

### 3.1 論理トラック統合アルゴリズム (`group_by_logical_track`)
複数フォーマットを同一トラックとして統合するための正規化・照合プロセス：
1.  **Stem 抽出**: ファイル名から拡張子を除去。
2.  **冗長番号除去**: `^(\d+[\s._-]+)+` で行頭の連番を削除。
3.  **接尾辞除去**: `[\s(\[]+(aiff|mp3|flac|wav|lossless|high-res|ost|soundtrack|official)[\s)\]]+$` (IGNORECASE) を削除。
4.  **文字列正規化**: `[^a-zA-Z0-9]` をスペース置換、小文字化、誤字補正 (`artifical` -> `artificial`)、数値正規化 (`01` -> `1`)。
5.  **ハイブリッド照合 (Hybrid Matching)**:
    単なる文字列の一致だけでなく、以下の条件を組み合わせて同一トラックか判定します：
    - **ディスク番号の一致** ＋ 以下のいずれか：
        - **正規化名の完全一致**
        - **推測トラック番号の一致 ＆ 再生時間の差が 1.0秒以内**
        - **文字列類似度（difflib）が 0.85以上 ＆ 再生時間の差が 1.0秒以内**
6.  **音声指紋（AcoustID）による補完**:
    テキスト情報による同定が困難な場合、アルバム内の先頭数曲をサンプリングし、`fpcalc` を用いて AcoustID API から MusicBrainz Recording ID を直接特定します。取得された ID は MusicBrainz 検索時の強力なヒントとして機能します。
7.  **論理IDの決定**:
    - グループ内のファイル間で、ファイル名から抽出されたトラック番号 (`^(\d+)`) が**2つ以上**存在する場合、`{norm_stem} {track_num}` というキーを生成してトラックを分離。
    - それ以外は `{disc}_{norm_stem}` をキーとして統合。

### 3.2 複数フォーマットの混在
同一アルバム内に AIFF と MP3 等が混在する場合、以下の優先順位で 1 つのファイルのみを採用（Adopt）します。
1. **Lossless**: FLAC, WAV, AIFF, ALAC
2. **Lossy**: OGG, AAC, M4A, MP3

---

## 4. メタデータ同定と LLM 連携層 (`llm.py`, `ident/mbz.py`)

### 4.1 MusicBrainz スコアリング (`mbz.py`) (NWO Hybrid Scoring)
- **概要**: 候補の妥当性を物理的証拠に基づき数値化する。各配点は `.env` の `SCORE_MBZ_*` 変数で調整可能。
- **加点項目 (デフォルト)**: 
    - `DIRECT_STEAM_LINK` (+500), `PARENT_STEAM_LINK` (+300)
    - `DIRECT_STEAMDB_LINK` (+500), `PARENT_STEAMDB_LINK` (+300)
    - `ACOUSTID_MATCH` (+400): 音声指紋から得られた Recording ID が含まれている場合。
    - `SET_SIMILARITY` (+200): アルバム全体の「曲名＋再生時間」のパターン一致度に基づく加点。
    - `FINGERPRINT_MATCH` (+200): トラック名の 80% 以上が一致する場合。
    - `BANDCAMP_LINK` (+100)
- **減点項目 (デフォルト)**: `TRACK_COUNT_DIFF` (1曲につき -20, 最大 -300), `DATE_MISMATCH` (1年につき -20, 最大 -100)。


### 4.2 LLM による意味論的監査 (2フェーズ処理フロー)
- **Phase 1 (Global Identity)**: アルバム全体の `identity_confidence` (閾値100) と `integrity_quality` (閾値95) を決定。
  - **決定論的ファストトラック**: 以下の条件を満たす場合、LLM をバイパスして `ARCHIVE` 判定を下す。
    - **VGMdb 照合成功**: AcoustID/MBZ で特定された DiscID が VGMdb CDDB と一致し、多言語タイトルが取得できた場合。
    - **MBZ 直接リンク**: MBZの直接リンクがあり、かつ曲数が全ソースで一致する場合。
- **Phase 2 (Sequential Mapping)**:
    - **STABLE_ID (`idx_N`)**: LLMによるキーの「勝手な修正」を防ぐため、論理IDではなく不変のインデックスを使用。
    - **マッピング指示**: 
      - `override_track`: トラック番号が不明な場合、ストアリストから補完。すべてが同じ番号などの異常メタデータ時は `null` にフォールバック。
      - `override_disc`: ディスク番号が不明な場合に補完。
      - `override_title`: トラック番号が混入している場合、除去した「純粋な曲名」を生成。

---

## 5. バリデーションと検閲層 (`validator.py`)

### 5.1 物理検閲ゲート (`validate`)
LLM の確信度に関わらず、以下の物理的チェックに抵触した場合は強制的に `REVIEW` へ送られます。
1.  **Dirty/Conflicting Tags**: `^(\d+)([\s.-]+)` にマッチし、かつ小数点ではない、かつ実際のトラック番号と一致する、または `0` パディング/強いセパレータを伴う場合（MBZ公式タイトルがその形式である場合を除く）。
2.  **物理的欠損 (Track #0)**: 補完を試みてもトラック番号が `0` または "Unknown" のまま残った場合。
3.  **重複トラック**: 同一ディスク番号内に同一のトラック番号が複数存在する場合（Duplicate Disc/Track pairs）。
4.  **信頼度閾値**:
    - Identity Confidence < 100
    - Integrity Quality < 95
5.  **音声警告**: FFmpeg による「invalid rice order」や「Decoding error」等の警告やエラー。

---

## 6. タグ書き込みと変換層 (`tagger.py`, `builder.py`)

### 6.1 ID3v2.3 仕様の強制
- **FFmpeg 変換**: MP3 (`qscale:a 2`), AIFF (`-write_id3v2 1`)。
- **Mutagen 書き込み**: `TDRC` (v2.4) を削除し、`TYER` (v2.3) を追加。`APIC` は Type `3` (Front Cover) 固定。
- **`COMM` コメント欄の動的調整**: 
  - `tags.delall("COMM")` で初期化後、親ゲーム情報を ` | ` で連結。
  - ID3v2.3の推奨制限に準拠するため、UTF-16で 2000文字を超える場合は、情報の断片化を最小限に抑えつつ、末尾のタグ要素から `pop()` して調整する。

---

## 7. システム実行制御 (`runner.py`, `main.py`)

### 7.1 Adaptive Routing
- **ティア分け**: SMALL (<= 50, 並列実行), MEDIUM/LARGE (> 50, **並列数 1** 固定)。
- **並列処理制限**: `MAX_PARALLEL_ALBUMS` (アルバム単位), `MAX_ENCODING_TASKS` (音声処理単位)。

### 7.2 セーフティ・メカニズム
- **シングルトン・ロック**: `data/sst.lock` による多重実行防止。
- **ネイティブ・バッファリング**: 一時処理は `/tmp/sst-work/buffer_{AppID}_{RunID}` で行い、完了後に物理削除。
