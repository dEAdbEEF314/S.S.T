# 指示書 01: 多言語同フォーマットバリアント（FLAC/WAV）のスロット競合誤判定防止

## 1. 課題と背景

### 1.1 現象
Capcom Arcade Stadium / Capcom Arcade 2nd Stadium Mini-Album シリーズ 15 作品（`1611240` 他）およびゴシックは魔法乙女（`1971340`）において、本編 Steam スロットが 100% 充足（adopted == expected）し重複や未割当も 0 件であるにもかかわらず、`[Slot Conflict Candidates (1)]` または `[Slot Conflict Candidates (18)]` が発行されて Review 送りとなっていた。

### 1.2 根本原因
- これらのアルバムは同一フォルダ内に「日本語版音源」と「英語版音源」が両方同一フォーマット（FLAC 同士、または WAV 同士）で収録されている。
- システムは Steam 公式タイトル（日本語）に従い、日本語 FLAC/WAV を本編採用（`adopted_files`）として正しく選定している。
- しかし、`src/sst/processing/file_selection.py` の `select_slot_conflict_candidates` において、同一曲バリアントのスキップ条件に `adopted_formats.isdisjoint(rec_formats)` が含まれていたため、採用音源と候補音源が同一フォーマット（例: 双方とも FLAC）である場合、トラック番号・再生時間が完全に一致する同一曲の英語音源であっても `slot_conflict` として `review_candidates` に抽出され、`validator.py` で Review 判定となっていた。

---

## 2. 是正仕様

### 2.1 `select_slot_conflict_candidates` の改修 (`src/sst/processing/file_selection.py`)
1. 引数に `steam_meta: Optional[SteamMetadata] = None` を追加。
2. 同一スロット番号（`same_slot_num`）かつ再生時間差 1.5 秒以下（`dur_diff <= 1.5s`）を満たす場合、フォーマットが同一であっても、アルバム内の他スロットとタイトル衝突がない（`not has_cross_slot_conflict`）限り、正当な同一曲多言語バリアントとして `slot_conflict` から除外（`continue`）する。
3. 他スロットタイトル衝突（クロススロット誤割当ガード）の厳格検査：
   - `steam_meta.store_tracklist` がある場合、自スロット以外の全 Steam スロットのタイトル（正規化後）と候補タイトル（`title`、`norm_stem`、埋め込みタイトル）を照合。
   - `adopted_files` に存在する自スロット以外の全採用タイトルとも照合。
   - 他スロットと一致する場合は `has_cross_slot_conflict = True` となり、絶対にスキップせず `slot_conflict` として隔離を維持。

### 2.2 呼び出し元の改修 (`src/sst/processing/track_batch.py`)
`track_batch.py` の `select_slot_conflict_candidates` 呼び出し箇所で `steam_meta=steam_meta` を渡すよう更新。

---

## 3. 安全境界 (Safety Boundary)

1. **番号不一致時の保護**: トラック番号が異なるファイル（`same_slot_num == False`）は本除外の対象外。
2. **再生時間乖離時の保護**: 再生時間差が 1.5 秒を超えるファイル（`dur_diff > 1.5s`）は本除外の対象外。
3. **他スロット重複時の保護**: 候補タイトルがアルバム内の他スロットタイトルと一致する場合はクロススロット衝突として必ず `slot_conflict` に保持。
4. **本編スロット充足の不変**: 本編 `adopted_files` の最上位フォーマット選定・Steam 公式タイトル保持は変更しない。

