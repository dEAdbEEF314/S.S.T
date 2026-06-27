# S.S.T (Steam Soundtrack Tagger) 内部実装・判定ロジック仕様書

本書は、実際の Python ソースコードおよび設定ファイル (`.env.example`) から抽出された「実装の真実」を詳細に記述するものである。S.S.T がどのようにしてメタデータを収集・評価し、最終的な判定を下すのか、開発者が各モジュールの挙動を完全に理解するための究極のリファレンスとなることを目的とする。

---

## 1. 構成管理と環境変数 (`config.py`, `.env`)

システムの挙動は `src/sst/config.py` 内の `Config` クラス（Pydantic Settings）によって制御される。

### 1.1 パス解決ロジック
- **`STEAM_INSTALL_PATH`**: Windows形式 (`C:\...`) または WSL形式 (`/mnt/...`) を許容。内部で `utils.ensure_wsl_path` を通じて WSL ネイティブパスに正規化される。
- **`SST_WORKING_DIR`**: デフォルト `/tmp/sst-work`。音声変換や一時バッファに使用される。
- **`SST_OUTPUT_DIR`**: 最終成果物（ZIPアーカイブ）の出力先。Windows側ディスクI/O負荷を避けるため、ローカルWSLパス（例: `./output`）の指定を推奨。内部に `archive/` および `review/` フォルダが自動生成され、その中に ZIPファイル が出力される。

### 1.2 メタデータ優先順位 (分離の三権分立)
LLM（司法）への「憲法」として、以下の変数がプロンプトに注入される。
- **`METADATA_SOURCE_PRIORITY`**: アルバム全体の同定に使用（デフォルト: `MBZ,PICS_API,STEAM_STORE,STEAM_TAGS,EMBEDDED`）。
- **個別タグ優先順位 (`PRIORITY_*`)**:
  - `TIT2` (曲名): `MBZ,PICS_API,FILE,EMBED,VDF`
  - `TPE1` (アーティスト): `MBZ,PICS_API,EMBED`
    - `TRCK` (トラック番号): `PICS_API,MBZ,FILE,EMBED`
  - `TPOS` (ディスク番号): `PICS_API,EMBED,MBZ`
  - `TYER` (発売年): `MBZ,EMBED,WEB_API`

### 1.3 LLM可変設定（OLLAMA / Chunk制御）
`src/sst/config.py` と `.env` により、LLM出力長とチャンク戦略を動的制御する。

- **`LLM_OLLAMA_NUM_CTX`**: OLLAMAコンテキスト上限（デフォルト: `32768`）
- **`LLM_OLLAMA_NUM_PREDICT`**: OLLAMA出力トークン上限（デフォルト: `4096`）
- **`LLM_CHUNK_SIZE_VIRTUAL`**: 仮想アルバム統合の基本チャンクサイズ（デフォルト: `20`）
- **`LLM_CHUNK_SIZE_METADATA_OLLAMA`**: OLLAMA時のメタデータ統合チャンクサイズ（デフォルト: `10`）
- **`LLM_CHUNK_SIZE_METADATA_CLOUD`**: クラウド系バックエンド時のチャンクサイズ（デフォルト: `30`）
- **`LLM_CHUNK_ADAPTIVE`**: 出力予算に応じたチャンク自動縮小を有効化（デフォルト: `true`）
- **`LLM_CHUNK_OUTPUT_TOKENS_PER_TRACK`**: 1トラック当たりの出力見積（デフォルト: `180`）
- **`LLM_CHUNK_OUTPUT_SAFETY_RATIO`**: `num_predict` に対する安全率（デフォルト: `0.75`）

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
    テキスト情報による同定が困難な場合、アルバム内の曲をサンプリング（または全曲スキャン）し、`fpcalc` を用いて AcoustID API から MusicBrainz Recording ID を直接特定します。
    - **サンプリングモード（デフォルト）**: 全曲の約50%（3〜10曲）を抽出し、40%以上の合意で同定。
    - **全曲スキャンモード (`--fingerprint-all`)**: 全トラックを対象とし、数学的確定を目指す。詳細は 3.3項参照。
7.  **論理IDの決定**:
    - グループ内のファイル間で、ファイル名から抽出されたトラック番号 (`^(\d+)`) が**2つ以上**存在する場合、`{norm_stem} {track_num}` というキーを生成してトラックを分離。
    - それ以外は `{disc}_{norm_stem}` をキーとして統合。

### 3.2 複数フォーマットの混在
同一アルバム内に AIFF と MP3 等が混在する場合、以下の優先順位で 1 つのファイルのみを採用（Adopt）します。
1. **Lossless**: FLAC, WAV, AIFF, ALAC
2. **Lossy**: OGG, AAC, M4A, MP3

### 3.3 全曲AcoustID照合モード（数学的確定アルゴリズム）
`--fingerprint-all` 引数により発動する、時間を度外視した高精度同定モード。
- **スキャン範囲**: アルバム内の全論理トラック。
- **API負荷制御**: 各リクエスト間に 1.5〜2.0秒の `time.sleep` を強制挿入。
- **同定アルゴリズム (Intersection Logic)**:
    1.  全トラックの `Release MBID` リストを取得。
    2.  それらすべてのリストに含まれる「共通の Release ID（積集合）」を計算。
    3.  結果、IDが1つに絞り込まれた場合、それは「現在手元にある音源構成を完全に包含する特定の版」として Identity Confidence 100% の確定ソースとみなされる。
- **ユースケース**: 「Duplicates（重複候補）」が多すぎて自動処理できない大規模アルバムや、MusicBrainz上の特定の版と物理的に完全に一致させたい場合に使用。

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
    - **MBZ 直接リンク**: MBZの直接リンクがあり、かつ曲数が全ソースで一致する場合。
    - **Steam 信頼パス (STEAM-TRUST)**: 物理同定（指紋）が利用不可な場合でも、Steam ストアのトラックリストが全曲完備されており、LOCAL の曲数・順序・再生時間（±3秒以内）と 100% 構造的に一致する場合。
- **Phase 2 (Sequential Mapping)**:
    - **STABLE_ID (`idx_N`)**: LLMによるキーの「勝手な修正」を防ぐため、論理IDではなく不変のインデックスを使用。
    - **マッピング指示**: 
      - `override_track`: トラック番号が不明な場合、ストアリストから補完。すべてが同じ番号などの異常メタデータ時は `null` にフォールバック。
      - `override_disc`: ディスク番号が不明な場合に補完。
      - `override_title`: トラック番号が混入している場合、除去した「純粋な曲名」を生成。

    ### 4.3 LLM切断検知とチャンク自動縮小
    - OLLAMA応答の `done_reason` を取得し、`length` / `max_tokens` の場合は `response_truncated` として扱う。
    - 切断が検知されたチャンクは、その場でチャンクサイズを半減して再試行する。
    - これにより「長すぎるJSON応答」による欠落を、同一ラン内で縮退回復できる。

---

## 5. バリデーションと検閲層 (`validator.py`)

### 5.1 物理検閲ゲート (`validate`)
LLM の確信度に関わらず、以下の物理的チェックに抵触した場合は強制的に `REVIEW` へ送られます。
1.  **Dirty/Conflicting Tags**: `^(\d+)([\s.-]+)` にマッチし、かつ小数点ではない、かつ実際のトラック番号と一致する、または `0` パディング/強いセパレータを伴う場合（MBZ公式タイトルがその形式である場合を除く）。
2.  **物理的欠損 (Track #0)**: 補完を試みてもトラック番号が `0` または "Unknown" のまま残った場合。
3.  **重複トラック**: 同一ディスク番号内に同一のトラック番号が複数存在する場合（Duplicate Disc/Track pairs）。
    - **スマート救済ロジック (Smart Rescue Logic)**: 重複が検知された場合、システムは以下の優先順位で自動修復を試みます。
        - **Heuristic 1: マルチディスク整列**: ディスク番号が異なるのにインデックスが重複している場合、ローカルのディスク番号を正として、Steamリスト内の正しいディスク範囲から候補を再配分。
        - **Heuristic 2: 名前ベースの再検索**: LLMが誤ったインデックスを割り当てた場合でも、ファイル名とSteamリスト内の全トラック名を Fuzzy/Prefix マッチングで照合し、正しいインデックスを特定。
        - **Heuristic 3: 連続同名曲の順次配分**: Steamリストに同名（または類似名）の曲が連続している場合、ローカルファイルの並び順に従って未使用のインデックスへ順次割り当て。
4.  **重複タイトル検知 (Duplicate Title Detection)**: アルバム内で同一の曲名が 50% 以上のトラックで使用されている場合。LLMの誤認やマッピングミス（全曲に1曲目のタイトルが付与される等）を物理的に遮断するための安全装置。
5.  **信頼度閾値**:
  - **通常パス**: Identity Confidence >= 100, Integrity Quality >= 95
  - **STEAM-TRUST パス**: 物理同定（指紋）が欠落しているが Steam と構造一致する場合、品質閾値を **75%** へ動的に緩和し、物理データの欠落による減点を許容する。
    - **LLM矛盾救済**: LLM が `archive_vs_review_ratio` で誤って Review を指定していても、確信度と品質が上記閾値を満たしていればシステム側で Archive を強行する。
5.  **音声警告**: FFmpeg による「invalid rice order」や「Decoding error」等の警告やエラー。

---

## 6. タグ書き込みと変換層 (`tagger.py`, `builder.py`)

### 6.1 ID3v2.3 仕様の強制
- **FFmpeg 変換**: MP3 (`-b:a 320k`), AIFF (`-write_id3v2 1`)。多言語（日本語・韓国語等）を含むパス名がFFmpegの標準エラー出力に現れた際、Pythonが文字列デコードエラー（UnicodeDecodeError）で異常終了するのを防ぐため、コマンド出力は常にバイナリでキャプチャし、安全に `errors='ignore'` でデコードします。
- **Mutagen 書き込み**: `TDRC` (v2.4) を削除し、`TYER` (v2.3) を追加。`APIC` は Type `3` (Front Cover) 固定。
  - **エンコーディング仕様**: ID3v2.3 は UTF-8 をサポートしていないため、非アスキー文字を含むテキストフレームの書き込みには必ず **UTF-16 with BOM (encoding=1)** を使用します。
- **`COMM` コメント欄の動的調整**: 
  - `tags.delall("COMM")` で初期化後、親ゲーム情報を ` | ` で連結。
  - ID3v2.3の推奨制限に準拠するため、UTF-16で 2000文字を超える場合は、情報の断片化を最小限に抑えつつ、末尾のタグ要素から `pop()` して調整する。

### 6.2 タグ決定プロセスとメタデータマージ仕様
- **再生時間に基づく自動整列 (Duration-based Alignment)**:
  AcoustID波形照合で特定された MusicBrainz (MBZ) のリリース情報について、元のリリース曲順がローカルファイル（＝Steamの公式曲順）と異なる場合、システムは事前に「ローカルファイルの再生時間」と「MBZ側の全トラックの再生時間」を照合し、最も近いもの（差が3秒以内）を紐付けます。これにより、LLMには整列済みの綺麗な構造のデータがインプットされます。
- **ブレンド優先度とフォールバック**:
  タグの各項目は、`.env` で設定された個別の優先度（例: `PRIORITY_TIT2=MBZ,PICS_API...`）に従って最適なソースから採用されます。LLMが `use_fingerprint` などの指示を出した場合でも、該当ソースのトラックデータが存在しない場合は、次の優先度ソース（`PICS_API` など）へ自動フォールバックされます。
- **監査レポートでの透明性確保**:
  各トラックの曲名に実際にどのソースが適用されたかを示す「Title Source」および、上記の整列・ブレンド仕様を可視化した「System Merge Note」を `AUDIT_REPORT.html` に出力することで、人間の監査プロセスでの混乱を防ぎます。

---

## 7. システム実行制御 (`runner.py`, `main.py`)

### 7.1 並列処理の動的制御 (Tier-based Concurrency)
- **ティア分けと同時処理数**: 
  - SMALL (<= 50曲): `MAX_PARALLEL_SMALL` (デフォルト 4並列)
  - MEDIUM (51-100曲): `MAX_PARALLEL_MEDIUM` (デフォルト 2並列)
  - LARGE (> 100曲): `MAX_PARALLEL_LARGE` (デフォルト 1並列固定)
- **並列処理制限**: `MAX_PARALLEL_ALBUMS` (アルバム単位の全体上限), `MAX_ENCODING_TASKS` (FFmpeg等の音声処理の同時実行数)。

### 7.2 セーフティ・メカニズム
- **シングルトン・ロック**: `data/sst.lock` による多重実行防止。
- **ネイティブ・バッファリング**: 一時処理は `/tmp/sst-work/buffer_{AppID}_{RunID}` で行い、完了後に物理削除。

---

## 8. Review診断トレースと再分析

`src/sst/processor.py` は、Review化の根因を追跡するため `diagnostics` を `metadata.json` / DBに保存する。

- **`diagnostics.trace`**: 実行ステージ時系列（`PROCESS_START`, `LLM_CONSOLIDATED`, `VALIDATION_DONE`, `PACKAGE_SAVE_*` など）
- **`diagnostics.review_cause_code`**: Review判定の直接原因（例: `EARLY_REVIEW_RETURN`）
- **`diagnostics.upstream_cause_code`**: 上流原因（例: `LLM_RESPONSE_MISSING`, `LOW_CONFIDENCE_GATE`）
- **`diagnostics.packager_invoked`**: パッケージ処理に到達したかのフラグ

分析は `Maintenance/analyze_processing_results.py` で行い、以下を集計可能。

- `review_cause_code` / `upstream_cause_code` 分布
- `message` 欠落行の原因別内訳
- DB上の `review` 件数と `output/review` 実体差分
