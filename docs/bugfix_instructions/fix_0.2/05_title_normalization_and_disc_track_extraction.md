# 修正指示書 05: タイトル正規化（アポストロフィ・複合語空白）およびディスク/トラック番号抽出の網羅的修正

## 1. 背景と問題の概要

`src/sst/track_grouper.py` の `TrackManager.normalize_title` および `TrackManager.build_file_records` における文字列正規化・ファイル名構造解析に以下の6つの欠陥が存在し、**Review行き12件以上の直接原因**となっている。

### 発生している現象（実データ例）
1. **アポストロフィの空白置換（`' -> " "`）による所有格・短縮形の不一致**:
   - `TrackManager.normalize_title`（85行目）が `'` を `" "`（空白）に置換しているため、アポストロフィの有無で単語が分裂し不一致となる：
     - **AppID `802640` (Deep Rock Galactic)**: Steam `"Coward's Crossing"`（`"coward s crossing"`）vs Local `"Cowards Crossing"`（`"cowards crossing"`）。
     - **AppID `2150000` (Dome Keeper)**: Steam `"Alone with one's thoughts"`（`"alone with one s thoughts"`）vs Local `"Alone with ones thoughts"`（`"alone with ones thoughts"`）。
     - **AppID `2198580` (DREDGE)**: Steam `"The Flames' Defender"`（`"the flames defender"`）vs Local `"44 The Flame's Defender"`（`"the flame s defender"`）。
2. **複合語のスペース有無（`"Butter fly"` vs `"Butterfly"` 等）による不一致**:
   - **AppID `924331` (The Messenger - Disc II)**: Steam `"The Butter fly Matriarch"` vs Local `"The Butterfly Matriarch"`。
   - **AppID `1919620` (Phantom Breaker: Omnia)**: Steam `"Blood Thirst"` vs Local `"Bloodthirst"`。
   - **AppID `2125650` (DJMAX Portable 2)**: Steam `"Brandnew Days"` vs Local `"Brand NEW Days"`。
3. **空白入り複合ディスク・トラック番号 `01 - 02 - Title` の未認識による全曲トラック番号崩壊**:
   - **AppID `1831430` (式神の城II - サウンドトラック)**:
     ファイル名が `01 - 01 - Thema of Shikigami.mp3`〜`01 - 25 - 転生 reborn0.mp3` および `02 - 01 - Thema of Shikigami NAOMI ver..mp3`〜`02 - 25 - ...` となっている。
     `build_file_records`（137行目）の `c_match = re.match(r'^(\d{1,2})[-_](\d{1,3})(?:[^\d]|$)', clean_stem)` がハイフン前後の空白を許容していないためマッチせず、192行目の `leading_match = re.match(r'^(\d+)', clean_stem)` にフォールバックした結果、**Disc 1の全25曲に `track_num = 1`、Disc 2の全25曲に `track_num = 2`（かつ `disc = 1`）** が付与されてアライメントが崩壊した。
4. **区切り文字なし先頭数字 `^(\d+)` の無条件トラック番号抽出と4桁超数字の誤抽出**:
   - **AppID `689920` (1bitHeart Original Soundtrack)**:
     曲名自体が `1bitarrange-ver1-.mp3`〜`1bitarrange-ver4-.mp3`, `1BitHeart(feat.minx).mp3` であるにもかかわらず、192行目の `re.match(r'^(\d+)', clean_stem)` が区切り文字を確認せずに `"1bit"` の先頭 `"1"` をトラック番号として抽出し、7曲すべてに `track_num = 1` を付与した上、曲名から `"1"` を削り取って `"bitarrange ver2"` に変조した。
   - **AppID `2716920` (Kevin(1997-2077) Soundtrack)**:
     曲名自体が `00001-01000.mp3`, `01001-02000.mp3`, `02001-03000.mp3` であるにもかかわらず、`^(\d+)` が5桁の `"01001"` 等を `track_num = 1001` として抽出し、曲名を `"02000"` に切断した。
5. **ファイル名先頭 `Disc 01 - ...` の未抽出と `embedded_track` 検索位置の誤爆**:
   - **AppID `2198580` (DREDGE - Original Soundtrack)**:
     ファイル名が `Disc 01 - DREDGE (Original Game Soundtrack) - 01 Main Theme.wav/.flac/.mp3`, `Disc 02 - DREDGE The Pale Reach (Original Game Soundtrack) - 01 The Pale Reach Theme.wav` となっている。
     - `build_file_records`（108〜115行目）が親ディレクトリ名しか見ずファイル名先頭の `Disc 01` / `Disc 02` / `Disc 03` を見ないため、タグ無し `.wav` がすべて `disc = 1` になる。
     - さらに `.flac` / `.mp3` では、206行目の `num_pattern.search(clean_stem)` が左から最初に一致する数値を探すため、`Disc 01` の Track 01 や `Disc 02` の Track 02 で **`"Disc 01"` / `"Disc 02"` 内の数字にマッチ** し、`norm_stem` に `"dredge original game soundtrack 1 main theme"` を残して `.wav`（`"main theme"`）と別グループに分裂させた。
6. **連番ディスクサブフォルダ（`01. Base_ver` 等）・英数字トラックプレフィックス（`12b.`）・`ost01` 形式の未対応**:
   - **AppID `1899360` (Return Ace Soundtrack)**:
     Steam 80スロット（Disc 1〜4 × 各20曲）に対し、ローカルは `01. Base_ver/`, `02. Tech_ver/`, `03. Rock_ver/`, `04. Oche_ver/` の4つのサブフォルダに各20曲（WAV+MP3）が格納されている。サブフォルダ名に `Disc` / `CD` という文字列がないため全160ファイルが `disc = 1` となり、Disc 2〜4の60スロットが欠損（`20/80`）した。
   - **AppID `3107200` (Anger Foot)**: `12b. ate too much pizza.wav` の `"12b."` が `normalize_title` で除去されない。
   - **AppID `461050` (Murasaki)** / **AppID `865290` (Murasaki Tsurugi)**: `murasaki_ost01.wav`, `mu2_ost01.wav` の `"ost01"` からトラック番号 `1` が抽出されない。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/track_grouper.py` (`TrackManager.normalize_title`: 46〜91行目)
- 55行目: `re.sub(r"^\s*\d{1,3}(?:[\s._-]+|\s*-\s*)", "", t)` が英字サフィックス付きトラック番号（`12b.` 等）に対応していない。
- 85行目: `re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)` により、アポストロフィ（`'`, `’`, `` ` ``）も空白 `" "` に変換されるため、`"Coward's"` が `"coward s"` の2単語に分裂する。

### 2.2 `src/sst/track_grouper.py` (`TrackManager.build_file_records`: 95〜245行目)
- 108〜115行目: ディスク番号抽出が親ディレクトリの `(?:disc|cd)\s*(\d+)` のみであり、ファイル名先頭の `^(?:disc|cd)\s*0*(\d+)` や、全サブフォルダが `01. ...`, `02. ...` の連番になっているマルチディスク構造を認識できない。
- 137行目: `c_match = re.match(r'^(\d{1,2})[-_](\d{1,3})(?:[^\d]|$)', clean_stem)` が `01 - 02 - Title`（空白ありハイフン）にマッチしない。
- 192〜199行目: `leading_match = re.match(r'^(\d+)', clean_stem)` が直後の区切り文字（`[\s._-]`）も数値範囲（`1 <= val <= 300`）も確認せず、`1bitarrange` や `01001-02000` の先頭数字をトラック番号として破壊的に切り取る。
- 206〜214行目: `embedded_track` がある場合に左端の `search` を使うため `Disc 01` の `01` に誤爆し、また `ost01` のような `(?:ost|trk|track|bgm)0*(\d{1,3})$` パターンを拾えない。

---

## 3. 具体的な修正仕様

### 3.1 `TrackManager.normalize_title` (`src/sst/track_grouper.py`: 46〜91行目) の修正
1. **アポストロフィの空白なし除去**:
   85行目の記号空白化（`re.sub(r"[^\w\s]", " ", t)`）の **直前** に、単語内のアポストロフィ類（`'`, `’`, `‘`, `` ` ``, `´`）を空文字 `""` に除去する：
   ```python
   t = re.sub(r"['’‘`´]", "", t)
   ```
   これにより `"Coward's"` と `"Cowards"` はどちらも `"cowards"`、`"one's"` と `"ones"` はどちらも `"ones"`、`"Flame's"` と `"Flames'"` はどちらも `"flames"` に統一される。
2. **先頭トラック番号プレフィックス除去の改善**:
   `strip_track_prefix=True` のとき、`01 - 02 - Title` のような複合プレフィックス（`r"^\s*\d{1,2}\s*[-_]\s*\d{1,3}(?:[\s._-]+)"`）および `12b. Title` のような英字1文字付きトラック番号（`r"^\s*\d{1,3}[a-z]?(?:[\s._-]+|\s*-\s*)"`）を除去する。
   ただし `1bitarrange` のように数字直後に区切り文字がなく3文字以上の英字が続く単語は絶対に削らないこと。
3. **空白無視比較（Compact Match）の併用**:
   `prematch.py`（`_titles_match`）、`slot_variants.py`（`_normalized_titles_match`）、`unassigned.py` において、正規化タイトル双方が5文字以上で `s_title.replace(" ", "") == l_title.replace(" ", "")` が成り立つ場合（`"the butter fly matriarch"` vs `"the butterfly matriarch"`, `"blood thirst"` vs `"bloodthirst"`, `"brand new days"` vs `"brandnew days"`）は完全一致と同等に扱う。

### 3.2 `TrackManager.build_file_records` (`src/sst/track_grouper.py`: 95〜245行目) の修正
1. **連番サブフォルダおよびファイル名先頭 `Disc N` からのディスク番号抽出**:
   - **ファイル名先頭 `Disc N` / `CD N` の抽出と除去**:
     `clean_stem` が `r'^(?:disc|cd)\s*0*(\d{1,2})\b[\s._-]*'`（大文字小文字無視）で始まる場合、もし `disc == 1` なら `disc = int(m.group(1))` を設定し、**`clean_stem` の先頭からその `Disc N - ` プレフィックスを除去** する（さらに除去後の先頭にアルバム名やサブタイトル `DREDGE ... (Original Game Soundtrack) - ` が残っている場合も除去する）。これにより `2198580` (DREDGE) の `.wav` に正しい `disc = 1, 2, 3` が設定され、かつ `.flac`/`.mp3` で `"Disc 01"` の `"01"` に誤爆する問題も根絶される。
   - **連番サブフォルダ（`01. Base_ver`, `02. Tech_ver` 等）のディスク認識**:
     親ディレクトリに `disc`/`cd` がない場合でも、アルバム内のファイル群が2つ以上の直近サブフォルダに分かれており、各サブフォルダ名が `r'^\s*0*(\d{1,2})(?:[\s._-]+)'`（`1` から始まる連番 `1..K`, `2 <= K <= 10`）で始まり、かつ各サブフォルダ内にそれぞれ `01` から始まる複数トラックが存在する場合（AppID `1899360` 型）、そのサブフォルダ先頭番号を `disc` として採用する。
2. **複合ディスク・トラック番号パターン `c_match`（137, 189行目）の空白許容**:
   - 137行目の正規表現を `r'^(\d{1,2})\s*[-_]\s*(\d{1,3})(?:[\s._-]|$)'` に拡張し、`01 - 02 - 飛翔 flying`（AppID `1831430`）のような空白付きハイフンにもマッチさせる。
   - ただし、第1グループまたは第2グループが4桁以上（例: `00001-01000`）の場合や、アルバム全体の集合整合性チェック（`is_genuine_compound`: 複数ディスクが存在し各ディスクがTrack 1から始まること）を満たさない単一ディスクの曲名（`53_17 Doors` 等）は引き続き棄却する。
   - 189行目のプレフィックス除去も `re.sub(r'^\d{1,2}\s*[-_]\s*\d{1,3}[\s._-]*', '', clean_stem)` に合わせる。
3. **先頭数字 `leading_match`（192〜200行目）の厳格化**:
   - `re.match(r'^(\d+)', clean_stem)` を廃止し、**1〜3桁（かつ `1 <= int(val) <= 300`）で直後に明確な区切り文字（`[\s._-]`）が存在するパターン** `re.match(r'^(\d{1,3})[a-z]?(?=[\s._-]+)', clean_stem, re.IGNORECASE)` に限定する。
   - かつ、`00001-01000` のようにハイフン前後がともに4桁以上の数値レンジである場合や、`1bitarrange` のように数字直後に区切り文字がない場合は、先頭数字をトラック番号として抽出せず、`clean_stem` 全体を曲名として保持する。
4. **`ost01` 等の末尾トラック番号抽出の追加（214〜228行目）**:
   - 先頭数字がなく `embedded_track` もない場合（例: `murasaki_ost01.wav`, `mu2_ost01.wav`）、`re.search(r'(?:ost|track|trk|bgm|no)[\s._-]*0*(\d{1,3})$', clean_stem, re.IGNORECASE)` にマッチすればその数値を `filename_track_val` / `t_num_str` として抽出する。

---

## 4. 不変条件・禁止事項

- 修正指示書 `fix_0.1/05_filename_disc_and_track_extraction.md` で修正済みの単一ディスク数値曲名（`53_17 Doors.wav`, `25-5StarArcade.flac`, `05_4.8 stars.mp3`, `07_18noayamachi.mp3`）およびマスタリング数値（`PGRC OST 24 MASTER 01 Main Theme.wav`）のテストケースをすべて維持し、デグレさせないこと。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下の回帰テストを追加すること。

1. **`test_normalize_title_removes_apostrophes_without_splitting_words`**:
   - **検証**:
     - `TrackManager.normalize_title("Coward's Crossing") == TrackManager.normalize_title("Cowards Crossing") == "cowards crossing"`
     - `TrackManager.normalize_title("Alone with one's thoughts") == TrackManager.normalize_title("Alone with ones thoughts") == "alone with ones thoughts"`
     - `TrackManager.normalize_title("The Flame's Defender") == TrackManager.normalize_title("The Flames' Defender") == "the flames defender"`
     - `TrackManager.normalize_title("12b. ate too much pizza") == "ate too much pizza"`
     - `TrackManager.normalize_title("1bitarrange-ver2-") == "1bitarrange ver2"`
2. **`test_build_file_records_handles_spaced_multidisc_and_leading_disc_prefix`**:
   - **設定**:
     - ケースA（AppID `1831430` 型）: `01 - 01 - Thema of Shikigami.mp3`, `01 - 02 - 飛翔 flying.mp3`, `02 - 01 - Thema of Shikigami NAOMI ver..mp3`, `02 - 02 - 飛翔 flying NAOMI ver..mp3`。
     - ケースB（AppID `2198580` 型）: `Disc 01 - DREDGE (Original Game Soundtrack) - 01 Main Theme.wav`, `Disc 02 - DREDGE The Pale Reach (Original Game Soundtrack) - 01 The Pale Reach Theme.wav`。
   - **検証**:
     - ケースAで前半2曲が `disc=1, t_num_val="1", "2"`、後半2曲が `disc=2, t_num_val="1", "2"` となり、`norm_stem` から `"01 - 02 - "` が除去されていること。
     - ケースBで `.wav`（タグ無し）でも `disc=1, 2` および `t_num_val="1"`、`norm_stem="main theme"`, `"the pale reach theme"` が抽出されること。
3. **`test_build_file_records_preserves_1bit_and_numeric_range_titles_and_numbered_subfolders`**:
   - **設定**:
     - `1bitarrange-ver1-.mp3`, `1bitarrange-ver2-.mp3`, `1BitHeart(feat.minx).mp3`（AppID `689920` 型）
     - `00001-01000.mp3`, `01001-02000.mp3`（AppID `2716920` 型）
     - `01. Base_ver/01 Title.wav`, `01. Base_ver/02 Stage.wav`, `02. Tech_ver/01 Title.wav`, `02. Tech_ver/02 Stage.wav`（AppID `1899360` 型）
     - `murasaki_ost01.wav`, `murasaki_ost02.wav`（AppID `461050` 型）
   - **検証**:
     - `1bitarrange-ver2-.mp3` の `norm_stem` が `"1bitarrange ver2"` であり、`t_num_val` が誤って `"1"` にならないこと。
     - `01001-02000.mp3` の `t_num_val` が `"1001"` にならず、`norm_stem` が `"01001 02000"` を保持すること。
     - `01. Base_ver` と `02. Tech_ver` が `disc=1, 2` として認識されること。
     - `murasaki_ost01.wav`, `murasaki_ost02.wav` から `t_num_val="1", "2"` が抽出されること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_fast_track.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

