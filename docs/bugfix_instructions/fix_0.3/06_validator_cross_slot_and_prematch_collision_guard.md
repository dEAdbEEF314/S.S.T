# 修正指示書 06: `ResultValidator` の括弧付きサブタイトル・埋め込みタイトルに対するクロススロット不一致検出と `prematch` 同一埋め込みタイトル衝突ガード

## 1. 背景と問題の概要

全324件の Archive 出力を全数監査した結果、以下の **2件の問題のある Archive（誤Archive）** が確認された。これらは上流のアライメント不具合（指示書01・04で修正）だけでなく、最終関門である [`src/sst/validator.py`](file:///mnt/workspace/S.S.T/src/sst/validator.py), [`src/sst/processor_tracks.py`](file:///mnt/workspace/S.S.T/src/sst/processor_tracks.py), および [`src/sst/llm/prematch.py`](file:///mnt/workspace/S.S.T/src/sst/llm/prematch.py) の検査網の穴をすり抜けて Archive 化されていた。

### 発生している現象（実データ例）
1. **【誤Archive ①：括弧付きサブタイトルを持つファイルの6曲逆順入れ替わり見逃し】AppID `4206020` (Emerald Blue Soundtrack)**:
   - 全8曲。LLM Phase 2 の誤割当により、8曲中6曲が全く別のスロットに配置された：
     - Slot `1_2` (`"The Final Stand"`) ← `7. FAINT OF HEART (End).mp3`
     - Slot `1_3` (`"Contemplation"`) ← `5. UNAUTHORIZED (Boss Fight).mp3`
     - Slot `1_4` (`"Reaffimed Under Pressure"`) ← `4. REALISING FATE (Lab).mp3`
     - Slot `1_5` (`"Realising Fate"`) ← `3. REAFFIRMED UNDER PRESSURE (Sky Factory).mp3`
     - Slot `1_6` (`"Unauthorized"`) ← `2. CONTEMPLATION (Ship Port).mp3`
     - Slot `1_8` (`"Faint Of Heart"`) ← `1. THE FINAL STAND (New Tokyo).mp3`
   - これほど明白な曲入れ替わりが発生していたにもかかわらず、`ResultValidator.validate`（`validator.py:209-269`）が `Official Title Mismatch` を **0件** と判定して Archive を許可してしまった！
   - **見逃した原因**:
     1. ローカルファイル名にすべて括弧付きのステージ名サブタイトル（`"(End)"`, `"(Boss Fight)"`, `"(Lab)"`, `"(Sky Factory)"`, `"(Ship Port)"`, `"(New Tokyo)"`）が付いていたため、`orig_stem` を正規化した文字列が `"faint of heart end"`, `"the final stand new tokyo"` となり、Steam スロット側の正規化タイトル集合 `other_norm_titles`（`"faint of heart"`, `"the final stand"`）と **完全一致（`n in other_norm_titles`）しなかった**。
     2. さらに、`validator.py:221-226` は `track.get("original_title")`, `track.get("clean_title")`, `track.get("original_embedded_title")` を参照しようとしているが、実際には **`processor_tracks.py:224-234` がこれらのキーを `track_meta` 辞書に一切格納していない**（デッドコード化している）ため、ファイル名以外の元タイトル情報が `ResultValidator` に届いていなかった。
2. **【誤Archive ②：同一埋め込みタイトルを持つ別ファイル名の重複Track 11によるSlot 12誤充填】AppID `1832420` (Happy’s Humble Burger Farm: Score (OST))**:
   - 全25曲。Steam スロットは `1_11`: `"Time to Vent"`（262秒）、`1_12`: `"Time to Leave"`。
   - ローカルフォルダには、`12. Time to Leave` の音源が存在せず、代わりに **Track 11（`"Time to Vent"`, 262.75秒）の同一音源が2つの異なるファイル名で重複収録** されている：
     1. `11. Time to Vent.mp3`（262.75秒、埋め込み `title="Time to Vent"`, `track="11/25"`）
     2. `11 - Desktop - Time to Leave.mp3`（262.75秒、ファイル名は `Time to Leave` だが、**埋め込みタグは `title="Time to Vent"`, `track="11/25"`** で中身も Track 11 の音声そのもの！）
   - **すり抜けた原因**:
     1. `prematch.py:471-488`（`extract_deterministic_prematches`）の同一スロット衝突検査が、`local_tracks[idx].get("title") or local_tracks[idx].get("norm_stem")` のみを見ていた。2つのファイルはどちらも埋め込み `title` が `"Time to Vent"` であったため、`norm_titles = {"time to vent"}`（`len(norm_titles) == 1`）となり、ファイル名ステム（`norm_stem`）が `"time to vent"` と `"desktop time to leave"` で食い違っているにもかかわらず **「同一曲の複数フォーマット/コピー」と誤認して両方とも `v_idx=10`（Slot 11）のプレマッチ候補に通してしまった**。
     2. その後、2つ目のファイル `11 - Desktop - Time to Leave.mp3` が Phase 2 の `v_idx=11` バグ（指示書01で修正）によって Slot 12（`"Time to Leave"`）に割り当てられた。
     3. 最終段の `ResultValidator` は `original_filename`（`"11 - Desktop - Time to Leave.mp3"`）の `" - "` 後半 `"Time to Leave"` だけを見て Slot 12 と一致すると判断し、**元の埋め込みタイトル `original_embedded_title` が `"Time to Vent"`（Slot 11 の曲名！）であり、かつ Slot 11 に採用されたファイルと再生時間（262.75秒）も埋め込みタイトルも同一の重複音源であること**を見逃して Archive にしてしまった。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/processor_tracks.py` (`process_single_track`: 223〜235行目)
```python
        return {
            "track_meta": {
                "file_path": f"{disc_subdir}/{processed_path.name}",
                "original_filename": adopted_info["path"].name,
                "tags": tag_map,
                "source": instr.get("reason") or ("STEAM" if tag_map.get("title_source") == "STEAM" else "Fallback"),
                "title_source": tag_map.get("title_source", "UNKNOWN"),
                "slot_key": f"{slot_key[0]}_{slot_key[1]}",
                "source_format": adopted_info["path"].suffix.lower().lstrip("."),
                "tier_rank": adopted_info.get("tier_rank", 999),
                "field_provenance": field_provenance,
            },
```
- `validator.py:221` が参照している `"original_embedded_title"`（`adopted_info.get("meta", {}).get("title")`）、`"clean_title"`（`clean_title`）、および `"original_duration_s"`（`adopted_info.get("duration_s")`）が `track_meta` に含まれていない。

### 2.2 `src/sst/validator.py` (`ResultValidator.validate`: 219〜269行目)
```python
                    for key in ("original_title", "clean_title", "original_embedded_title"):
                        val = track.get(key)
                        if val:
                            local_candidates.append(str(val))
```
1. `local_candidates` から正規化タイトル集合 `local_norms` を作る際、丸括弧・角括弧の補足表記 `(...)` / `（...）` / `[...]`（例: `(New Tokyo)`, `(Boss Fight)`, `(End)`）を除去したコアタイトルを `local_norms` に追加していない。そのため、`4206020` のようにローカルファイル名に括弧付きステージ名が付いていると、別スロットの公式タイトルとの一致を全く検出できない。
2. また、`original_embedded_title`（元の埋め込みタイトルタグ）が存在し、それが割り当て先スロットの公式タイトルとは一致せず別スロットの公式タイトルと完全一致する場合（`1832420` で Slot 12 `"Time to Leave"` に割り当てられたファイルの埋め込みタイトルが Slot 11 の `"Time to Vent"` である場合）、たとえファイル名の一部が `"Time to Leave"` を含んでいても、ファイル名と埋め込みタイトルが別々のスロットを指して矛盾しているため Review へ送る必要がある。

### 2.3 `src/sst/llm/prematch.py` (`extract_deterministic_prematches`: 471〜488行目)
```python
        norm_titles = {
            TrackManager.normalize_title(
                str(local_tracks[idx].get("title") or local_tracks[idx].get("norm_stem") or "")
            )
            for idx in distinct_track_indices
        }
        norm_titles.discard("")
        if len(norm_titles) > 1:
            # Collision of different titles on the same slot: defer to LLM
            continue
```
- `local_tracks[idx].get("title")` が存在すると `norm_stem`（ファイル名由来の正規化タイトル）を完全に無視するため、同じ埋め込みタイトル `"Time to Vent"` を持つがファイル名が `"11. Time to Vent.mp3"` と `"11 - Desktop - Time to Leave.mp3"` のように別曲名を示している2つの別ファイル（どちらも `.mp3` で同一フォーマット）を衝突として検出できない。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/processor_tracks.py` の修正
1. **`track_meta` への元ファイル属性の格納**:
   - `process_single_track`（224〜234行目）が返す `"track_meta"` 辞書に以下のフィールドを追加する：
     ```python
     "clean_title": clean_title,
     "original_embedded_title": (adopted_info.get("meta") or {}).get("title") or "",
     "original_track_number": (adopted_info.get("meta") or {}).get("track_number") or adopted_info.get("filename_track") or "",
     "duration_s": adopted_info.get("duration_s"),
     ```

### 3.2 `src/sst/validator.py` (`ResultValidator.validate`: 219〜269行目) の修正
1. **括弧付きサブタイトル除去後のコアタイトルによるクロススロット不一致検出**:
   - `local_candidates` から `local_norms` を生成する際、各候補文字列から末尾または途中の括弧表記 `r"\s*[\(\[（【][^)\]）】]*[\)\]）】]"` を除去した文字列も正規化して `local_norms_no_paren` として保持する。
   - 割り当て先スロット `slot_key` の正規化タイトル集合 `assigned_norms`（括弧除去版も含む）と `local_norms` / `local_norms_no_paren` が **一切共通要素を持たず（自身のスロットと不一致）**、かつ `local_norms` または `local_norms_no_paren` の要素が **別スロット `k != slot_key` の公式タイトル集合 `other_norm_titles` と完全一致する場合**（かつ既存の連番・プレフィックス保護条件に該当しない場合）は、`this_track_mismatched = True`（`Official Title Mismatch`）として検出する。
   - **効果**: これにより、仮に上流で `4206020` のような括弧付きサブタイトルを持つファイルのクロススロット誤配置が起きたとしても、`ResultValidator` が6曲すべてを確実に `Official Title Mismatch` として捕捉し、誤 Archive を100%阻止できる。
2. **埋め込みタイトル（`original_embedded_title`）とファイル名のスロット間矛盾（ハイブリッド汚染）の検出**:
   - `track.get("original_embedded_title")` が非空であり、その正規化文字列 `emb_norm` が：
     1. 割り当て先スロット `slot_key` の公式タイトル集合 `assigned_norms` と一致せず（かつ部分一致もせず）、
     2. アルバム内の **別スロット `other_k != slot_key` の公式タイトルと完全一致** しており、
     3. さらにその別スロット `other_k` に採用されたトラックの元の埋め込みタイトルまたはファイル名も `emb_norm` であり、かつ再生時間差が ±1.0秒以内（つまり別スロット `other_k` の重複音源がファイル名だけ変えて `slot_key` に紛れ込んでいる状態：AppID `1832420`）である場合、
     `this_track_mismatched = True`（`Official Title Mismatch`）として確実に Review へ送る。

### 3.3 `src/sst/llm/prematch.py` (`extract_deterministic_prematches`: 471〜495行目) の修正
1. **同一スロットに複数の同一フォーマットファイルがマッチした際の `norm_stem` 乖離チェック**:
   - `len(distinct_track_indices) > 1` のとき、`norm_titles`（埋め込みタイトル優先）だけでなく、ファイル名由来の `norm_stems`（`TrackManager.normalize_title(str(local_tracks[idx].get("norm_stem") or ""))`、および `"<Artist/Tag> - "` 除去後のコアステム）も確認する。
   - もし `distinct_track_indices` 内に **同一拡張子（例: 両方 `.mp3`）** のファイルが複数あり、一方は `norm_stem` が当該 `steam_slot` のタイトルと一致するが、もう一方の `norm_stem`（または `" - "` 後半）が当該 `steam_slot` と一致せず **アルバム内の別の Steam スロットのタイトルと完全一致する場合**（AppID `1832420` の `11. Time to Vent.mp3` vs `11 - Desktop - Time to Leave.mp3`）：
     - `norm_stem` が当該 `steam_slot` と一致する正当なファイル（`11. Time to Vent.mp3`）のみを `deterministic_prematches` に採用し、ファイル名と埋め込みタイトルが矛盾している異常ファイル（`11 - Desktop - Time to Leave.mp3`）はプレマッチから除外する。

---

## 4. 不変条件・禁止事項

- 同一スロットの正当なフォーマットバリアント（例: タグなし `01.wav` とタグ付き `01 - Title.mp3`、あるいは中国語ファイル名 `01_中文.wav` と英語ファイル名 `01_English.mp3` の異フォーマットペア）を衝突として排除してはならない（3.3 のチェックは「別スロットの公式タイトルと完全一致する `norm_stem` を持つ同一フォーマット重複ファイル」に限定すること）。
- 本編に `"Theme"` と `"Theme (Extended)"` の2スロットが存在するアルバムにおいて、Slot `"Theme (Extended)"` に正しく配置された `"Theme (Extended).mp3"` の括弧を除去した結果が別スロット `"Theme"` と一致するからといって誤検知してはならない（自身の割り当て先スロット `assigned_norms` と既に一致している場合は `not (local_norms & assigned_norms)` が `False` となるため、決して誤検知されない）。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下の合成回帰テストを追加すること。

1. **`test_validator_detects_cross_slot_mismatch_with_parenthetical_location_subtitles`**:
   - **設定**:
     - Steam トラックリスト: `1_2` = `"The Final Stand"`, `1_8` = `"Faint Of Heart"`。
     - トラック結果: Slot `1_2` に `original_filename="7. FAINT OF HEART (End).mp3"` (`tags.title="The Final Stand"`), Slot `1_8` に `original_filename="1. THE FINAL STAND (New Tokyo).mp3"` (`tags.title="Faint Of Heart"`) が割り当てられた状態（AppID `4206020` 型）。
   - **検証**: `ResultValidator.validate` が括弧除去後のコアタイトル（`"faint of heart"`, `"the final stand"`）のクロススロット一致を検出し、`Official Title Mismatch (2)` として確実に `status == "review"` を返すこと。
2. **`test_validator_and_prematch_detect_duplicate_audio_with_conflicting_embedded_title_and_filename`**:
   - **設定**:
     - Steam トラックリスト: `1_11` = `"Time to Vent"` (262s), `1_12` = `"Time to Leave"` (120s)。
     - ローカルファイル:
       - `11. Time to Vent.mp3` (`title="Time to Vent"`, `norm_stem="time to vent"`, `dur=262.7`)
       - `11 - Desktop - Time to Leave.mp3` (`title="Time to Vent"`, `norm_stem="desktop time to leave"`, `dur=262.7`)（AppID `1832420` 型）。
   - **検証**:
     - `extract_deterministic_prematches` が Slot 11 (`v_idx=10`) には `11. Time to Vent.mp3` のみを確定させ、`11 - Desktop - Time to Leave.mp3` を混ぜないこと。
     - 万が一 `11 - Desktop - Time to Leave.mp3` が Slot 12 (`1_12`) に採用されて `ResultValidator.validate` に渡された場合でも、`original_embedded_title="Time to Vent"` と Slot 11 との重複汚染により `Official Title Mismatch` で `status == "review"` となること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_audit_contracts.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

