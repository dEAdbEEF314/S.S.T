# 修正指示書 03: 決定論的プレマッチの自己衝突解消・完全一致救済・残差確定の前方一致ガードおよび全スロット確定時の確信度昇格

## 1. 背景と問題の概要

LLM呼び出し前の決定論的プレマッチ（[`src/sst/llm/prematch.py`](file:///mnt/workspace/S.S.T/src/sst/llm/prematch.py)）、LLM呼び出し後の決定論的残差確定（[`src/sst/processing/unassigned.py`](file:///mnt/workspace/S.S.T/src/sst/processing/unassigned.py)）、および全スロット確定時の確信度判定（[`src/sst/llm/organizer.py`](file:///mnt/workspace/S.S.T/src/sst/llm/organizer.py)）に以下の4つの欠陥が存在し、**Review行き18件以上の直接原因**となっている。

### 発生している現象（実データ例）
1. **タグ無しWAV（ファイル名由来の `title`）とタグ有りFLAC/MP3（埋め込み `title`）のプレマッチ自己衝突破棄**:
   - **AppID `2198580` (DREDGE - Original Soundtrack)**:
     `.wav` には埋め込みタイトルタグがないため `local_track["title"]` が `best_path.stem`（`"Disc 01 - DREDGE (Original Game Soundtrack) - 02 The Restless Town"`）となり、`.flac` / `.mp3` は埋め込みタグ `"The Restless Town"` となる。
     両方とも `resolve_prematch_signals` で正しく `v_idx=1`（`1_2 The Restless Town`）に決定論的マッチしたにもかかわらず、`extract_deterministic_prematches`（`prematch.py:250-256`）が `local_tracks[idx].get("title")` を正規化して比較し、`"disc 1 dredge original game soundtrack 2 the restless town" != "the restless town"`（`len(norm_titles) == 2 > 1`）と判定して **「異タイトル衝突」として全95スロットのプレマッチを自己破棄** し、15チャンクのLLM Phase 2へ送り込んで崩壊させた。
   - **AppID `1586580` (Narita Boy)** / **AppID `2125650` (DJMAX Portable 2)** / **AppID `3162910` (Parking Garage Rally Circuit)**:
     同様にWAVの `best_path.stem`（`"Narita Boy (Original Game Soundtrack) - 01 - Narita Boy Theme"`、`"01 Forte Escape - Wind ( Opening )"`、`"PGRC OST 24 MASTER 01 Main Theme"`）とMP3の埋め込み `title`（`"Narita Boy Theme"`、`"Wind ( Opening )"`、`"Main Theme"`）が同一スロット上で「異タイトル衝突」と誤認され、全曲または大半の決定論的プレマッチが破棄された。
2. **トラック番号欠落時・Steam欠番時・括弧内日英併記時のプレマッチ漏れと前方一致横取り**:
   - **AppID `2943720` (カルトに厳しいギャル-CULT VS GAL- Soundtrack)**:
     Steamトラックリストの `number` が `1, 3, 4, 5, 6, 7, 8`（`2` が欠番）である一方、ローカルファイル名 `00_OMOHIDE LOOP.mp3`, `01_SHIKATANAKATTA NO TSUMI.mp3`, ..., `06_SHIKATANAKATTA NO TSUMI_DEV.mp3` は **Steamのタイトル文字列と100%完全一致** している。しかし `03_SHIKATANAKATTA NO TSUMI_OPPY.mp3` の先頭 `"03"` が `track_num = 3` として抽出され、Steam `n=3`（`01_SHIKATANAKATTA NO TSUMI`）と部分一致（`s_title in l_title`）したため、完全一致する本物のトラックを差し置いて `1_3` を横取りした。
   - **AppID `1593020` (Milk inside a bag of milk)** / **AppID `3994280` (Easy Delivery Co.)** / **AppID `4284690` (Super Woden: Rally Edge)** / **AppID `2716920` (Kevin(1997-2077))** / **AppID `689920` (1bitHeart)**:
     ファイル名にトラック番号がない（`track_num is None`）ため、Steamスロットと1対1で正規化タイトルが完全一致しているにもかかわらず、`prematch.py:178` の `elif track_num is not None:` によりプレマッチから除外された。
   - **AppID `1940590` (METAL SLUG)** / **AppID `1940600` (METAL SLUG 2)** / **AppID `1921810` (METAL SLUG 3)**:
     Steamタイトルが `THE MILITARY SYSTEM（操作説明、ランキング）`（英語本題＋全角括弧の日本語補足）、ローカルタイトルが `THE MILITARY SYSTEM (Operation Explanation, Ranking)`（同じ英語本題＋半角括弧の英語補足）であり、括弧前のメインタイトル・トラック番号・再生時間がすべて完全一致しているにもかかわらず、括弧内の言語差で `_titles_match` が偽となった。
   - **AppID `1553350` (30XX)** / **AppID `2353511` (PAYDAY 2: Chinatown)** / **AppID `1879310` (TCSTRIKERS4)**:
     `(disc, track_num)` と再生時間が完全一致し、タイトルもSteam側の1〜2文字タイポ・冠詞差（`Millenium Spark` vs `Millennium Spark`, `Hollow (Original Demo)` vs `Hollows (Original Demo)`, `Trailerblazers` vs `Trailblazers`, `The Best Day Of The Life` vs `The Best Day Of Life`）で類似度 `>= 0.85` であるにもかかわらずプレマッチから漏れた。
3. **`reconcile_deterministic_unassigned_slots`（`unassigned.py`）の前方一致（`startswith`）暴走と相互ブロック**:
   - **AppID `1586580` (Narita Boy)**: 未割当の `06 - Memory #1 .wav`（正規化 `"memory 1"`）が、Slot 48 `Memory #12`（正規化 `"memory 12"`）に対して `"memory 12".startswith("memory 1")`（単語境界なし前方一致）でマッチし、Disc 1 Track 6 が Disc 2 Slot 48 へ誤配置された。
   - **AppID `942070` (Ultra Space Battle Brawl)**: Disc 1の `06. Djarwani Theme.mp3`（`"djarwani theme"`）が、Disc 2 Slot 18 `Djarwani Theme (Chiptuned)`（`"djarwani theme chiptuned"`）に前方一致で誤配置された。
   - **AppID `3994280` (Easy Delivery Co.)**: 未割当の `Rainless`（`"rainless"`）と `Rainless (Hum)`（`"rainless hum"`）が、`startswith` により互いのスロット（`1_2` と `1_12`）の `matching_groups` に両方入り込み、完全一致側（`s_title == track_title`）まで相殺されて両方とも救済不能となった。
4. **全Steamスロット確定＋全バリアント統合完了時の `album_confidence = 85%` 取り残し**:
   - **AppID `461050` (Murasaki)** / **AppID `865290` (Murasaki Tsurugi)** / **AppID `1568690` (DJMAX Portable 3)**:
     全Steamスロット（19/19, 18/18, 47/47）が決定論的プレマッチで100%確定し、残りのタグ無しWAVバリアントも `slot_variants.py` で全件スロットに統合されて `unassigned_files == 0` となったにもかかわらず、`align_slots` 時点でタグ無しWAVが `unmatched_local_tracks` に一時残っていたために `album_confidence` が `85%` のまま据え置かれ、`[Album confidence too low (85%)]` のみでReview行きとなった。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/prematch.py`
1. **35〜45行目 (`_titles_match`)**:
   - `local_track.get("title")` のみを見ており、`TrackManager.build_file_records` がアルバム名・ディスク番号・トラック番号を除去して生成した `local_track.get("norm_stem")`（または `local_key[1]`）を併せて評価していない。
   - Steamタイトル末尾の `" by <Artist>"` とローカルファイル名先頭の `"<Artist> - "`（例: `1568690` / `2125650` の `"OUT LAW - Reborn by Mr.Funky"` vs `"01 Mr.Funky - OUT LAW - Reborn"`）を吸収していない。
   - 括弧 `(...)` / `（...）` 内の日英補足差（`METAL SLUG` 3作品の `"THE MILITARY SYSTEM（操作説明、ランキング）"` vs `"THE MILITARY SYSTEM (Operation Explanation, Ranking)"`）を吸収していない。
   - 同一 `(disc, track_num)` かつ再生時間一致時の軽微なタイポ（`SequenceMatcher >= 0.85`）を許容していない。
2. **178〜187行目 (`resolve_prematch_signals`)**:
   - `elif track_num is not None:` のみであり、生のタイトルがSteamスロットと1対1で完全一致するケース（`2943720` の `00_OMOHIDE LOOP`〜`06_...` や、`track_num is None` の `1593020`, `3994280`, `4284690`, `2716920`）を決定論的プレマッチできない。
3. **246〜261行目 (`extract_deterministic_prematches`)**:
   - 同一 `matched_v_idx` に集まった候補群の `local_tracks[idx].get("title")` を正規化して集合サイズ `len(norm_titles) > 1` で衝突判定しているため、タグ無しWAV（アルバム名・アーティスト名入りファイル名）とタグ有りMP3/FLAC（純粋な曲名）が同一スロットに集まると必ず衝突扱いになり、両方ともプレマッチから除外される。

### 2.2 `src/sst/processing/unassigned.py` (`_find_candidate_unassigned_matches`: 10〜44行目)
```python
        title_matches = bool(
            s_title
            and track_title
            and (
                s_title == track_title
                or s_title.startswith(track_title)
                or track_title.startswith(s_title)
            )
        )
```
1. `startswith` に単語境界チェックがないため、`"memory 1"` が `"memory 12"` にマッチする。
2. 完全一致（`s_title == track_title`）と前方一致（`startswith`）を同列に `matching_groups` へ混ぜるため、`"rainless"` と `"rainless hum"` が互いを汚染する。
3. バージョン識別語（`"chiptuned"`, `"demo"`, `"hum"`, `"remix"`, `"mix"`, `"inst"`, `"instrumental"`, `"ver"`, `"long"`, `"short"`, `"edit"`）の有無が異なる別曲を `startswith` で別ディスク・別番号のスロットに結びつけてしまう。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/alignment_inputs.py` (`build_local_album`: 388〜395行目) の改善
- `v_local["tracks"]` の各エントリに、生の `"title"` だけでなく `TrackManager.build_file_records` が抽出したクリーンな `"norm_stem": best.get("norm_stem", "")` を明示的に含める。

### 3.2 `src/sst/llm/prematch.py` の修正
1. **生タイトル1対1完全一致の最優先チェック（`2943720` 等の番号ズレ防止）**:
   - トラック番号による部分一致照合を行う前に、ローカルトラックのファイル名stemまたは埋め込みタイトル（**トラック番号プレフィックス除去前の正規化文字列** `TrackManager.normalize_title(raw, strip_track_prefix=False)`、および除去後の `s_title == l_title`）が、`full_ref_steam` 内の **ただ1つのSteamスロットと完全一致** する場合（かつ、もしローカルとSteam双方に再生時間がある場合は差が `<= 5.0s`）、そのSteamスロットを最優先で `deterministic_number_and_title` として確定する。
   - これにより、`2943720` の `03_SHIKATANAKATTA NO TSUMI_OPPY` は自身の完全一致スロット `n=5`（`03_SHIKATANAKATTA NO TSUMI_OPPY`）に確定し、かつ `track_num is None` のアルバム（`1593020`, `3994280`, `4284690`, `2716920`）でも一意な完全一致タイトルがすべて決定論的プレマッチで確定する。
2. **`_titles_match(local_track, steam_slot, *, same_slot_and_duration: bool = False)` の強化**:
   - ローカル側のタイトル候補として `local_track.get("title")` と `local_track.get("norm_stem")`（または `local_key[1].split("::")[0]`）の双方を評価する。
   - Steam側の `"<Title> by <Artist>"`（`re.sub(r'\s+by\s+.+$', '', s_raw, flags=re.IGNORECASE)`）およびローカル側の `"<Artist> - <Title>"`（`" - "` で分割した後半）も正規化候補に加える。
   - 括弧 `(...)` / `（...）` を除去したメインタイトル同士が非空（4文字以上）で完全一致し、かつ同一 `(disc, track_num)` である場合（例: `METAL SLUG` 1/2/3 の `"THE MILITARY SYSTEM（操作説明、ランキング）"` vs `"THE MILITARY SYSTEM (Operation Explanation, Ranking)"`）も一致と判定する。
   - `s_title in l_title` または `l_title in s_title`（部分一致）を適用する際は、**必ず単語境界（空白または文字列端）で一致し、かつ数値トークンの矛盾（`"memory 1"` vs `"memory 12"` 等）や別スロットへの完全一致候補が存在しないこと** を条件とする。
   - `same_slot_and_duration=True`（`(disc, track_num)` が一致し、かつ再生時間差 `<= 3.0s` またはSteam側duration未設定）の場合に限り、`SequenceMatcher(None, l_title, s_title).ratio() >= 0.84`（`Millenium` vs `Millennium`, `Hollow` vs `Hollows`, `Trailerblazers` vs `Trailblazers`, `The Best Day Of Life` vs `The Best Day Of The Life`）もタイトル整合と判定する。
3. **`extract_deterministic_prematches`（246〜267行目）の自己衝突誤検知の解消**:
   - 同一 `matched_v_idx` に複数のローカルトラック候補が集まった際、それらの生の `title` 同士が完全一致しなくても：
     - 各候補がすべて対象 `steam_slot = full_ref_steam[matched_v_idx]` に対して `_titles_match(cand_track, steam_slot)` を満たしており、**かつ**
     - 候補間の再生時間差が `<= 3.0s`（同一曲のWAVとMP3/FLACバリアント）である場合は、**衝突（`colliding_v_indices`）とみなさず**、すべてのフォーマットバリアントを決定論的プレマッチとして確定させる。

### 3.3 `src/sst/processing/unassigned.py` (`reconcile_deterministic_unassigned_slots`) の修正
1. **完全一致（Exact Match）と部分一致（Substring/Prefix Match）の2段階分離**:
   - 第1パスでは `s_title == track_title`（正規化タイトル完全一致、または `norm_stem` 完全一致）のみを検索し、1対1（または同一尺バリアント集合）で一致するものを先に確定させる。これにより `3994280` の `"rainless"`（`1_2`）と `"rainless hum"`（`1_12`）が互いに干渉せず両方とも確定する。
2. **第2パス（前方/部分一致）の厳格化**:
   - 第1パスで残った未充填スロットに対してのみ部分一致を試みる際：
     - 必ず **単語境界**（`re.search(rf'(?:^|\s){re.escape(short)}(?:\s|$)', long)`）を要求する（`"memory 1"` が `"memory 12"` にマッチすることを禁止）。
     - 短い方の文字列と長い方の文字列の間で、バージョン識別語（`chiptuned`, `hum`, `demo`, `remix`, `mix`, `ver`, `inst`, `instrumental`, `long`, `short`, `edit`, `bonus`）や数値トークンの有無が異なる場合（例: `942070` の `"djarwani theme"` vs `"djarwani theme chiptuned"`）はマッチを禁止する。
     - ディスク番号またはトラック番号がローカル側で明示されており、それが対象Steamスロットと異なり、かつローカル側の本来の `(disc, track_num)` スロットが別にある場合は横取りを禁止する。

### 3.4 全Steamスロット確定＋未割当0件達成時の確信度整合 (`src/sst/alignment_flow.py` / `src/sst/llm/organizer.py`)
- `execute_alignment_flow`（`src/sst/alignment_flow.py:388-400`）において、決定論的プレマッチまたは残差確定＋`build_slot_variant_index` の完了後に：
  - 全Steamスロットが100%充填されており、**かつ**
  - 全ローカルファイルがいずれかのSteamスロット（または `slot_variant_index`）に統合されて未割当ファイルが0件となり、**かつ**
  - 採用された全スロットが `SYSTEM: Deterministic match` / `STEAM_SLOT_MATCH` / `決定論的残差確定` で確定していて未解決の `contradictory_slot_assignments` が存在しない場合、
  Phase 1でフォーマット数倍差（例: WAV無タグ19 + FLAC19 + MP319 = 57ファイル vs 19スロット）により `album_confidence` が `85%` に留まっていたケース（`461050`, `865290`, `1568690`）について、`organizer.py:729` と同様に確信度を `100%`（`archive_vs_review_ratio = {"archive": 100, "review": 0}`）へ昇格させる。

---

## 4. 不変条件・禁止事項

- タイトルが一致しないトラックをトラック番号と尺だけで `prematch.py` や `unassigned.py` で決定論的確定してはならない。
- 未割当ファイルが残っている場合や、Steamスロットに欠損がある場合に確信度を `100%` に引き上げてはならない。

---

## 5. テスト作成指示

`tests/test_differential_alignment.py` および `tests/test_batch_accuracy_improvements.py` に以下の回帰テストを追加すること。

1. **`test_extract_deterministic_prematches_does_not_collide_untagged_wav_with_tagged_flac`**:
   - **設定**: 同一スロット `v_idx=1`（`"The Restless Town"`）に対し、タグ無しWAV（`title="Disc 01 - DREDGE (Original Game Soundtrack) - 02 The Restless Town"`, `norm_stem="the restless town"`, `duration_ms=224000`）とタグ有りFLAC（`title="The Restless Town"`, `norm_stem="the restless town"`, `duration_ms=224000`）がともに決定論的マッチしている合成データ（AppID `2198580` / `1586580` / `2125650` 型）。
   - **検証**: `extract_deterministic_prematches` が衝突（`colliding_v_indices`）と判定せず、WAVとFLACの双方を決定論的指示として確定させること。
2. **`test_prematch_exact_raw_title_prevents_prefix_number_theft_and_handles_missing_track_num`**:
   - **設定**:
     - ケースA（AppID `2943720` 型）: Steamスロットが `n=1: "00_OMOHIDE LOOP"`, `n=3: "01_SHIKATANAKATTA NO TSUMI"`, `n=5: "03_SHIKATANAKATTA NO TSUMI_OPPY"` で、ローカルファイルが同名の3ファイル。
     - ケースB（AppID `1593020` / `3994280` 型）: `track_num=None` で `"Rainless"`, `"Rainless (Hum)"` のようにSteamスロットと1対1完全一致するローカルトラック。
   - **検証**: ケースAで `03_SHIKATANAKATTA NO TSUMI_OPPY` が `n=3` を横取りせず `n=5` に確定し、`01_SHIKATANAKATTA NO TSUMI` が `n=3` に確定すること。ケースBで両方とも自身のSteamスロットに決定論的プレマッチすること。
3. **`test_reconcile_unassigned_slots_word_boundary_and_exact_priority`**:
   - **設定**: 未充填Steamスロットに `"Memory #12"`、`1_2: "Rainless"`、`1_12: "Rainless (Hum)"`、`2_18: "Djarwani Theme (Chiptuned)"` があり、未割当ローカルに `"06 - Memory #1"`、`"Rainless"`、`"Rainless (Hum)"`、`"06. Djarwani Theme"` がある合成データ。
   - **検証**: `"06 - Memory #1"` が `"Memory #12"` に誤結合されないこと。`"06. Djarwani Theme"` が `"Djarwani Theme (Chiptuned)"` に誤結合されないこと。`"Rainless"` と `"Rainless (Hum)"` がそれぞれ `1_2` と `1_12` に確定すること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_differential_alignment.py tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

