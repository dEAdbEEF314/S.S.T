# 修正指示書 04: LLM通信エラー（`APIConnectionError`）時の誤フォールバック防止と番号のみマッピングの廃止

## 1. 背景と問題の概要

バッチ処理中にLLMバックエンド（Ollama等）への通信断（`APIConnectionError` / `ConnectionError`）が発生した際、現行の `identity.py` および `organizer.py` がこれを「LLM応答のトークン上限切断（Truncation）」と誤認して `STEAM-TRUSTフォールバック` や `_recover_prematch_fallback_slots` を発動させている。

さらに `_recover_prematch_fallback_slots` には **「タイトルが全く一致しないにもかかわらずトラック番号だけでSteamスロットに割り当てる」** という仕様違反（[`docs/METADATA_SOURCE_SPEC.md`](../METADATA_SOURCE_SPEC.md) §7.1 違反）および **「同一スロットの複数ファイル（フォーマット違い等）を上書き消去する」** バグが存在し、**Review行き32件中10件の原因**となっている。

### 発生している現象（実データ例）
- **0始まり（`00_...`）のローカルファイルが1曲ずつズレて別曲タイトルに上書きされた3件**:
  - **AppID `4206020` (Emerald Blue Soundtrack)**: ローカルファイルは `0. REBEL.mp3`, `1. THE FINAL STAND (New Tokyo).mp3`, ..., `7. FAINT OF HEART (End).mp3` の0始まり8曲。Steamスロットは `1: Rebal`, `2: The Final Stand`, ..., `8: Faint Of Heart` の1始まり8曲。LLM通信断時に `_recover_prematch_fallback_slots` の `Number match fallback (#1)`〜`(#7)` が発動し、**`1. THE FINAL STAND` に `Rebal` のタイトルを、`2. CONTEMPLATION` に `The Final Stand` のタイトルを付与して1曲ずつズラしてマッピング**し、`0. REBEL.mp3` を未割当にした。
  - **AppID `2943720` (カルトに厳しいギャル Soundtrack)**: 同様に `00_OMOHIDE LOOP.mp3` が外れ、`01_SHIKATANAKATTA NO TSUMI.mp3` が Steam Slot `#1 (00_OMOHIDE LOOP)` に番号フォールバックで誤割当された。
  - **AppID `2339210` (HAZAMA_QUEEN Soundtrack)**: 同様に `00_EP1.mp3` が外れ、`01_EP2.mp3` が Steam Slot `#1 (EP1_bhaskara)` に番号フォールバックで誤割当された。
- **Phase 1 は `STEAM-TRUSTフォールバック` で通過したが Phase 2 で全滅した3件**:
  - **AppID `905290` (Alwa's Awakening)** / **AppID `1593020` (Milk inside a bag of milk)** / **AppID `2716920` (Kevin 1997-2077)**: Phase 1の通信断を「LLM応答切断」として `album_confidence=100` に引き上げた後、Phase 2でも通信断が発生し、`Track Mapping Failure (No valid slot assignments): SYSTEM: STEAM-TRUSTフォールバック` という誤解を招く診断メッセージでReview行きとなった。
- **Phase 1 で通信断により即座に失敗した4件**:
  - **AppID `467870`**, **`584382`**, **`2455450`**, **`3282950`**。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/identity.py` (`resolve_album_identity`: 78〜105行目)
```python
    if not global_res:
        if steam_count > 0 and steam_count == local_count:
            logger.warning(
                "[%s] Identity LLM call failed/truncated. Activating STEAM-TRUST fallback (%s tracks).",
                app_id,
                steam_count,
            )
            global_res = {
                "album_confidence": 100,
                ...
                "confidence_reason": "SYSTEM: STEAM-TRUSTフォールバック (LLM応答切断のため構造一致を採用)",
```
1. `global_log` の失敗原因が「応答切断（truncation）」なのか「バックエンド接続不能（`APIConnectionError` / `Connection refused` / `Connect call failed` 等）」なのかを判定していない。バックエンド自体がダウンしている状態で Phase 1 を成功扱いにすると、直後の Phase 2 でも確実に通信失敗して時間を浪費し、不正確な監査原因（`TRACK_MAPPING_FAILURE`）を残す。
2. 79行目の構造一致条件が `steam_count == local_count` のみになっており、124行目で使用している `unique_local_slots`（WAV+MP3等のマルチフォーマット時にユニークスロット数で比較するロジック）が79行目には適用されていない。

### 2.2 `src/sst/llm/organizer.py` (`_recover_prematch_fallback_slots` & `_process_track_mapping_segment`: 323〜348行目, 415〜420行目)
```python
    @staticmethod
    def _recover_prematch_fallback_slots(
        chunk: List[Dict[str, Any]],
        prematch_map: Optional[Dict[str, Any]],
        full_ref_steam: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback_slots = {}
        for track in chunk:
            for fid in track.get("file_ids", []):
                fid_str = str(fid)
                pm = prematch_map.get(fid_str) if prematch_map else None
                if pm and (pm.acoustid_steam_slot or pm.mbz_search_steam_slot or pm.override_track):
                    target_slot = str(pm.acoustid_steam_slot or pm.mbz_search_steam_slot or pm.override_track)
                    fallback_slots[target_slot] = {
                        "files": [fid_str],
                        "confidence": 0.95,
                        "reason": f"SYSTEM: Prematch fallback ({pm.evidence[0] if pm.evidence else 'rule'})",
                    }
                else:
                    t_num = track.get("n") or track.get("track_num")
                    if t_num and str(t_num).isdigit() and full_ref_steam and 0 < int(t_num) <= len(full_ref_steam):
                        fallback_slots[str(t_num)] = {
                            "files": [fid_str],
                            "confidence": 0.90,
                            "reason": f"SYSTEM: Number match fallback (#{t_num})",
                        }
        return fallback_slots
```
1. **341〜347行目（タイトル未検証の番号のみフォールバック）**:
   ローカルトラックの番号 `t_num` が `1..len(full_ref_steam)` の範囲にあれば、**Steamスロット側のタイトルとローカルトラックのタイトルが全く異なっていても無条件で割り当てている**。
2. **335行目・343行目（辞書の上書きバグ）**:
   `fallback_slots[target_slot] = {"files": [fid_str], ...}` と毎回上書き代入しているため、1つのトラックに複数 `file_ids` がある場合や複数フォーマットがある場合に、最後の1ファイル以外がすべて消去される。
3. **333行目（未検証 `override_track` の採用）**:
   `pm.is_deterministic` が `False` の場合でも、`pm.override_track`（番号のみ一致したMBZやFPのトラック番号）が存在すると無条件で採用してしまう。

---

## 3. 具体的な修正仕様

### 3.1 接続障害判定ヘルパーの追加と `src/sst/llm/identity.py` の修正
1. `global_log`（または `track_log`）が通信・接続エラーであるかを判定するヘルパー関数 `_is_connection_error_log(log_data: Optional[Dict[str, Any]]) -> bool` を実装する：
   ```python
   def is_connection_error_log(log_data: Optional[Dict[str, Any]]) -> bool:
       if not isinstance(log_data, dict):
           return False
       err = str(log_data.get("error") or "").lower()
       connection_markers = (
           "apiconnectionerror",
           "cannot connect to host",
           "connect call failed",
           "connection refused",
           "connectionerror",
           "name or service not known",
       )
       return any(marker in err for marker in connection_markers)
   ```
2. `resolve_album_identity`（`src/sst/llm/identity.py`）において：
   - `unique_local_slots` の計算（現在109〜121行目にある処理）を `if not global_res:` の前に移動する。
   - `if not global_res:` の際、`is_connection_error_log(global_log)` が `True` であれば **`STEAM-TRUSTフォールバック` を発動させず**、即座に `return None, {"phase1_res": None, "phase1_log": global_log}` を返して明確に `LLM Failure` として早期リターンさせる。
   - 接続エラーではなく（応答切断・JSONパース失敗等で）、かつ `steam_count > 0 and (steam_count == local_count or steam_count == unique_local_slots)` を満たす場合にのみ `STEAM-TRUSTフォールバック` を適用する。

### 3.2 `src/sst/llm/organizer.py` (`_recover_prematch_fallback_slots` & `_process_track_mapping_segment`) の修正
1. `_process_track_mapping_segment`（415行目付近）において、`is_connection_error_log(track_log)` が `True` の場合は、不完全なフォールバックを行わず `track_res = {}` とし、ログに通信エラーであることを明記する。
2. `_recover_prematch_fallback_slots` を以下のように修正する：
   - **タイトル整合性の必須化**:
     `assignment_validation.py` の `titles_are_compatible(local_title, steam_title)`（または `TrackManager.normalize_title` による一致・包含判定）を用い、対象となる Steam スロット（`disc` と `number` が一致するスロット）のタイトルとローカルトラックのタイトル（`track.get("title") or track.get("t") or track.get("local_key", ("", ""))[1]`）が整合する場合にのみフォールバック採用する。
     - `0. REBEL.mp3` / `1. THE FINAL STAND.mp3` vs Slot `#1 Rebal` のようにタイトルが不一致の番号フォールバックは**絶対に採用しない**。
   - **複数 `file_ids` の保持（上書き防止）**:
     `fallback_slots` への登録時は上書きではなく `setdefault` で `"files"` リストに追加する：
     ```python
     slot_entry = fallback_slots.setdefault(
         target_slot,
         {
             "files": [],
             "confidence": confidence,
             "reason": reason,
         },
     )
     if fid_str not in slot_entry["files"]:
         slot_entry["files"].append(fid_str)
     ```

---

## 4. 不変条件・禁止事項

- 既存の切断フォールバックテスト（`test_organizer_truncation_prematch_fallback` および `test_organizer_identity_truncation_steam_trust_fallback`）は、「応答切断（`response truncated by backend`）」かつ「タイトルが一致（`What's wrong?` vs `What's wrong!`、`Track i` vs `Track i`）」するケースであるため、引き続きパスさせること。
- LLM接続障害時にタイトル未検証の番号一致だけでスロットを埋め、誤った曲名タグを付与することを厳禁とする。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下のテストを追加すること。

1. **`test_identity_does_not_trigger_steam_trust_on_api_connection_error`**:
   - **設定**: `organizer._call_llm` が `(None, {"error": "litellm.APIConnectionError: OllamaException - Cannot connect to host localhost:11434 [Connect call failed]"})` を返すようにモックする。
   - **検証**: `organizer.align_slots(...)` が `({}, {"phase1_res": None, "phase1_log": ...})` を返し、`STEAM-TRUSTフォールバック` が誤発動しないこと。
2. **`test_recover_prematch_fallback_slots_rejects_mismatched_titles_and_preserves_multiple_files`**:
   - **設定**:
     - ケースA（AppID `4206020` 再現）: Steam Slot `#1` が `"Rebal"`、Slot `#2` が `"The Final Stand"` に対し、ローカルトラック `n=0, title="0. REBEL"` と `n=1, title="1. THE FINAL STAND"` を `_recover_prematch_fallback_slots` に渡す。
     - ケースB（複数ファイル保持）: ローカルトラック `n=1, title="Main Theme", file_ids=["wav1", "mp31"]` と Steam Slot `#1 "Main Theme"` を渡す。
   - **検証**:
     - ケースAでは `n=1 ("1. THE FINAL STAND")` が Slot `"1" ("Rebal")` にフォールバック割当されないこと（戻り値が `{}` であること）。
     - ケースBでは `fallback_slots["1"]["files"] == ["wav1", "mp31"]` となり、2ファイルとも保持されること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_degraded_prompt.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。
