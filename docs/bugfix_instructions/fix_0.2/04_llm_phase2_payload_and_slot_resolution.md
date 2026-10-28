# 修正指示書 04: LLM Phase 2 ペイロード欠落・チャンク相対番号解決暴走・マルチフォーマット矛盾棄却バグの修正

## 1. 背景と問題の概要

決定論的プレマッチで確定しきれなかった残余トラックを処理する LLM Phase 2（`src/sst/llm/organizer.py`、[`normalization.py`](file:///mnt/workspace/S.S.T/src/sst/llm/normalization.py)、[`assignment_validation.py`](file:///mnt/workspace/S.S.T/src/sst/llm/assignment_validation.py)、[`prompts.py`](file:///mnt/workspace/S.S.T/src/sst/llm/prompts.py)）に以下の3つの連鎖バグが存在し、**Review行き25件以上の直接原因**となっている。

### 発生している現象（実データ例）
1. **Phase 2 プロンプトにおける Steam側 `dur`（再生時間）とローカル側 `n`（トラック番号）の意図せぬ片落ち欠落**:
   - `_simplify_v_album`（`organizer.py:553`）が `v_steam` から `duration_ms`（`dur`）を削り落とし、一方で `_prepare_chunk_payload`（`organizer.py:307-314`）が `LOCAL FILE SIGNALS` から `track_num`（`n`）を削り落としている。
   - その結果、Phase 2のLLMプロンプトでは **Steam側に `n` があって `dur` がなく、ローカル側に `dur` があって `n` がない** 状態となり、日英異言語タイトルアルバム（`336870` 神威, `441260` Deathsmiles, `441950` Deathsmiles Arrange, `442101` Mushihimesama, `466530` 恋姫†演武, `566260` トラブル☆ウィッチーズ, `840070` 恋姫†演武 遼来来, `959840` 鋼鉄のヴァンパイア, `1851920` Milk outside a bag, `1879310` TCSTRIKERS4, `2337040` Wall World, `354350` This War of Mine 等）において、LLMがトラック番号でも再生時間でも照合できなくなっている。
2. **`resolve_slot_key_to_v_idx`（`normalization.py:5-56`）の `fallback_index = value - 1` による部分スロットリスト・マルチディスクへの誤集約とチャンク相対番号暴走**:
   - **部分未充填リストへの誤インデックス参照**:
     プレマッチ後に残った `unfilled_steam_slots` が数件（例: `1919620` では `[v_idx=15 (n=16), v_idx=18 (n=19)]`、`1553350` では `[v_idx=48 (n=49), v_idx=66 (n=67)]`、`3638290` では4件、`1075710` / `1761580` / `802640` では1〜2件）のとき、LLMが `"slots": {"1": ..., "2": ...}` を返すと、`resolve_slot_key_to_v_idx` の49〜51行目 `fallback_index = value - 1` が **`unfilled_steam_slots[0]` や `unfilled_steam_slots[1]` を無条件に返し、全く無関係な未充填スロットへ全ファイルを流し込む**。
   - **`v_idx` 指定時の未解決バグ**:
     逆に **AppID `2353511` (PAYDAY 2: Chinatown Music Pack)** では、`unfilled_steam_slots` が `[{"v_idx": 2, "d": 1, "n": 3, "t": "Trailerblazers"}]` の1件のみで、LLMがプロンプトの `"v_idx": 2` を見て `"slots": {"2": ...}` を返したところ、`resolve_slot_key_to_v_idx` が `track.get("v_idx") == value` をチェックせず、`len(unfilled_steam_slots) == 1 <= 2` のため `None` を返して正当なマッピングを棄却した。
   - **チャンク2以降の相対番号リセットとSlot 1〜10への多重衝突**:
     20ファイル超のアルバムが複数チャンクに分割されると、ローカル側に `n` がないため、LLMがChunk 2・Chunk 3でも `"slots": {"1": ..., "2": ...}` と1番から番号を振り直し（例: `441260` では理由欄に `"Safeguard→セーフガード"`＝Slot 10 と書きながらキーを `"1"` で出力）、Chunk 1のSlot 1〜10と全面衝突して `LLM Contradictory Slot Assignments` を大量発生させている。
   - **`confidence: 0.0` ダミー出力の誤採用**:
     **AppID `1919620` (Phantom Breaker: Omnia)** では、LLMが `"slots": {"1": {"files": [...], "confidence": 0.0, "reason": "No matching STEAM slot"}}` と「該当なし」の意味で出力したにもかかわらず、`normalize_track_mapping_result` が `confidence <= 0.0` をチェックせず有効な割当として採用した。
3. **`reject_contradictory_slot_assignments`（`assignment_validation.py:82-101`）における `elif len(steam_matches) == 1:` のマルチフォーマット全棄却バグ**:
   - 同一スロットに正当な曲と無関係な曲が衝突した際、82行目で `elif len(steam_matches) == 1:`（Steamタイトルと一致する `tid` が **ちょうど1個だけ** のときのみ救済する）としている。
   - しかし現行アーキテクチャでは **1物理ファイル＝1 `tid`** であるため、WAV+MP3やFLAC+MP3の2フォーマット構成アルバムでは、正当な曲の `steam_matches` が必ず **2個（WAV+MP3）または3個（WAV+FLAC+MP3）** になる（`len(steam_matches) == 2`）！
   - その結果、`len(steam_matches) == 1` が偽となって `retained_tids = set()` が選ばれ、**Steamタイトルと完全一致している本物の曲のWAVとMP3まで諸共すべて棄却** されている（`1075710`, `1761580`, `802640`, `1586580`, `2198580`, `1940600`, `441260` 等で発生）。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/organizer.py` (`_prepare_chunk_payload`: 307〜314行目 / `_simplify_v_album`: 540〜559行目)
```python
        # _prepare_chunk_payload (307-314行目)
        s_chunk = [
            {
                "file_ids": [str(file_id) for file_id in t.get("file_ids", [])],
                "t": t.get("title"),
                "d": t.get("disc", 1),
                "dur": int(t.get("duration_ms", 0) / 1000) if t.get("duration_ms") else None,
            }
            for t in chunk
        ]
```
```python
        # _simplify_v_album (552-558行目)
        for idx, t in enumerate(tracks):
            entry: Dict[str, Any] = {"v_idx": idx, "d": t.get("disc", 1), "n": t.get("track_num"), "t": t.get("title")}
            if source != "STEAM":
                entry["dur"] = int(t.get("duration_ms", 0) / 1000) if t.get("duration_ms") else None
```
- `s_chunk` に `"n": t.get("track_num") or t.get("filename_track")` が無く、`_simplify_v_album` では `if source != "STEAM":` によりSteamスロットから `"dur"` が除外されている。

### 2.2 `src/sst/llm/normalization.py` (`resolve_slot_key_to_v_idx`: 5〜56行目 / `normalize_track_mapping_result`: 62〜107行目)
```python
    fallback_index = value - 1
    if 0 <= fallback_index < len(full_ref_steam):
        return int(full_ref_steam[fallback_index].get("v_idx", fallback_index))

    if 0 <= value < len(full_ref_steam):
        return int(full_ref_steam[value].get("v_idx", value))
```
1. `full_ref_steam` には未充填の部分リスト `unfilled_steam_slots` が渡されるため、`unfilled_steam_slots` が `[v_idx=48 (n=49), v_idx=66 (n=67)]` の2要素しかないときにLLMが `"1"` を出力すると、`fallback_index = 0` で `unfilled_steam_slots[0]`（`v_idx=48`）に化ける。
2. マルチディスクで `"d_n"` 形式（例: `"1_5"`, `"2_1"`）が返された場合の `(d, n)` 解決がなく、複数ディスクに同じ `n` があると `len(direct_matches) > 1` となって `fallback_index` に落ち、常に先頭ディスクへ誤解決される。
3. `normalize_track_mapping_result`（76〜83行目）で `slot_data.get("confidence")` が `0`（または負値）の場合や、`reason` が明確な未割当理由（`"no matching steam slot"`, `"unassigned"`）である場合を除外していない。

### 2.3 `src/sst/llm/assignment_validation.py` (`reject_contradictory_slot_assignments`: 82〜101行目)
```python
        elif len(steam_matches) == 1:
            retained_tids = set(steam_matches)
            rejected_tids = [tid for tid in tids if tid not in retained_tids]
        else:
            retained_tids = set()
            rejected_tids = list(tids)
```
- `steam_matches` に含まれる全 `tid` が同一曲のフォーマットバリアント（正規化タイトルが同一、または再生時間差 `< 3.0s` で全件が対象Steamスロットと一致）である場合でも、`len(steam_matches) >= 2` になると `else:` に落ちて全件棄却される。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/llm/organizer.py` および `src/sst/llm/prompts.py` の修正
1. **`_simplify_v_album`（`organizer.py:552-558`）でSteamスロットにも `"dur"` を保持する**:
   `if source != "STEAM":` の制限を外し、`t.get("duration_ms")` が存在する場合は `source == "STEAM"` でも `"dur": int(t.get("duration_ms", 0) / 1000)` を出力する。
2. **`_prepare_chunk_payload`（`organizer.py:307-314`）でローカルトラックにも `"n"` を保持する**:
   `s_chunk` の各辞書に `"n": t.get("track_num") or t.get("filename_track")`（およびクリーンな `"norm_t": t.get("norm_stem")`）を含める。
3. **`build_mapping_prompt`（`prompts.py:67-115`）の明確化**:
   - スロットキーには **相対順位（1, 2, 3...）ではなく、対象 `STEAM SLOTS` エントリの `"n"`（マルチディスクの場合は `"<d>_<n>"` または `"v_idx"`）をそのまま指定すること** を明記する。
   - 対応するSteamスロットが存在しないファイルは `"slots"` に入れず必ず `"unassigned_files"` に出力することを明記する。

### 3.2 `src/sst/llm/normalization.py` (`resolve_slot_key_to_v_idx` & `normalize_track_mapping_result`) の修正
1. **`normalize_track_mapping_result` における無効スロットの除外**:
   - `slot_data` の `confidence` が数値として存在し `float(confidence) <= 0.0` である場合、または `str(slot_data.get("reason") or "").lower()` が `"no matching steam slot"` 等の未割当を示す場合は、そのスロット割当を採用せず無視する。
2. **`resolve_slot_key_to_v_idx(slot_key, full_ref_steam)` の厳格化**:
   - **Step 1（複合キー `<d>_<n>` / `<d>-<n>` の解決）**:
     `re.match(r"^\s*(\d+)\s*[_-]\s*(\d+)\s*$", normalized_slot_key)` にマッチする場合、`int(track.get("d", 1)) == d` かつ `normalize_key(track.get("n", "")) == normalize_key(n)` を満たす一意な `track.get("v_idx")` を返す。
   - **Step 2（トラック番号 `n` の一意一致）**:
     `normalize_key(track.get("n", "")) == normalized_key` を満たすトラックが `full_ref_steam` 内に **ただ1つ** 存在すればその `v_idx` を返す。
   - **Step 3（`v_idx` の一意一致 — `v_idx=2` 等への対応）**:
     `full_ref_steam` が部分リスト（`len(full_ref_steam)` が元の全スロット数より少ない、または `full_ref_steam[i].get("v_idx") != i` の要素を含む）である場合、`int(track.get("v_idx", -1)) == value`（または `int(track.get("v_idx", -1)) + 1 == value` でかつ `n` とも整合する場合）で一意に一致するスロットがあればその `v_idx` を返す。
   - **Step 4（部分リストに対する `fallback_index = value - 1` の禁止）**:
     `full_ref_steam` が未充填の部分リスト（`any(int(t.get("v_idx", i)) != i for i, t in enumerate(full_ref_steam))`）である場合、または複数ディスクが存在する（`len({int(t.get("d", 1)) for t in full_ref_steam}) > 1`）場合は、**配列添字 `full_ref_steam[value - 1]` / `full_ref_steam[value]` へのフォールバックを一切行わず `None` を返す**（無関係な空きスロットへの誤集約を防止するため）。

### 3.3 `src/sst/llm/assignment_validation.py` (`reject_contradictory_slot_assignments`: 82〜101行目) の修正
- `elif len(steam_matches) == 1:` を以下のように拡張する：
  - `steam_matches` が1件以上存在し（`len(steam_matches) >= 1`）、かつ **`steam_matches` に含まれるすべての `tid` が互いに同一曲のコヒーレントなバリアントである**（すなわち `_are_slot_assignments_coherent(matched_v_idx, steam_matches, ...)` が真、または `steam_matches` 内の正規化タイトル集合が1種類もしくは再生時間差が `< 3.0s` である）場合：
    - `retained_tids = set(steam_matches)` として **`steam_matches` の全フォーマットバリアント（WAV+MP3等）を保持** し、それ以外の矛盾する `tid`（`[tid for tid in tids if tid not in retained_tids]`）のみを `rejected_tids` として棄却する！

---

## 4. 不変条件・禁止事項

- `steam_matches` 内に互いに別曲（タイトルも尺も異なる2つの別トラック）が含まれている真の衝突ケースでは、勝手に片方を採用せず従来通り `retained_tids = set()` として両方棄却すること。
- `resolve_slot_key_to_v_idx` で解決不能なキーを、配列先頭 `full_ref_steam[0]` へフォールバックさせてはならない。

---

## 5. テスト作成指示

`tests/test_differential_alignment.py` および `tests/test_llm_normalization.py` に以下の回帰テストを追加すること。

1. **`test_resolve_slot_key_to_v_idx_does_not_fallback_to_partial_unfilled_list_index`**:
   - **設定**: `unfilled_steam_slots = [{"v_idx": 48, "d": 1, "n": 49, "t": "Millenium Spark"}, {"v_idx": 66, "d": 1, "n": 67, "t": "Hollow"}]`（AppID `1553350` 型）。
   - **検証**:
     - `resolve_slot_key_to_v_idx("49", unfilled_steam_slots)` が `48` を返すこと。
     - `resolve_slot_key_to_v_idx("67", unfilled_steam_slots)` が `66` を返すこと。
     - `resolve_slot_key_to_v_idx("1", unfilled_steam_slots)` および `resolve_slot_key_to_v_idx("2", unfilled_steam_slots)` が `48` や `66` に誤解決されず **`None` を返す** こと。
2. **`test_resolve_slot_key_to_v_idx_resolves_explicit_v_idx_in_single_unfilled_slot`**:
   - **設定**: `unfilled_steam_slots = [{"v_idx": 2, "d": 1, "n": 3, "t": "Trailerblazers"}]`（AppID `2353511` 型）。
   - **検証**: `resolve_slot_key_to_v_idx("3", unfilled_steam_slots)` と `resolve_slot_key_to_v_idx("2", unfilled_steam_slots)` の双方が `2` を返すこと。
3. **`test_reject_contradictory_slot_assignments_retains_multiformat_steam_matches`**:
   - **設定**: スロット `v_idx=23`（`"01840728"`）に対し、正当なWAV（`tid_wav`）とMP3（`tid_mp3`）（ともにタイトル `"01840728"`, duration `120.0s`）に加え、無関係なボーナストラック（`tid_bonus`, タイトル `" Katana ZERO (Ost-Version)"`, duration `195.0s`）が割り当てられた合成データ（AppID `1075710` / `1761580` 型）。
   - **検証**: `reject_contradictory_slot_assignments` 実行後、`tid_bonus` のみが棄却され、正当な **`tid_wav` と `tid_mp3` の両方が保持される** こと。
4. **`test_prepare_chunk_payload_and_simplify_v_album_preserve_track_num_and_steam_duration`**:
   - **検証**: Phase 2 プロンプト用の `s_chunk` に `"n"` が含まれ、`full_ref_steam` に `"dur"` が含まれること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_differential_alignment.py tests/test_llm_normalization.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

