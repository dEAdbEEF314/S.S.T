# 修正指示書 06: Fast-Trackの汎用接尾辞ストップワード拡張・アーティスト付きクロススロットスワップ検出および `MBZ_STEAM_VERIFIED` タイトル検証の適正化

## 1. 背景と問題の概要

全270件の Archive 出力および Review 出力の監査により、[`src/sst/processing/fast_track.py`](file:///mnt/workspace/S.S.T/src/sst/processing/fast_track.py) と [`src/sst/validator.py`](file:///mnt/workspace/S.S.T/src/sst/validator.py) のタイトル整合性チェックに関して、以下の **1件の誤Archive（曲入れ替わり）** と **1件の誤Review（`MBZ_STEAM_VERIFIED` に対する誤検出）** が確認された。

### 発生している現象（実データ例）
1. **【誤Archive（曲スワップ）】AppID `2086480` (DJMAX RESPECT V - Portable Original Soundtrack(REMASTERED))**:
   - ルート: `FAST_TRACK` → **Archive**（全96曲）。
   - Disc 2 (`CD2_RETRO`) の Track 34 と Track 35 において：
     - **Steam定義**:
       - Slot `2_34`: `"ON (Extended Ver.) by ND Lee"`（201秒）
       - Slot `2_35`: `"Eternal Memory ~소녀의 꿈~ (Extended Ver.) by M2U"`（205秒）
     - **ローカルファイル**:
       - `34 M2U - Eternal Memory ~소녀의 꿈~ (Extended Ver.).wav`（埋め込みタイトル `"Eternal Memory ~소녀의 꿈~ (Extended Ver.)"`, アーティスト `"M2U"`, 205.5秒）
       - `35 ND Lee - ON (Extended Ver.).wav`（埋め込みタイトル `"ON (Extended Ver.)"`, アーティスト `"ND Lee"`, 201.3秒）
     - ローカル側のトラック番号 `34` と `35` がSteam側の順序と入れ替わっていたにもかかわらず、`FAST_TRACK` がそのまま番号順（`34 -> 2_34`, `35 -> 2_35`）で確定させ、かつ後段の `ResultValidator` もこれを検出できず、**2曲の中身とタイトルが入れ替わった状態で Archive へパッケージングされた**。
2. **【誤Review（過剰検出）】AppID `355890` (Hotline Miami 2: Wrong Number - Soundtrack)**:
   - ルート: `MBZ_STEAM_VERIFIED`（49/49スロット確定、未割当0件、確信度100%）。
   - Steam Store / MusicBrainz公式リリース（Steam AppID直リンク検証済み）では、Track 1が `"Untitled 2"`、Track 20が `"Untitled"` という曲名になっている。
   - ローカルのTrack 1ファイル `01 Untitled.flac` は、AcoustID Recording MBID の1対1完全一致により公式リリースの Track 1（`"Untitled 2"`）であることが物理的に証明されている（`MBZ_STEAM_VERIFIED`）。
   - しかし `ResultValidator.validate`（`validator.py:224-237`）のクロススロット不一致検査が、`01 Untitled.flac` のファイル名由来タイトル `"untitled"` が Slot `1_20` の `"untitled"` と完全一致することのみを見て、「別スロット `1_20` の曲が `1_1` に誤配置された」と誤判定し、`[Official Title Mismatch (1)]` のみで Review に落とした。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/processing/fast_track.py` (`_fast_track_titles_compatible`: 9〜55行目 / `build_fast_track_group_map`: 130〜143行目)
```python
    stopwords = {
        "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
        "with", "from", "by", "ost", "soundtrack", "theme", "song", "bgm",
        "track", "music", "version", "remix", "mix",
    }
    non_stop_common = common - stopwords
    if len(common) >= 2 and len(non_stop_common) >= 1:
        return True
```
1. **ストップワードの不足**:
   `stopwords` に `"version"`, `"remix"`, `"mix"` は含まれているが、サウンドトラックで頻出する **`"extended"`, `"ver"`, `"edit"`, `"short"`, `"long"`, `"full"`, `"original"`, `"inst"`, `"instrumental"`, `"remastered"`, `"remaster"`, `"bonus"`, `"stage"`, `"boss"`, `"loop"`, `"arrange"`, `"arranged"`, `"feat"`, `"ft"`, `"opening"`, `"ending"`, `"title"`** が含まれていない。
   そのため、`"ON (Extended Ver.) by ND Lee"` と `"Eternal Memory ~소녀의 꿈~ (Extended Ver.)"` を比較した際、共通トークン `common = {"extended", "ver"}` が `len(common) == 2 >= 2` かつ `len(non_stop_common) == 2 >= 1` を満たしてしまい、**全く異なる2曲が「タイトル互換（`True`）」と誤判定**された！
2. **クロススロット衝突検査（137〜142行目）における `" by <Artist>"` / `"<Artist> - "` 未除去**:
   ```python
   other_norm_titles = {
       t_norm for k, t_norm in steam_title_map.items() if k != slot_key and t_norm
   }
   ```
   Steam側のタイトルが `"ON (Extended Ver.) by ND Lee"`（正規化 `"on extended ver by nd lee"`）である一方、ローカルの埋め込みタイトルは `"ON (Extended Ver.)"`（正規化 `"on extended ver"`）、ファイル名は `"35 ND Lee - ON (Extended Ver.)"`（正規化 `"nd lee on extended ver"`）であるため、単純な完全一致集合 `n in other_norm_titles` では Slot `2_34` との一致（クロススロット衝突）を検出できなかった。

### 2.2 `src/sst/validator.py` (`ResultValidator.validate`: 204〜239行目)
1. `fast_track.py` と同様、`steam_slot_norm_titles` が `" by <Artist>"` を含んだままの完全一致比較のみを行っているため、`2086480` のスワップ（ローカル `"on extended ver"` vs Slot `2_34` `"on extended ver by nd lee"`）を検出できない。
2. 逆に `355890` のように、割り当て先スロット `1_1` の公式タイトル `"untitled 2"` 自体がローカルファイル名 `"untitled"` をプレフィックスとして含んでおり（`n in assigned_norm`）、かつファイルのトラック番号 `01` がスロット `1_1` と一致している（さらに `MBZ_STEAM_VERIFIED` でAcoustID Recording MBIDが1対1検証済みである）ケースでも、別スロット `1_20` に `"untitled"` があるというだけで機械的に `mismatched_title_count += 1` としている。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/processing/fast_track.py` の修正
1. **`_fast_track_titles_compatible`（9〜55行目）のストップワード拡張と括弧内バージョン表記の分離**:
   - `stopwords` に以下の汎用音楽メタ語を追加する：
     ```python
     "extended", "ver", "edit", "short", "long", "full", "original",
     "inst", "instrumental", "remastered", "remaster", "bonus",
     "stage", "boss", "loop", "arrange", "arranged", "feat", "ft",
     "opening", "ending", "title", "mode", "select", "result",
     ```
   - さらに、タイトル中に括弧 `(...)` / `（...）` / `[...]` がある場合、**括弧内の汎用バージョン表記（`Extended Ver.`, `Original Mix`, `Remastered` 等）を除いた括弧外の本体タイトル同士に共通の非ストップワード（または部分一致）が1つも存在しない場合は、必ず `False` を返す**。
     - 例: `"ON (Extended Ver.) by ND Lee"`（本体: `"on"`）と `"Eternal Memory ~소녀의 꿈~ (Extended Ver.)"`（本体: `"eternal memory 소녀의 꿈"`）は本体タイトルに共通語が一切ないため `False` となり、Fast-Trackを棄却してアライメントへ回す（またはクロススロット検査で弾く）。
2. **アーティスト名付きタイトルの正規化ヘルパーの導入とクロススロット衝突検査の強化**:
   - Steamタイトル末尾の `r"\s+by\s+.+$"` を除去した正規化タイトル、およびローカルファイル名 `r"^.+?\s+-\s+"`（`Artist - Title`）からアーティスト部を除去した正規化タイトルも生成するヘルパーを用意する。
   - `build_fast_track_group_map`（130〜143行目）において、`steam_title_map` に完全正規化タイトルだけでなく `by <Artist>` 除去後のコアタイトルも登録し、ローカルの埋め込みタイトルまたはアーティスト除去後タイトルが **割り当て先 `slot_key` とは一致せず、他のスロット `k != slot_key` のコアタイトルと完全一致する場合** はクロススロット衝突として `return None`（Fast-Track不成立）とする。

### 3.2 `src/sst/validator.py` (`ResultValidator.validate`: 204〜240行目) の修正
1. **アーティスト表記除去後のクロススロット一致検出**:
   - `steam_slot_norm_titles` を構築する際、生のSteamタイトル正規化文字列に加え、末尾の `" by <Artist>"` を除去したコアタイトルも各スロットのタイトルとして保持する。
   - ローカル側 `local_norms` にも、`orig_stem` から先頭のトラック番号および `"<Artist> - "` を除去したコアタイトル（および `tags.get("artist")` がファイル名に含まれる場合はそれを除去したタイトル）を含める。
   - これにより、AppID `2086480` で `2_34` に `"Eternal Memory ~소녀의 꿈~ (Extended Ver.)"` が入り `2_35` に `"ON (Extended Ver.)"` が入った場合、それぞれのコアタイトルが相手スロット（`2_35`, `2_34`）のコアタイトルと一致し、自身のスロットとは一致しないため、確実に `Official Title Mismatch` として検出・Review隔離される。
2. **同名異番・連番タイトル（`"Untitled"` vs `"Untitled 2"`）および `MBZ_STEAM_VERIFIED` に対する誤検出防止**:
   - 以下の条件を **すべて** 満たす場合は、クロススロット不一致（`this_track_mismatched = True`）と判定しない：
     1. ローカルの正規化タイトル `n` が、割り当てられた自身のスロット `slot_key` の公式正規化タイトル `assigned_norm` と **単語境界付き前方一致（`assigned_norm.startswith(n + " ")`、例: `"untitled"` と `"untitled 2"`）** している、**かつ**
     2. 元ファイル名 `orig_name` から抽出されるトラック番号が割り当て先スロット `slot_key` のトラック番号と一致している（例: `01 Untitled.flac` が `1_1` に割り当てられている）、または `processing_route == "MBZ_STEAM_VERIFIED"` でAcoustID Recording MBIDによる1対1物理検証が完了していること。

---

## 4. 不変条件・禁止事項

- `ResultValidator` の `Official Title Mismatch` 検査自体を無効化したり、別スロットのタイトルと完全一致し自身のスロットと無関係なトラック（`2086480` のスワップ等）を見逃してはならない。
- `_fast_track_titles_compatible` で `(Extended Ver.)` や `(Remix)` の一致のみを根拠に別曲を互換と判定してはならない。

---

## 5. テスト作成指示

`tests/test_fast_track.py` および `tests/test_validator.py`（または `tests/test_batch_accuracy_improvements.py`）に以下の回帰テストを追加すること。

1. **`test_fast_track_rejects_swapped_extended_ver_tracks_with_by_artist_suffix`**:
   - **設定**:
     - Steamスロット: `2_34` = `"ON (Extended Ver.) by ND Lee"` (201s), `2_35` = `"Eternal Memory ~소녀의 꿈~ (Extended Ver.) by M2U"` (205s)。
     - ローカルファイル: `34 M2U - Eternal Memory ~소녀의 꿈~ (Extended Ver.).wav` (埋め込み title=`"Eternal Memory ~소녀의 꿈~ (Extended Ver.)"`, duration=205.5s), `35 ND Lee - ON (Extended Ver.).wav` (埋め込み title=`"ON (Extended Ver.)"`, duration=201.3s)（AppID `2086480` 型）。
   - **検証**:
     - `_fast_track_titles_compatible("Eternal Memory ~소녀의 꿈~ (Extended Ver.)", "ON (Extended Ver.) by ND Lee")` が **`False`** を返すこと。
     - `build_fast_track_group_map` がこのスワップ状態に対して **`None`（Fast-Track不成立）** を返すこと。
     - 仮にスワップされたまま `ResultValidator.validate` に渡された場合でも、`Official Title Mismatch (2)` として確実に **`review`** 判定になること。
2. **`test_validator_does_not_false_positive_on_mbz_steam_verified_untitled_disambiguation`**:
   - **設定**:
     - Steam/MBZ公式トラックリスト: `1_1` = `"Untitled 2"`, `1_20` = `"Untitled"`。
     - 採用トラック: `1_1` に `01 Untitled.flac`（`tags.title = "Untitled 2"`）、`1_20` に `20 Untitled.flac`（`tags.title = "Untitled"`）が配置された全49曲完了状態（AppID `355890` 型）。
   - **検証**: `ResultValidator.validate` が `01 Untitled.flac` を `Official Title Mismatch` と誤判定せず、`archive` と判定すること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_fast_track.py tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

