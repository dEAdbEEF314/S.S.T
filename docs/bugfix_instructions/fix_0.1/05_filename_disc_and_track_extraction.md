# 修正指示書 05: ファイル名からのディスク番号・トラック番号抽出正規表現の誤爆修正

## 1. 背景と問題の概要

`TrackManager.build_file_records`（`src/sst/track_grouper.py`）におけるファイル名解析ロジックに2つの正規表現バグがあり、**Archive行き5件のアルバムで全トラックの `TPOS`（総ディスク数）タグが `1/53` や `1/25` に破損**しているほか、**Review行き2件（`2339210`, `3162910`）の直接原因**となっている。

### 発生している現象（実データ例）
1. **複合ディスク番号パターン `^(\d+)[-_](\d+)` の誤爆による `TPOS`（総ディスク数）破損**:
   1枚組（全1ディスク）のアルバムにおいて、「トラック番号 + `_` または `-` + 数字で始まる曲名」というファイル名が存在すると、先頭のトラック番号が **`disc`（ディスク番号）**、曲名先頭の数字が **`track`（トラック番号）** として誤抽出される。その結果、`initialize_album_context` の `total_discs = max(max_local_disc, max_store_disc)` が汚染され、アルバム全曲のID3タグ `TPOS`（`disc_number`）の分母が異常値になる：
   - **AppID `1944840` (Ghostwire: Tokyo)** [Archive]: 53曲目 `53_17 Doors.wav`（曲名 `"17 Doors"`）が `disc=53, track=17` と誤認され、全65曲の `TPOS` が **`1/53`** に破損。
   - **AppID `1475790` (PHOGS!)** [Archive]: 25曲目 `25-5StarArcade.flac`（曲名 `"5 Star Arcade"`）が `disc=25, track=5` と誤認され、全33曲の `TPOS` が **`1/25`** に破損。
   - **AppID `1394870` (Going Under)** [Archive]: `05_4.8 stars.mp3`, `07_9.01 am.mp3`, `12_401cave.mp3`, `20_401grave.mp3` が `disc=5, 7, 12, 20` と誤認され、全29曲の `TPOS` が **`1/20`** に破損。
   - **AppID `1987320` (Super Nano Blaster)** [Archive]: `19_3INCH5.flac`（曲名 `"_3INCH5"`）が `disc=19, track=3` と誤認され、全22曲の `TPOS` が **`1/19`** に破損。
   - **AppID `2339210` (HAZAMA_QUEEN)** [Review]: 7曲目 `07_18noayamachi.mp3`（曲名 `"18noayamachi"`）が `disc=7, track=18` と誤認され、全7曲の `TPOS` が **`1/7`** に破損した上、プレマッチから外れてReview行き。
2. **アルバム名・マスタリング表記除去前の数値検索によるトラック番号誤爆**:
   - **AppID `3162910` (Parking Garage Rally Circuit Soundtrack)** [Review]:
     ファイル名が `PGRC OST 24 MASTER 01 Main Theme.wav`（24-bit WAV）および `PGRC OST 320 MASTER 01 Main Theme.mp3`（320kbps MP3）となっている。
     現行コードは `re.search(r'(?:^|[\s\-_])(\d{1,3})(?:[\s\-_.]|$)', f.stem)` で左から最初に出現する1〜3桁の数値を探すため、本来のトラック番号 `01`〜`15` ではなく、**全WAVファイルに `track_number = 24`、全MP3ファイルに `track_number = 320`** を割り当ててしまい、さらに埋め込みタグの `meta.get("track_number")` よりもこの誤抽出値を優先したためアライメントが崩壊した。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/track_grouper.py` (`TrackManager.build_file_records`: 110〜149行目)
```python
            # Check for multi-disc compound pattern in filename: e.g. "1_1", "1-01", "02_05"
            disc_track_match = re.match(r'^(\d+)[-_](\d+)', f.stem)
            if disc_track_match:
                file_disc = int(disc_track_match.group(1))
                file_track = int(disc_track_match.group(2))
                if disc == 1 and file_disc > 0:
                    disc = file_disc
                filename_track_val = file_track
                t_num_str = str(file_track)
            else:
                t_num = re.match(r'^(\d+)', f.stem)
                if not t_num:
                    t_num = re.search(r'(?:^|[\s\-_])(\d{1,3})(?:[\s\-_.]|$)', f.stem)
                filename_track_val = int(t_num.group(1)) if t_num else None
                t_num_str = t_num.group(1) if t_num else None
```
1. **111行目の `^(\d+)[-_](\d+)` の問題**:
   - 第2グループ `(\d+)` の直後に区切り文字（空白、`-`、`_`、`.`）があるかを確認していないため、`25-5StarArcade` や `53_17 Doors`（`17` と `Doors` の間は空白だが `53` はトラック番号）、`05_4.8 stars`（小数点）、`07_18noayamachi` 等に無差別マッチする。
   - さらに単一ファイルの文字列だけで即座に `disc = file_disc` を確定しているため、アルバム内の他ファイルが `01_...`, `02_...`, ..., `53_17 Doors` という1枚組の連番であっても、53曲目だけを `Disc 53` にしてしまう。
2. **120〜135行目の順序と優先順位の問題**:
   - アルバム名 `album_name` の除去（128〜135行目）を行う前に `f.stem` に対して数値検索を行っている。
   - `re.search` で途中の数値を拾う際、`24 MASTER 01` や `320 MASTER 01` のように複数の数値トークンがある場合に、ビット数・ビットレート等の共通固定値（`24`, `320`, `16`, `44`, `48`, `96`, `192` 等）をトラック番号として誤採用している。

### 2.2 `src/sst/processing/album_context.py` (`initialize_album_context`: 51〜53行目)
```python
    max_local_disc = max((disc for disc, _ in track_groups.keys()), default=1) if track_groups else 1
    max_store_disc = max((int(track.get("disc", 1)) for track in steam_meta.store_tracklist), default=1) if steam_meta.store_tracklist else 1
    total_discs = max(max_local_disc, max_store_disc)
```
Steamトラックリスト（`steam_meta.store_tracklist`）が存在し、その全トラックが `disc = 1`（`max_store_disc == 1`）であるにもかかわらず、ローカル側の誤抽出された `max_local_disc`（または `The Messenger - Disc II` のように別AppIDとして独立配信されている単一ディスクDLCの `disc = 2`）で `total_discs` を引き上げてしまうため、出力トラックの実ディスクが `1` しかないのに `TPOS = 1/2` や `1/53` が出力される。

---

## 3. 具体的な修正仕様

### 3.1 `TrackManager.build_file_records` (`src/sst/track_grouper.py`) の修正
1. **アルバム名除去を先に行う**:
   `f.stem` から `album_name`（および `short_album`）を除去した `clean_stem` を先に作成し、先頭・途中のトラック番号抽出には `clean_stem`（先頭空白・ハイフン除去後）を使用する。
2. **複合ディスク・トラック番号パターン `^(\d+)[-_](\d+)` の2パス検証（集合整合性チェック）**:
   単一ファイルだけで `disc_track_match` を確定させず、全ファイルの候補を走査した上で、以下の条件をすべて満たす場合のみ複合パターン `(file_disc, file_track)` として採用する：
   - **構文条件**: `re.match(r'^(\d{1,2})[-_](\d{1,3})(?:[\s\-_.]|$)', clean_stem)` にマッチし、かつ直後が小数点＋数字（例: `05_4.8`）ではないこと。
   - **埋め込みタグとの非矛盾**: 埋め込みタグ `meta.get("track_number")` が存在し、その値が第1グループ `int(group(1))` と一致し第2グループ `int(group(2))` と異なる場合（例: `53_17 Doors.wav` で埋め込み `track_number == 53` の場合）、第1グループはディスク番号ではなく**トラック番号**であるため、複合ディスク解釈を棄却する。
   - **アルバム全体のディスク集合整合性**:
     同一の `file_disc` を持つファイルがアルバム内に **複数曲（2曲以上、かつ `file_track == 1` または連番を含む）** 存在し、かつ `file_disc` の最大値が妥当なディスク数（例: `1 <= file_disc <= 10` かつ、全ファイルが `01_...`〜`25_...` の通し番号ではないこと）である場合のみ、`disc = file_disc`, `track = file_track` として採用する。
     それ以外（例: `01_foo`, `02_bar`, ..., `05_4.8 stars`, ..., `25-5StarArcade` のように第1グループがファイル間の通しトラック番号になっている場合）は、第1グループ `int(group(1))` を**トラック番号**（`disc = 1`）、第2グループ以降を**曲名の一部**として扱う（かつ `normalize_title` でも曲名先頭の数字 `17` や `5` や `18` が削られないよう、確定したトラック番号プレフィックスのみを除去して `normalize_title` に渡す）。
3. **途中出現の数値からのトラック番号抽出の改善**:
   先頭数値 `re.match(r'^(\d+)', clean_stem)` が存在せず、文字列途中の数値を探す場合：
   - もし埋め込みタグ `meta.get("track_number")` に有効な正の整数が入っていれば、ファイル名途中の曖昧な数値（`"24 MASTER"` や `"320 MASTER"` や `"Count_321"`）よりも **埋め込みタグの `track_number` を優先** する。
   - ファイル名途中から抽出する場合は、`re.findall(r'(?:^|[\s\-_])(\d{1,3})(?=[\s\-_.]|$)', clean_stem)` で候補を取得し、全ファイルで同一の値を取り続ける固定トークン（例: 全WAVで `"24"`、全MP3で `"320"`）を除外した上で、連番を成す数値トークン（`01`..`15`）をトラック番号として採用する。

### 3.2 `total_discs` と `TPOS` 決定ロジックの修正 (`src/sst/processing/album_context.py` & `src/sst/builder.py`)
1. `initialize_album_context`（`src/sst/processing/album_context.py` 51〜53行目）において：
   `steam_meta.store_tracklist` が存在する場合、構造の正本は Steam であるため（[`docs/METADATA_SOURCE_SPEC.md`](../METADATA_SOURCE_SPEC.md) §2）、`total_discs` は原則として `max_store_disc` を正とする（`steam_meta.store_tracklist` が空の場合のみ `max_local_disc` を使用）。
2. `MetadataBuilder.build_tag_map`（`src/sst/builder.py` 243〜258行目）において：
   `chosen_src in {"STEAM", "MBZ_STEAM_VERIFIED"}` または `pics_track` が存在する場合、ローカルの埋め込みタグ `local_tags.get("disc_number")` に含まれる `/N` で `actual_total_discs` を勝手に拡大しないよう、`res_disc` が実際に `total_discs` を超える場合のみ `actual_total_discs = max(total_discs, int(res_disc))` とする。

---

## 4. 不変条件・禁止事項

- 本物のマルチディスク複合ファイル名（例: AppID `467300` の `01-01-...`, `01-02-...`, `02-01-...` や AppID `3959740` の `01_001_...`, `02_001_...`）では、各ディスク（`01`, `02`）に複数のトラック番号（`01`, `02`, ...）が存在するため、引き続き正しく `disc=1, 2` およびそれぞれの `track` として認識させること。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py`（または新規 `tests/test_track_grouper_extraction.py`）に以下のテストを追加すること。

1. **`test_single_disc_numeric_title_filenames_do_not_corrupt_disc_number`**:
   - **設定**: `tmp_path` に以下の単一ディスク連番ファイル群を作成して `TrackManager.build_file_records` を実行する：
     - `01_monorail hype.mp3`, `05_4.8 stars.mp3`, `07_9.01 am.mp3`, `12_401cave.mp3`, `20_401grave.mp3`（AppID `1394870` 型）
     - `24-NormalTrack.flac`, `25-5StarArcade.flac`（AppID `1475790` 型）
     - `52_Normal.wav`, `53_17 Doors.wav`（AppID `1944840` 型）
     - `06_EP3_sarai_Remix.mp3`, `07_18noayamachi.mp3`（AppID `2339210` 型）
   - **検証**:
     - すべてのレコードの `disc` が **`1`** であること（`5`, `7`, `12`, `20`, `25`, `53` にならないこと）。
     - `filename_track` / `t_num_val` がそれぞれ `5`, `7`, `12`, `20`, `25`, `53`, `7` であること。
     - `norm_stem` に曲名先頭の数字（`"4 8 stars"`, `"5stararcade"`, `"17 doors"`, `"18noayamachi"`）が削られずに残っていること。
2. **`test_genuine_multidisc_compound_filenames_are_still_detected`**:
   - **設定**: `01_001_OPENING.wav`, `01_002_SELECT.wav`, `02_001_OPENING.wav`, `02_002_SELECT.wav`（AppID `3959740` 型）。
   - **検証**: 前半2曲が `disc=1, t_num_val="1", "2"`、後半2曲が `disc=2, t_num_val="1", "2"` として正しく認識されること。
3. **`test_mastering_bitrate_numbers_in_filename_prefix_are_ignored`**:
   - **設定**: `PGRC OST 24 MASTER 01 Main Theme.wav`, `PGRC OST 24 MASTER 02 Menu.wav`, `PGRC OST 320 MASTER 01 Main Theme.mp3`, `PGRC OST 320 MASTER 02 Menu.mp3`（AppID `3162910` 型）。
   - **検証**: `t_num_val` が `"24"` や `"320"` ではなく、正しく `"1"`, `"2"` として抽出されること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_fast_track.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。
