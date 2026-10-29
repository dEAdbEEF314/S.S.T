# 修正指示書 03: `normalize_title` の NFKC アキュートアクセント分裂修正・アンダースコア識別子の番号誤抽出防止・マルチディスク通し連番照合および PICS CSV 破損復元

## 1. 背景と問題の概要

全352件バッチ処理の監査において、[`src/sst/track_grouper.py`](file:///mnt/workspace/S.S.T/src/sst/track_grouper.py), [`src/sst/llm/prematch.py`](file:///mnt/workspace/S.S.T/src/sst/llm/prematch.py), および [`src/sst/steam_web_api.py`](file:///mnt/workspace/S.S.T/src/sst/steam_web_api.py) の文字正規化・トラック番号抽出・PICS トラックリスト解析の不備により、以下の **4件の Review アルバム** でスロット欠落や未割当ファイルが発生していることが確認された。

### 発生している現象（実データ例）
1. **【NFKC正規化による `´`（アキュートアクセント）の空白分裂】AppID `802640` (Deep Rock Galactic - Original Soundtrack Volume I + II)**:
   - 全75曲中74曲が確定し、Disc 1 Track 24（`1_24`）の1曲のみが未確定で Review 落ち。
   - Steam 公式タイトルは `"Karl's End"`（ASCII アポストロフィ `U+0027`）。
   - ローカルファイルは `24 - Karl´s End.wav` および `24 - Karl´s End.mp3`（埋め込みタイトルも `"Karl´s End"`、アキュートアクセント `U+00B4` をアポストロフィとして使用）。
   - `TrackManager.normalize_title`（`track_grouper.py:80-87`）において、80行目で先に `unicodedata.normalize("NFKC", stem)` を実行しているため、`U+00B4`（`´`）が **`U+0020`（半角スペース）＋ `U+0301`（結合アキュートアクセント）に分解**される！
   - その結果、86行目の `re.sub(r"['’‘`´]", "", stem)` には `´` が到達せず、87行目で `U+0301` もスペースに置換されて **`"karl s end"`**（3トークン）になり、Steam 側の **`"karls end"`**（2トークン）と一致しなくなった。
2. **【アンダースコア識別子 `radio1_8.mp3` からの誤ったトラック番号抽出】AppID `1851920` (Milk outside a bag of milk outside a bag of milk Soundtrack)**:
   - 全78曲中、Track 1〜66 はすべて番号なしファイル名（`100-99.mp3`, `another point of view.mp3` 等）であり、`fix_0.2` で導入された番号なしタイトル一意照合により66曲すべて deterministically prematch された。
   - しかし後半の12曲（Track 67〜78: `radio1_1.mp3`, `radio1_2.mp3`, ..., `radio1_8.mp3`, `radio2_14.mp3`, `radio3_2.mp3`）において、`TrackManager.build_file_records`（`track_grouper.py:257`）のフォールバック正規表現 `re.finditer(r'(?:^|[\s\-_])(\d{1,3})(?=[\s\-_.]|$)', clean_stem)` がアンダースコア `_` の直後の数値 `1`, `2`, ..., `8`, `14` を **ファイル名トラック番号 `filename_track`（`t_num_val`）として誤抽出**した！
   - その結果、`radio1_8.mp3`（本来は Slot 68 `"radio1_8"`）が「Track 8」として扱われ、Slot 8（`"bulk"`）とタイトル不一致でプレマッチ失敗し、番号なし厳密タイトル照合（`track_num is None` 条件）にも入れず、12曲すべてが未割当となった。
3. **【単一フォルダ通し連番WAV（`20..32`）とマルチディスクSteam定義（Disc 2 `1..13`）の不一致】AppID `1879310` (TCSTRIKERS4 soundtrack)**:
   - Steam スロットは Disc 1（`1_1`〜`1_19`）と Disc 2（`2_1`〜`2_13`）の全32曲。
   - ローカルの MP3 は `Disc 1/01..19.mp3` と `Disc 2/01..13.mp3` に分かれているが、ロスレスの WAV は単一フォルダ `WAV/` 内に **`01 Title.wav`〜`32 Extra Story.wav` の通し連番（`disc=1, track_num=1..32`）** で格納されている。
   - `20 Technology Crisis.wav`〜`32 Extra Story.wav`（`disc=1, track_num=20..32`）は、Steam の `2_1`〜`2_13`（グローバルインデックス `v_idx=19..31`、1始まり通し番号 `20..32`）と曲名・再生時間が完全一致しているにもかかわらず、`prematch.py:_find_matching_steam_slot` がトラック番号 `20..32` を持つスロットしか探さないためプレマッチに失敗した。
4. **【Steam PICS `originalname` 内の改行CSV混入による2曲結合破損】AppID `1299740` (FlatOut 4: Total Insanity Soundtrack)**:
   - Steam PICS の `tracks` 辞書において、インデックス `79`（Disc 4 Track 45）の `originalname` が `'Atterissage,,,0:00,\n4,46,"Brake'` という改行入りの壊れたCSV文字列になっているため、Disc 4 Track 45 のタイトルが壊れ、かつ **Disc 4 Track 46（`"Brake"`）が `store_tracklist` から欠落**している。
   - その結果、ローカルの `45_ATTERISSAGE.mp3` と `46_BRAKE.mp3` が両方とも未割当となった。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/track_grouper.py` (`TrackManager.normalize_title`: 78〜90行目)
```python
        stem = html.unescape(stem)
        stem = unicodedata.normalize("NFKC", stem).lower()
        if strip_track_prefix:
            # Strip composite track prefix like "01 - 02 - " or "1-02 " or "01. " or "12b. "
            stem = re.sub(r"^\d{1,3}\s*[-_.]\s*\d{1,3}[\s._-]+", "", stem)
            stem = re.sub(r"^\d{1,3}[a-z]?(?:[\s._-]+|$)", "", stem)
        # Remove apostrophes so "Coward's" and "Cowards" normalize identically
        stem = re.sub(r"['’‘`´]", "", stem)
```
- `unicodedata.normalize("NFKC", stem)` が `re.sub(r"['’‘`´]", "", stem)` より先に呼ばれているため、NFKC で空白＋結合文字（`\u0020\u0301` や `\u0020\u0300`）に分解される互換文字（`´` U+00B4 等）がアポストロフィ除去正規表現に引っかからない。

### 2.2 `src/sst/track_grouper.py` (`TrackManager.build_file_records`: 255〜275行目)
```python
            if not m_track:
                for m_cand in re.finditer(r'(?:^|[\s\-_])(\d{1,3})(?=[\s\-_.]|$)', clean_stem):
```
- 先頭にトラック番号がないファイルに対して曲名内部の数値を検索する際、区切り文字に `_` を無条件で含めているため、`radio1_8` や `bgm_01_2` のような識別子・枝番の末尾数値をトラック番号として誤抽出してしまう。

### 2.3 `src/sst/llm/prematch.py` (`_find_matching_steam_slot`: 198〜237行目)
- `disc_val == 1` で `int(target_slot_num)` が Disc 1 の最大トラック番号を超えている場合（通し連番 `20..32`）に、`v_idx == int(target_slot_num) - 1`（マルチディスクのグローバル1始まり通し番号）のスロットを照合する処理がない。

### 2.4 `src/sst/steam_web_api.py` (`parse_pics_tracks`: 66〜83行目)
- PICS の `originalname` に改行 `\n` と次トラックの CSV 行（`<disc>,<track>,"<title>`）が混入しているケースを分割・サニタイズしていない。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/track_grouper.py` (`TrackManager.normalize_title`: 78〜90行目) の修正
1. **NFKC 正規化の前後でのアポストロフィ・アクセント文字除去**:
   - `unicodedata.normalize("NFKC", stem)` を呼び出す **直前** に、`stem = re.sub(r"['’‘`´ʹʼˈˊˋ]", "", stem)` を実行する。
   - これにより `"Karl´s End"` は NFKC 前に `"Karls End"` となり、NFKC 後も確実に `"karls end"` に正規化され、`"Karl's End"` と完全一致する。

### 3.2 `src/sst/track_grouper.py` (`TrackManager.build_file_records`: 255〜275行目) の修正
1. **中間・末尾トラック番号フォールバック抽出におけるアンダースコア識別子保護**:
   - 先頭数値 `m_track` が存在しないファイルに対する中間数値検索（257行目）において：
     - 区切り文字としてアンダースコア `_` の直後の数値 `(\d{1,3})` をトラック番号候補として採用してよいのは、直前のトークンが `track`, `trk`, `ost`, `bgm`, `no`, `num`, `song` 等の汎用プレフィックスである場合に限定する（または、直前のトークンが英数字識別子 `r"[a-z]+\d+_"` [例: `radio1_`, `stage2_`, `ch1_`] である場合は枝番・曲名の一部とみなしてスキップする）。
     - これにより、`radio1_1.mp3`〜`radio3_2.mp3`（AppID `1851920`）は `filename_track = None` となり、後段の番号なし厳密タイトル一意照合によって12曲すべてが Steam スロット `"radio1_1"`〜`"radio3_2"` に100%決定論的にプレマッチされる。

### 3.3 `src/sst/llm/prematch.py` (`_find_matching_steam_slot`: 198〜237行目) の修正
1. **マルチディスクにおけるグローバル通し連番（`v_idx = int(target_slot_num) - 1`）照合の追加**:
   - `_find_matching_steam_slot` において、`(disc_val, target_slot_num)` および `steam_slots_by_num.get(target_slot_num)` で一致スロットが見つからず、かつ `disc_val == 1` で `target_slot_num.isdigit()` の場合：
     - `global_idx = int(target_slot_num) - 1` を計算し、`0 <= global_idx < len(full_ref_steam)` かつ `int(full_ref_steam[global_idx].get("d", 1) or 1) > 1`（Disc 2以降のスロット）である場合、その `global_slot = full_ref_steam[global_idx]` に対して `_titles_match(track, global_slot)` を検査する。
     - `_titles_match` が `True` であり、かつ再生時間が利用可能な場合は差が ±3.0秒以内であれば、`global_slot` を一致スロットとして返す。
   - これにより、AppID `1879310` の `WAV/20 Technology Crisis.wav`〜`32 Extra Story.wav` はすべて Disc 2 の Slot `2_1`〜`2_13` に決定論的にプレマッチされ、既存の `Disc 2/01..13.mp3` と同一スロットで統合されてロスレス WAV が100%採用される。

### 3.4 `src/sst/steam_web_api.py` (`parse_pics_tracks`: 66〜83行目) の修正
1. **PICS `originalname` 内の改行CSV混入の検出と分割復元**:
   - `parse_pics_tracks` において、`raw_title = str(t_info.get("originalname") or t_info.get("name") or "").strip()` に改行 `\n` または `,,,\d+:\d+,` が含まれている場合：
     - 正規表現 `r"^([^,\r\n]+?),*,\d+:\d+,\s*[\r\n]+\s*(\d+),(\d+),\"?([^\"\r\n]+)\"?$"` でマッチするか検査する。
     - マッチした場合、現在のトラックの `title` を第1グループ（例: `"Atterissage"`）に修正した上で、第2・第3・第4グループ（例: `disc=4, number="46", title="Brake"`）を後続の独立したトラックエントリとして `tracklist` に追加する（既存のトラックリストに同じ `(disc, number)` がまだ存在しない場合）。
   - ※DBキャッシュ（`data/sst_local_state.db` の `soundtracks.store_tracklist`）に既に破損した文字列が保存されているアルバムに対しても、`processor.py` / `album_context.py` で `steam_meta.store_tracklist` をロードする際に同様のサニタイズヘルパーを通すことで、再フェッチなしでも即座に復元されるようにする。

---

## 4. 不変条件・禁止事項

- `Artist - Album - 01 Title.ext` や `murasaki_ost01.wav` のような正当なトラック番号抽出（既存テストでカバーされているパターン）を壊してはならない。
- グローバル通し連番照合（`global_idx = int(target_slot_num) - 1`）は、タイトル一致（`_titles_match`）が確認できる場合にのみ適用し、タイトル不一致のまま通し番号だけで別ディスクへ割り当ててはならない。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下の合成回帰テストを追加すること。

1. **`test_normalize_title_strips_acute_accent_apostrophe_before_nfkc`**:
   - **検証**: `TrackManager.normalize_title("24 - Karl´s End")` と `TrackManager.normalize_title("Karl's End", strip_track_prefix=False)` がともに **`"karls end"`** となり完全一致すること（AppID `802640` 型）。
2. **`test_build_file_records_does_not_extract_track_number_from_alphanumeric_underscore_title`**:
   - **設定**: `radio1_1.mp3`, `radio1_8.mp3`, `radio2_14.mp3`（埋め込み `track_number` タグなし）を含むファイルリスト（AppID `1851920` 型）。
   - **検証**: `build_file_records` が `filename_track` を `None` とし、`extract_deterministic_prematches` で Steam スロット `"radio1_1"`, `"radio1_8"`, `"radio2_14"` に100%決定論的にプレマッチされること。
3. **`test_prematch_matches_continuous_single_folder_numbering_against_multidisc_steam_slots`**:
   - **設定**: Steam が Disc 1 (`1_1..1_19`) + Disc 2 (`2_1 Technology Crisis`..`2_13 Extra Story`) で、ローカル WAV が `disc=1, track_num=20, title="20 Technology Crisis"` の場合（AppID `1879310` 型）。
   - **検証**: `extract_deterministic_prematches` が `20 Technology Crisis.wav` を `v_idx=19`（Slot `2_1`）に決定論的にプレマッチすること。
4. **`test_parse_pics_tracks_splits_corrupted_csv_newline_originalname`**:
   - **設定**: PICS `tracks` に `'79': {'discnumber': '4', 'tracknumber': '45', 'originalname': 'Atterissage,,,0:00,\n4,46,"Brake', 'm': '2', 's': '49'}` が含まれる場合（AppID `1299740` 型）。
   - **検証**: Disc 4 Track 45（`title="Atterissage"`）と Disc 4 Track 46（`title="Brake"`）の2トラックに正しく分割・復元されること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_id3_tag_construction.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

