# 修正指示書 02: `resolve_duplicate_mappings` における正常スロットの強制退去・上書き破壊バグの修正

## 1. 背景と問題の概要

`src/sst/processing/duplicate_mappings.py` の `resolve_duplicate_mappings`（特に `_resolve_disc_title_matches`）において、同一 `v_idx` に複数の `tid` が残った際、**すでにその `v_idx` に正しく対応している本物のトラックまでも `if s_idx != v_idx:` という条件によって別スロット `s_idx` へ強制移動（退去）させ、さらに移動先 `s_idx` にあった正常なトラックを上書き破壊・スワップさせる致命的なロジック欠陥**が存在する。

このバグにより、決定論的プレマッチで **全スロットが100%正確に確定していたアルバム** が後段の `resolve_duplicate_mappings` で自ら破壊され、**Review行き3件（`916190`, `3449720`, `467870`）の直接原因**となっている。

### 発生している現象（実データ例）
1. **AppID `916190` (CrossCode Original Soundtrack)**:
   - 全64スロット中64スロットが決定論的プレマッチで100%確定（`alignment_slots=64, conf=100%`）。
   - ルートとサブフォルダに同一の `.mp3` が2セット（計128ファイル）存在したため、各 `v_idx` に2つずつ `tid` が入った状態で `_resolve_disc_title_matches` が実行された。
   - `_resolve_disc_title_matches` の206行目 `if s_idx != v_idx:` により、**自身のスロット `v_idx` と完全一致（`sim=1.0`）しているにもかかわらず、`s_idx == v_idx` がスキップされ、類似度 `>= 0.80` または前方一致する「別のスロット `s_idx`」へ強制移動**された！
   - その結果：
     - `07 Battle 1.mp3`（本来 `1_7`）が `1_22`（`Battle 2`）へ移動し、`22 Battle 2.mp3`（本来 `1_22`）が `1_7`（`Battle 1`）へ移動して **曲名が逆転（スワップ）**。
     - `10 Challenge 1.mp3` と `17 Challenge 2.mp3` も同様に **スワップ**。
     - Disc 2の `41 Battle 3`, `47 Escape Again`, `53 Temple of the Lake` が Disc 1の類似タイトルスロットへ上書き移動され、**3スロットが消滅（`61/64`）**してReview行き。
2. **AppID `3449720` (都市伝説解体センター オリジナルサウンドトラック)**:
   - 全32スロット中32スロットが決定論的プレマッチで100%確定（`alignment_slots=32, conf=100%`）。
   - Track 32 `32.KIKIKAITAI`（`v_idx=31`）に `.wav` と `.mp3` の2つの `tid` があった際、`_resolve_disc_title_matches` が実行された。
   - ローカルタイトル `"kikikaitai"` に対し、Slot 20（`v_idx=19`）の `"kikikaitai ed edit"` が `norm_steam.startswith(norm_local)` により `sim = 1.0` と判定され、かつ `if s_idx != v_idx:` によって本来正しかった `s_idx = 31`（`"kikikaitai"` 完全一致）がスキップされ、**Track 32のファイルがSlot 20へ強制移動されてSlot 32が空になり欠損（`31/32`）**した。
3. **AppID `467870` (MINUS ZERO - Original Sound Track)**:
   - 全14スロット中14スロットがアライメントで確定（`alignment_slots=14, conf=100%`）。
   - 各スロットにWAVとMP3が割り当てられた後、`_resolve_disc_title_matches` が発動し：
     - `07_Ending`（本来 `1_7`）を前方一致で `1_14`（`Ending Long MIX`）へ移動して `1_7` を空にし、
     - `09_NoGood 01 Long MIX` と `10_NoGood 02 Long MIX` をファジーマッチ（`sim >= 0.80`）で互いに逆のスロットへスワップさせ、
     - `11_MinusZero Full MIX`（本来 `1_11`）を前方一致で `1_12`（`MinusZero Full MIX 2013`）へ移動して `1_11` を空にした結果、**5スロット欠損（`9/14`）かつ4件の `Official Title Mismatch`** を引き起こしてReview行き。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/processing/duplicate_mappings.py` (`_resolve_disc_title_matches`: 166〜224行目)
```python
        best_match = None
        if candidates_same_disc:
            candidates_same_disc.sort(key=lambda x: x[2], reverse=True)
            for s_idx, s_name, sim in candidates_same_disc:
                if s_idx != v_idx:
                    best_match = (s_idx, s_name, sim, False)
                    break
        elif len(candidates_other_disc) == 1:
            s_idx, s_name, sim = candidates_other_disc[0]
            if s_idx != v_idx:
                best_match = (s_idx, s_name, sim, True)
```
1. **正しいスロットに居るトラックまで移動対象にしている**:
   `tids` の中に、現在の `v_idx`（`store_tracks[v_idx]`）とタイトルが完全一致（またはトラック番号も一致）する正当な `tid` が含まれているにもかかわらず、すべての `tid` に対して `if s_idx != v_idx:` で **現在のスロット `v_idx` 以外の候補** を探して移動させている。
2. **`_match_titles`（109〜123行目）が前方一致（`startswith`）とファジー一致（`>= 0.80`）を区別せず移動に使っている**:
   - `norm_steam.startswith(norm_local)` が `sim = 1.0` を返すため、`"kikikaitai"`（Slot 32）が `"kikikaitai ed edit"`（Slot 20）に `sim = 1.0` でマッチし、`"ending"`（Slot 7）が `"ending long mix"`（Slot 14）に `sim = 1.0` でマッチする。
   - また `"battle 1"` と `"battle 2"`、`"nogood 01 long mix"` と `"nogood 02 long mix"` は末尾の番号だけが異なる別曲であるにもかかわらず、`SequenceMatcher` の類似度が `>= 0.80` となるため、`if s_idx != v_idx:` と組み合わさることで **ナンバリング違いの別曲スロットへ強制スワップ** される。
3. **移動先スロット `s_idx` の占有状態を確認していない**:
   移動先 `s_idx` にすでにそのスロット本来の正当なトラックが割り当てられていても、無条件に `final_metadata[tid]["matched_v_idx"] = s_idx` で突っ込み、元のスロット `v_idx` を空にしている。

---

## 3. 具体的な修正仕様

### 3.1 `_resolve_disc_title_matches` (`src/sst/processing/duplicate_mappings.py`) の抜本修正
1. **現在のスロット `v_idx` に正当に属する `tid` の保護（アンカー固定）**:
   - `current_steam_track = store_tracks[v_idx]` の正規化タイトル `current_norm_steam`（および `(current_disc, current_track_num)`）を取得する。
   - `tids` のうち、`norm_local == current_norm_steam`（完全一致）であるか、またはローカルの `(disc, t_num_val)` が `(current_disc, current_track_num)` と一致しかつ `_match_titles(norm_local, current_norm_steam)` が真である `tid` は、**現在のスロット `v_idx` の正当な所有者（アンカー）** であるため、**絶対に他のスロット `s_idx != v_idx` へ移動させてはならない**。
   - もし `tids` の **すべて** が現在のスロット `v_idx` の正当な所有者（例: 同一曲のフォーマット違いやサブフォルダ重複）である場合は、1つも別スロットへ移動させずそのまま返す（最高優先度の1つが `v_idx` に採用される）。
2. **本当に別スロットの曲（誤割当された衝突トラック）のみを移動対象とする**:
   - 現在のスロット `v_idx` のタイトル `current_norm_steam` と一致しない `tid`（または `v_idx` よりも別のスロット `s_idx` と **完全一致 `norm_local == norm_steam`** する `tid`）のみを再配置候補とする。
3. **移動先スロット `s_idx` の安全性条件**:
   - 移動先 `s_idx` は、以下の条件を満たす場合にのみ選択できる：
     - **完全一致優先**: `norm_local == norm_steam`（または空白無視完全一致）であること。
     - もし完全一致ではなく前方一致やファジー一致（`>= 0.80`）しか存在しない場合は：
       - **ナンバリング矛盾の禁止**: `norm_local` と `norm_steam` に含まれる数値トークン集合（`re.findall(r'\d+', ...)`）が異なる場合（例: `"battle 1"` vs `"battle 2"`、`"nogood 1 long mix"` vs `"nogood 2 long mix"`、`"kikikaitai"` vs `"kikikaitai 2013"`）は別曲であるためマッチとみなさない。
       - **バージョン接尾辞矛盾の禁止**: 一方にのみ `"long"`, `"short"`, `"edit"`, `"extended"`, `"full"`, `"ver"`, `"mix"`, `"remix"`, `"chiptuned"`, `"demo"`, `"inst"`, `"instrumental"` 等のバージョン識別語が含まれる場合（例: `"kikikaitai"` vs `"kikikaitai ed edit"`, `"ending"` vs `"ending long mix"`）は別スロットへ移動させてはならない。
     - **占有済みスロットへの侵入禁止**: 移動先 `s_idx` が、すでに `s_idx` とタイトル完全一致する別のトラックによって占有されている場合は、`s_idx` へ移動させてはならない（未占有の空きスロット、または相互に誤配置されたスロットへのみ移動を許可する）。

### 3.2 `_resolve_sequential_track_duplicates` (`src/sst/processing/duplicate_mappings.py`: 227〜270行目) の安全ガード
- `next_name` と `base_name` の比較（244行目）においても、`_match_titles` の前方一致やファジー一致ではなく **`base_name == next_name`（完全一致する同名連続トラック、例: `"Untitled"`, `"Untitled"`）** の場合のみシーケンス展開を行うこと（`"Ending"` と `"Ending Long MIX"` のような別曲を同名シーケンスと誤認しないため）。

---

## 4. 不変条件・禁止事項

- 決定論的プレマッチで `(disc, track_num)` およびタイトル一致により確定したトラックを、`resolve_duplicate_mappings` が別スロットへ退去させて元のスロットを欠損（`Steam Slots Missing`）させてはならない。
- `"Battle 1"` と `"Battle 2"` のように番号が異なるトラックをファジーマッチで同一視してはならない。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py`（または `tests/test_differential_alignment.py`）に以下の回帰テストを追加すること。

1. **`test_resolve_duplicate_mappings_never_evicts_exact_slot_owner_to_fuzzy_or_prefix_slot`**:
   - **設定**:
     - Steamトラックリスト: Slot 1 (`"Battle 1"`), Slot 2 (`"Battle 2"`), Slot 3 (`"KIKIKAITAI (ED edit)"`), Slot 4 (`"KIKIKAITAI"`), Slot 5 (`"Ending"`), Slot 6 (`"Ending Long MIX"`)。
     - 各スロットに正しく2つずつの `tid`（例: サブフォルダ重複や未統合バリアント）が割り当てられている状態（AppID `916190` / `3449720` / `467870` 型）。
   - **検証**:
     - `resolve_duplicate_mappings` を実行した後、Slot 1〜6のすべてに元の正しい曲の `matched_v_idx`（`0`〜`5`）が維持されていること。
     - `"Battle 1"` が `"Battle 2"`（`v_idx=1`）へ移動したり、`"KIKIKAITAI"`（`v_idx=3`）が `"KIKIKAITAI (ED edit)"`（`v_idx=2`）へ移動したり、`"Ending"`（`v_idx=4`）が `"Ending Long MIX"`（`v_idx=5`）へ移動して元のスロットが空になる現象が一切発生しないこと。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_differential_alignment.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

