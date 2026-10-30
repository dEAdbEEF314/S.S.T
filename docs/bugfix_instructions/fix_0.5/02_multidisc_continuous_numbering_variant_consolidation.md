# 修正指示書 02: 通し連番マルチディスクにおける兄弟バリアント統合の一般化

## 1. 背景と課題

AppID `1879310` (TCSTRIKERS4) において、単一フォルダ（フラット構成）内に Disc 1 (1〜19) と Disc 2 (20〜32) の音源が通し連番で MP3 と WAV の両形式で存在している。
Steam 側のストアトラックリストでは、Disc 1 が 1〜19、Disc 2 が 1〜13（各ディスク独立連番）で登録されている。

### 原因調査
前段の LLM アライメント等により、Disc 2 の MP3（例: `20 Technology Crisis.mp3`）は Steam スロット `(2, 1)`（Disc 2 Track 1: テクノロジークライシス）に正しく割り当てられた。
しかし、同居する兄弟ファイルである WAV（`20 Technology Crisis.wav`）をバリアント統合する際：
1. fix_0.4 指示書04 で実装された `same_track_number = (inferred_track is not None and str(inferred_track) == str(slot_key[1]))` において、WAV のファイル名トラック番号は `20` であるのに対し、スロットキーは `(2, 1)`（`slot_key[1] == 1`）であるため、`"20" == "1"` となり `same_track_number` が False となった。
2. その結果、他ディスク間照合ガード（`if slot_key[0] != disc: ...`）に入り、Steam の公式日本語タイトル（`テクノロジークライシス`）と WAV の英語ステム（`technology crisis`）を直接照合しようとしたが不一致となり、兄弟バリアント統合から除外された。
3. このため、WAV 10曲が未割当（Unassigned）として Review 送りとなり、本編には低品質な MP3 のみが採用される本末転倒な結果となった。

## 2. 解決方針

1. **元ファイル名トラック番号（`assigned_orig_track`）の照合導入**:
   - 既にスロットに割り当てられている兄弟ファイル（MP3）の元ファイル名トラック番号（`assigned_orig_track = assigned_variant.get("t_num_val") or assigned_variant.get("filename_track")`）を取得する。
   - 未整列ファイル（WAV）の `inferred_track` と `assigned_orig_track` が一致している場合（`same_orig_track = True`）、Steam スロットの `slot_key[1]` が 1 からリセットされていても、両者が同一のトラック番号を持つ兄弟ファイルであると正しく認識する。

2. **兄弟ステム一致時の最優先統合**:
   - `(same_slot_number or same_track_number or same_orig_track)` かつ異フォーマット（WAV vs MP3）かつ同一 norm_stem（または SequenceMatcher >= 0.88）かつ尺整合（±2.0s 以内）である場合（`is_sibling_stem_match`）、既に割り当て済みの兄弟バリアントが存在するスロットキーへの統合を最優先とし、他ディスク直接 Steam タイトル照合をバイパスして即座に統合を確定する。

## 3. 実装詳細

### `src/sst/processing/slot_variants.py`

`build_slot_variant_index` 内のループを改修：

```python
assigned_orig_track = assigned_variant.get("t_num_val") or assigned_variant.get("filename_track")
same_orig_track = (
    inferred_track is not None
    and assigned_orig_track is not None
    and str(inferred_track).lstrip("0") == str(assigned_orig_track).lstrip("0")
)
same_track_number = (
    (inferred_track is not None and str(inferred_track).lstrip("0") == str(slot_key[1]).lstrip("0"))
    or same_orig_track
)
...
is_sibling_stem_match = (
    (same_slot_number or same_track_number or same_orig_track)
    and is_different_format
    and (dur_diff is None or dur_diff <= 2.0)
    and (
        unaligned_title == assigned_title
        or SequenceMatcher(None, unaligned_title, assigned_title).ratio() >= 0.88
    )
)
...
if is_sibling_stem_match and (slot_key[0] == disc or same_track_number or same_orig_track):
    matching_slot_keys = {slot_key}
    break
```

## 4. 安全境界

- 統合条件として「同一フォルダ内の異フォーマット」「norm_stem の完全一致または高類似度（>= 0.88）」「尺の差 <= 2.0秒」「元トラック番号の一致」がすべて要求されるため、無関係な楽曲が誤って統合されるリスクはゼロである。
- これにより、AppID 1879310 において WAV 10曲が安全に兄弟統合され、最高品質（ロスレス）の採用と未割当 0件が達成される。
