# 修正指示書 04: トラック番号オフセット・入れ替わりアルバムに対するアルバム全体1対1厳密タイトル照合プレマッチと番号プレフィックス不整合フォールバック防止

## 1. 背景と問題の概要

全352件バッチ処理の監査において、ローカルファイルにトラック番号（ファイル名先頭番号または埋め込み `track_number` タグ）が存在するものの、**0始まり連番・途中欠番・Steam側連番欠番・2曲順序入れ替わり等によりローカルの番号 `track_num` と Steam スロット番号 `n` がズレているアルバム**において、曲名が一字一句（または正規化後1対1で）完全一致しているにもかかわらず [`src/sst/llm/prematch.py`](file:///mnt/workspace/S.S.T/src/sst/llm/prematch.py) が番号一致スロットしか探さずにプレマッチを諦め、後段の LLM Phase 2 や `_recover_prematch_fallback_slots`（[`src/sst/llm/organizer.py`](file:///mnt/workspace/S.S.T/src/sst/llm/organizer.py)）で深刻な誤割当や Review 落ちを引き起こしている事象が **5件（誤Archive 1件・Review 4件）** 確認された。

### 発生している現象（実データ例）
1. **【0始まりファイル番号による誤Archive】AppID `4206020` (Emerald Blue Soundtrack)**:
   - 全8曲。Steam スロットは `1_1 Rebel`〜`1_8 Faint Of Heart`（1始まり）。
   - ローカルファイルは `0. REBEL.mp3`〜`7. FAINT OF HEART (End).mp3`（0始まり、埋め込みタグなし）。
   - `0. REBEL.mp3` は `track_num = None` となったため番号なしタイトル照合で `1_1 Rebel` にマッチしたが、`1. THE FINAL STAND (New Tokyo).mp3`〜`7. FAINT OF HEART (End).mp3` は `track_num = 1..7` が抽出されたため、`prematch.py` は番号が同じ Steam スロット `1_1..1_7`（1つ前の曲！）としか比較せず、7曲すべてがプレマッチ不成立となった。
   - その結果、Phase 2 で LLM が逆順のスロット番号を出力し、**8曲中6曲が別々のスロットに入れ替わったまま Archive された**。
2. **【Steam側のスロット番号欠番＋0始まりタイトルプレフィックスによる連鎖誤割当】AppID `2943720` (CULT VS GAL SOUNDTRACK)**:
   - 全7曲。Steam スロット番号は **`1, 3, 4, 5, 6, 7, 8`（スロット番号 `2` が欠番）** であり、かつ Steam 公式タイトル自体に `00_`〜`06_` のプレフィックスが含まれている：
     - `1_1`: `"00_OMOHIDE LOOP"`
     - `1_3`: `"01_SHIKATANAKATTA NO TSUMI"`
     - `1_4`: `"02_SHIKATANAKATTA NO TSUMI_OPPY"`
     - `1_5`: `"03_SHIKATANAKATTA NO TSUMI_orgel"`
     - `1_6`: `"04_CULT VS GAL"`
     - `1_7`: `"05_CULT VS GAL_FC"`
     - `1_8`: `"06_SHIKATANAKATTA NO TSUMI_DEV"`
   - ローカルファイル名は `00_OMOHIDE LOOP.mp3`〜`06_SHIKATANAKATTA NO TSUMI_DEV.mp3` で **Steam公式タイトルと100%完全一致**している！
   - しかし `build_file_records` が先頭の `01_`〜`06_` から `track_num = 1..6` を抽出したため、`prematch.py` は `track_num == n` で比較してズレにより不成立となった。
   - さらに悪いことに、`organizer.py:_recover_prematch_fallback_slots`（353〜379行目）が「同じ番号 `n=3` のローカル `03_SHIKATANAKATTA NO TSUMI_orgel` と Steam `1_3 (01_SHIKATANAKATTA NO TSUMI)`」を `titles_are_compatible` で比較した際、両方の先頭番号 `03_` と `01_` を削った結果 `"shikatanakatta no tsumi"` が `"shikatanakatta no tsumi orgel"` に部分一致してしまい、**2曲ズレたスロットへ誤フォールバック割当**して Review 落ちとなった。
3. **【番号なしファイル名＋ズレた埋め込みトラック番号タグ】AppID `3994280` (Easy Delivery Co. Soundtrack)**:
   - 全27曲。ファイル名はすべて番号なし（`Easy Delivery Co..flac`, `Rainless.flac`, `It_s No Problem.flac` 等）で、**27曲すべてのファイル名/タイトルが Steam 公式タイトルと1対1で完全一致**している。
   - しかし一部のファイルに Steam の曲順とは異なるアルバム順の埋め込み `track_number` タグが入っていたため、`track_num is not None` となり、`prematch.py` の番号なしタイトル照合（`resolve_prematch_signals` 376行目 `else:` 分岐）がスキップされ、16曲が未確定となって Phase 2 で崩壊した。
4. **【途中1曲欠番による後続22曲の番号-1シフト】AppID `942070` (Ultra Space Battle Brawl Original Soundtrack)**:
   - Steam 全28曲に対し、ローカルは Track 5（`Character Select`）が欠落し、代わりに末尾にボーナストラック `28. Raden Theme - Chiptuned.mp3` が入っているため、ローカルの `06. Nyammo Theme.mp3`〜`27. Turn Back Time (feat. Manami Matsumae).mp3` のトラック番号 `6..27` が Steam スロット `1_7`〜`1_28` に対してすべて `-1` シフトしている。
   - 曲名（`Nyammo Theme`, `AFRO Theme - Chiptuned` 等）も再生時間も Steam スロット `1_7`〜`1_28` と1対1で完全一致しているにもかかわらず、`track_num == n` しか見ないため20曲がプレマッチ失敗となった。
5. **【Steam PICS 上の隣接2曲の番号スワップ】AppID `1299740` (FlatOut 4: Total Insanity Soundtrack)**:
   - Disc 1 において、ローカルは `09_PRINCESS_HOLLYWOOD.mp3`（Track 9）と `10_HELLRIDE.mp3`（Track 10）であるが、Steam PICS の定義では `index 8` が `tracknumber=10, title="Princess Hollywood"`、`index 9` が `tracknumber=9, title="Hellride"` と番号が入れ替わっている。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/prematch.py` (`resolve_prematch_signals`: 369〜394行目)
```python
        if track_num is not None:
            matched_slot = _find_matching_steam_slot(
                track,
                str(track_num),
                disc_val,
                steam_by_disc_and_track,
                steam_slots_by_num,
                full_ref_steam,
            )
        else:
            # Unnumbered local file: match only if exact title matches a unique Steam slot
```
1. **`track_num is not None` のときに `_find_matching_steam_slot` が `None` を返した場合のフォールバック欠如**:
   - ローカルファイルにトラック番号が付いている場合、その番号のスロットとタイトルが一致しないと即座に `matched_slot = None` で終了し、アルバム内の他スロットとの1対1厳密タイトル一致を一切探さない。
2. **プレフィックス付き公式タイトル（`"01_SHIKATANAKATTA NO TSUMI"`）の非ストリップ完全一致の優先度不足**:
   - `_exact_title_match` が常に `strip_track_prefix=True`（デフォルト）で先頭数値を削ってから比較するため、Steam 公式タイトル自体が `"01_..."`, `"02_..."` のように番号プレフィックスを含んでいるケース（`2943720`）で、ファイル名（`01_...`）との完全一致を直接検出していない。

### 2.2 `src/sst/llm/organizer.py` (`_recover_prematch_fallback_slots`: 353〜379行目)
```python
            if (
                local_slot == steam_slot
                and str(s_track.get("v_idx")) not in mapped_slots
                and titles_are_compatible(local_title, steam_title)
            ):
```
- `local_title`（例: `"03_SHIKATANAKATTA NO TSUMI_orgel"`）と `steam_title`（例: `"01_SHIKATANAKATTA NO TSUMI"`）の両方に明示的な先頭番号プレフィックス（`03_` vs `01_`）が存在し、その番号が互いに食い違っているにもかかわらず、`titles_are_compatible` が両方の先頭番号を削って部分一致させてしまう。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/llm/prematch.py` の修正
1. **非ストリップ（生タイトル）完全一致の追加と括弧内ロケーション補足対応**:
   - `_exact_title_match(track, steam_slot)`（133〜170行目）において：
     - まず `TrackManager.normalize_title(..., strip_track_prefix=False)`（先頭番号を削らない正規化）同士が完全一致する場合（例: `"01_SHIKATANAKATTA NO TSUMI"` == `"01_SHIKATANAKATTA NO TSUMI"`）、即座に `True` を返す。
     - ただし、もし `steam_slot` の生タイトル自体が `^\d{1,3}[\s._-]+` で始まっており（例: `"01_..."`）、かつローカルのファイル名・生タイトルも `^\d{1,3}[\s._-]+` で始まっている場合において、**その先頭数値同士が異なる場合（例: ローカル `"03_..."` vs Steam `"01_..."`）は、後続のストリップ後比較で誤マッチしないよう必ず `False` を返す**。
2. **`track_num is not None` で番号一致スロットが不成立だった場合の「アルバム全体1対1厳密タイトル＋尺一致フォールバック」の導入**:
   - `resolve_prematch_signals`（369〜394行目）において、`track_num is not None` で `_find_matching_steam_slot(...)` が `None` を返した場合、諦めずに以下の厳格な条件でアルバム内のスロットを検索する：
     1. まず同一ディスク（`int(s.get("d", 1) or 1) == disc_val`）、そこになければ全ディスクの `full_ref_steam` から、`_exact_title_match(track, s)` が `True` となるスロット候補 `exact_candidates` を探す。
     2. もし `exact_candidates` が空であり、かつローカルファイル名またはタイトルに括弧付きサブタイトル（例: `4206020` の `"1. THE FINAL STAND (New Tokyo)"` の `(New Tokyo)`）が含まれている場合は、括弧部分を除去したコアタイトルが Steam スロットの正規化タイトルと **完全一致** するスロット候補を `exact_candidates` とする。
     3. `len(exact_candidates) == 1`（アルバム/ディスク内で **一意に1つのスロットのみ** と完全一致）であるとき、その候補スロット `cand_slot` に対して以下の安全条件を検証する：
        - **再生時間整合**: `cand_slot` に有効な再生時間 `s_dur > 0` があり、ローカルトラックにも `l_dur > 0` がある場合、`|l_dur - s_dur| <= 3.0` 秒であること。
        - **本来の番号保持者との非競合**: アルバム内の他のローカルトラックの中に、`cand_slot` と **同じ `(disc, n)` を持ち、かつ `_titles_match(other_track, cand_slot)` も満たすトラックが存在しない** こと（本来の番号でマッチする正当なトラックが別にある場合は横取りしない）。
     4. 上記を満たす場合、`matched_slot = cand_slot` として決定論的プレマッチを成立させる。

### 3.2 `src/sst/llm/organizer.py` (`_recover_prematch_fallback_slots`: 353〜379行目) の修正
1. **明示的先頭番号プレフィックス食い違い時および別スロット完全一致時のフォールバック抑止**:
   - `_recover_prematch_fallback_slots` において、`local_title` と `steam_title` の両方が `^\s*(\d{1,3})[\s._-]+` の数値プレフィックスを持っており、その数値 `int(m_local.group(1))` と `int(m_steam.group(1))` が異なる場合（AppID `2943720` の `03_...` vs `01_...`）はフォールバック割当を行わない。
   - また、`local_title` にサフィックス（例: `_orgel`, `_OPPY`）が含まれており、そのサフィックスまで含めて完全一致する別の Steam スロットが `steam_Context` 内に存在する場合は、ベースタイトルしか一致しない現在スロットへのフォールバック割当を行わない。

---

## 4. 不変条件・禁止事項

- アルバム内に同名タイトルのスロットが複数存在する場合（`len(exact_candidates) > 1`）に、番号がズレているトラックを曖昧にどちらかへプレマッチしてはならない。
- 再生時間が3秒以上乖離している別バージョン（Extended 版と Short 版など、例: AppID `3107200` の `12b. ate too much pizza.wav` [160s] vs Slot 36 `ate too much pizza` [131s]）をこのフォールバックで本編スロットへマッチさせてはならない（`dur_diff <= 3.0` ガードおよび他トラック競合ガードにより、`3107200` のボーナス曲 `12b` は確実に除外される）。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下の合成回帰テストを追加すること。

1. **`test_prematch_resolves_zero_indexed_local_files_with_parenthetical_location_subtitles`**:
   - **設定**: Steam スロットが `1_1 Rebel`〜`1_8 Faint Of Heart`（1始まり）で、ローカルファイルが `0. REBEL.mp3`〜`7. FAINT OF HEART (End).mp3`（`1. THE FINAL STAND (New Tokyo).mp3` 等、0始まり番号＋括弧サブタイトル付き）の8曲（AppID `4206020` 型）。
   - **検証**: `extract_deterministic_prematches` が8曲すべてを正しい Steam スロット `v_idx=0..7`（`1_1`〜`1_8`）に1対1で決定論的にプレマッチすること。
2. **`test_prematch_resolves_literal_numbered_steam_titles_with_skipped_slot_number`**:
   - **設定**: Steam スロットが `n=1 ("00_OMOHIDE LOOP")`, `n=3 ("01_SHIKATANAKATTA NO TSUMI")`, `n=4 ("02_SHIKATANAKATTA NO TSUMI_OPPY")`, `n=5 ("03_SHIKATANAKATTA NO TSUMI_orgel")`（`n=2` 欠番）で、ローカルファイルが `00_OMOHIDE LOOP.mp3` (`n=0`), `01_SHIKATANAKATTA NO TSUMI.mp3` (`n=1`), `02_SHIKATANAKATTA NO TSUMI_OPPY.mp3` (`n=2`), `03_SHIKATANAKATTA NO TSUMI_orgel.mp3` (`n=3`) の場合（AppID `2943720` 型）。
   - **検証**: 先頭プレフィックス付きの完全一致により全曲が正しい `v_idx` に1対1でプレマッチされ、`03_..._orgel` が `n=3`（`01_...`）に誤割当されないこと。
3. **`test_prematch_resolves_unnumbered_filenames_with_offset_embedded_track_numbers`**:
   - **設定**: ファイル名は番号なし（`Rainless.flac`, `It_s No Problem.flac`）、埋め込み `track_number` が Steam のスロット番号とズレているが、タイトルと再生時間は Steam スロットと1対1で完全一致するケース（AppID `3994280` / `942070` / `1299740` 型）。
   - **検証**: `extract_deterministic_prematches` が一意な厳密タイトル＋再生時間一致により正しい Steam スロットへプレマッチすること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_differential_alignment.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

