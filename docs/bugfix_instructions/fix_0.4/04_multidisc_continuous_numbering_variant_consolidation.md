# 修正指示書 04: フラットフォルダ通し連番におけるマルチディスク兄弟バリアント統合

## 1. 背景と課題

AppID `1879310` (TCSTRIKERS4) において、単一フォルダ（フラット構成）内に Disc 1 (1〜19) と Disc 2 (20〜32) の楽曲が MP3 と WAV の両形式で存在していた。
- 前段の整列処理により、Disc 2 の MP3（例: `20. xxx.mp3`）は Steam スロット `(2, 20)` に正しく割り当てられた。
- しかし、同居する兄弟ファイルである WAV（`20. xxx.wav`）をバリアント統合する際、フラットフォルダ由来で WAV の推測 disc が `1` となっていたため、`slot_key[0] != disc`（`2 != 1`）のガード条件により除外され、未割当ファイルとして残留してReview送りとなった。

## 2. 解決方針

1. **同一トラック番号・異フォーマット・同一ステムの兄弟バリアント救済**:
   - `src/sst/processing/slot_variants.py` の `build_slot_variant_index` において、`same_track_number`（推測トラック番号とスロットトラック番号の一致）を判定する。
   - `same_track_number` かつ異フォーマット（WAV vs MP3 等）かつ同一ファイル名ステム（または高類似度）かつ尺整合（±2.0秒以内）である兄弟ファイルの場合、推測 disc 番号が異なっていても同一楽曲の別フォーマットバリアントと判定し、スロットへの統合を許可する。

## 3. 実装詳細

### `src/sst/processing/slot_variants.py`
- `same_track_number = (inferred_track is not None and str(inferred_track) == str(slot_key[1]))` を定義。
- `is_sibling_stem_match` に `(same_slot_number or same_track_number)` を適用。
- スロット一致条件を `if is_sibling_stem_match and (slot_key[0] == disc or same_track_number):` に拡張。

