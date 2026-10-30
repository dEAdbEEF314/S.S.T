# 修正指示書 02: 個別タイポ置換ハードコードの根絶と汎用判定への統合

## 1. 背景と課題

過去の修正作業（`fix_0.3` 等）において、特定AppID（例: AppID `1167720` 等）の特定タイトルにあるタイポ（`artifical`）を吸収するために、以下のハードコードが混入していた：
- `src/sst/track_grouper.py:90`: `stem = stem.replace("artifical", "artificial")`
- `src/sst/llm/prematch.py:258`: `l_norm_fixed = l_norm.replace("artifical", "artificial")`

これらは個別事案に特化した場当たり的な修正であり、設計原則「個別事案向けハードコードの禁止」に抵触するアンチパターンである。本来、`artifical` と `artificial` は既存のレーベンシュタイン距離／類似度照合（`SequenceMatcher >= 0.88`、類似度約0.90）によって汎用的に吸収可能である。

また、AppID `2943720` 等において `A_25_Oligarch_s Dream.mp3` のような「単一英字ディスク/セクション記号＋アンダースコア＋トラック番号」のファイル名パターンが存在したが、`track_grouper.py` のアンダースコア直前プレフィックス検証で `A` がトラック識別キーワード（track, bgm等）以外として弾かれ、トラック番号が抽出できない問題があった。

## 2. 解決方針

1. **個別タイポ置換の完全削除**:
   - `src/sst/track_grouper.py` および `src/sst/llm/prematch.py` から `stem.replace("artifical", "artificial")` の記述を完全に削除する。
   - タイポの吸収は `SequenceMatcher.ratio() >= 0.88` の汎用ロジックに委ねる。
2. **単一文字プレフィックスの許容**:
   - `src/sst/track_grouper.py` において、アンダースコア直前のプレフィックス単語が1文字の英字（`A_`, `B_`, `C_` 等のディスク/セクション記号）である場合、正規のトラック番号前置子として許容し、トラック番号を正しく抽出する。

## 3. 実装詳細

### `src/sst/track_grouper.py`
- Line 90 の `stem = stem.replace("artifical", "artificial")` を削除。
- Line 274 付近の `prefix_word` チェックに `or (len(prefix_word) == 1 and prefix_word.isalpha())` を追加。

### `src/sst/llm/prematch.py`
- Line 258 付近の `l_norm_fixed` 置換コードを削除し、後続の `SequenceMatcher` に一本化。

