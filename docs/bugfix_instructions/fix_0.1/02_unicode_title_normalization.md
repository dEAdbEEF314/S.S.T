# 修正指示書 02: 非ASCII文字（日本語・韓国語・中国語・キリル文字等）のタイトル正規化保持と空文字フォールバック誤爆の修正

## 1. 背景と問題の概要

現在、`TrackManager.normalize_title` および `MetadataBuilder.build_tag_map` のファジー照合処理が ASCII 英数字（`a-zA-Z0-9`）以外のすべての文字を空白に置換（消去）しているため、日本語・韓国語・中国語・キリル文字・アクセント付きラテン文字を含む曲名がすべて空文字列 `""` または断片的な英数字（`"1"`, `"feat"` 等）に破壊されている。

### 発生している現象（実データ例）
- **AppID `689920` (1bitHeart Original Soundtrack)**:
  - Steamトラックリスト `v_idx=7`（Track 8）のタイトルは `"無色不透明(feat.鏡音リン)"` であり、`re.sub(r'[^a-zA-Z0-9]', ' ', ...)` を通すと日本語がすべて消えて **`"feat"`** の4文字だけになる。
  - ローカルの未割当ボーナストラック `"1BitHeart(feat.KagamineRin)"` および `"1BitHeart(feat.minx)"`（正規化後 `"1bitheart feat kagaminerin"` / `"1bitheart feat minx"`）に対して `MetadataBuilder.build_tag_map` がフォールバック補完を行う際、先頭の `"1bitheart"` がトラック番号除去正規表現 `^(\d+[\s._-]+)+` に誤って一部削られるか、または他の日本語トラックの `norm_t_title`（`""` や `"feat"`）に対して `norm_t_title == fuzzy_clean_title` / `fuzzy_clean_title.startswith(norm_t_title + " ")` が成立し、**2曲とも `Track 8: 無色不透明(feat.鏡音リン)` に上書きされて重複エラー（`Duplicates (2)`）でReview行き**となった。
- **AppID `1851920` (Milk outside a bag of milk outside a bag of milk Soundtrack)**:
  - ローカルファイルのタイトル・ファイル名がキリル文字（`01. Тёмная комната.mp3`, `02. Ключи.mp3` 等）であるため、`TrackManager.normalize_title` の結果が全曲 `""`（空文字列）となり、`clean_title` が `"::file_id"` のみになってタイトル比較・残差確定が機能せずReview行きとなった。
- **決定論的プレマッチ等の空文字すり抜け**:
  - `src/sst/llm/prematch.py` の136行目に `if not s_title or not l_title or ...` があるため、Steamタイトルが日本語のみ（`s_title == ""`）の場合、実際の曲名が全く異なっていてもトラック番号だけで無条件にタイトル一致（`deterministic_number_and_title`）と誤判定される。
  - 逆に `slot_variants.py`、`unassigned.py`、`assignment_validation.py` では `if not left_title or not right_title: return False` となっているため、日本語のみのタイトル（例: `"いつかあの場所で"`）同士のフォーマット統合（WAV+MP3）や決定論的残差確定が一切機能しない。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/track_grouper.py` (`TrackManager.normalize_title`: 77〜85行目)
```python
    @staticmethod
    def normalize_title(stem: str) -> str:
        stem = html.unescape(stem or "")
        stem = re.sub(r'^(\d+[\s._-]+)+', '', stem)
        stem = re.sub(r'[\s(\[]+(?:aiff|mp3|flac|wav|lossless|high[\s-]*res|ost|soundtrack|official|[\s\-])+[\s)\]]+$', '', stem, flags=re.IGNORECASE)
        stem = re.sub(r'[^a-zA-Z0-9]', ' ', stem)
        stem = " ".join(stem.split()).lower()
        stem = stem.replace("artifical", "artificial")
        stem = re.sub(r'\s*0+(\d+)', r' \1', stem)
        return stem.strip()
```
1. **81行目**: `re.sub(r'[^a-zA-Z0-9]', ' ', stem)` が ASCII 英数字以外の全 Unicode 文字（日本語のひらがな・カタカナ・漢字、ハングル、キリル文字、アクセント文字等）を削除している。
2. **84行目**: `re.sub(r'\s*0+(\d+)', r' \1', stem)` は先頭ゼロ除去（`"01"` → `"1"`）を意図しているが、`\s*`（0文字以上の空白）になっているため、`"1000"` や `"2001"`、`"fath0m"`、`"108"` のような**数値途中の `0` まで空白＋数字に分割・破壊**している（例: `"1000"` → `"100 0"` や `"00001 01000"` → `"1 1000"`、`"fath0m"` → `"fath 0m"`）。

### 2.2 `src/sst/builder.py` (`MetadataBuilder.build_tag_map`: 104〜124行目)
```python
        # 2. matched_v_idxが無くても、STEAMトラックリストからのファジーマッチを試みて補完する
        if not pics_track and instr.get("matched_v_idx") is None:
            fuzzy_clean_title = re.sub(r'^(\d+[\s._-]+)+', '', clean_title)
            fuzzy_clean_title = re.sub(r'\.[a-zA-Z0-9]+$', '', fuzzy_clean_title)
            fuzzy_clean_title = re.sub(r'[^a-zA-Z0-9]', ' ', fuzzy_clean_title)
            fuzzy_clean_title = " ".join(fuzzy_clean_title.split()).lower()

            exact_match = None
            prefix_match = None
            for t in steam_meta.store_tracklist:
                t_title = t.get("title") or t.get("name", "")
                norm_t_title = re.sub(r'[^a-zA-Z0-9]', ' ', t_title)
                norm_t_title = " ".join(norm_t_title.split()).lower()
                
                if norm_t_title == fuzzy_clean_title:
                    exact_match = t
                    break
                if not prefix_match and fuzzy_clean_title.startswith(norm_t_title + " "):
                    prefix_match = t
            
            pics_track = exact_match or prefix_match
```
1. `clean_title` に含まれる `::file_id` サフィックスを除去せずに `fuzzy_clean_title` を作っているため、`fuzzy_clean_title` の末尾に `<file_id>` が残ってしまい、完全一致（`norm_t_title == fuzzy_clean_title`）が絶対に成立せず、常に緩い前方一致（`startswith(norm_t_title + " ")`）に流れている。
2. `re.sub(r'[^a-zA-Z0-9]', ' ', ...)` により日本語が消去され、`norm_t_title` が `""` や `"feat"` になった場合に誤マッチする。
3. そもそも `instr.get("matched_v_idx") is None` のトラック（未割当トラック）に対して、すでに他トラックが割り当て済みのSteamスロットや、`startswith` だけの曖昧一致で勝手に `pics_track` を補完すると、本来のトラックと重複（`Duplicates`）を引き起こす。

---

## 3. 具体的な修正仕様

### 3.1 `TrackManager.normalize_title` (`src/sst/track_grouper.py`) の修正
1. **Unicode NFKC 正規化の導入**:
   `unicodedata.normalize("NFKC", html.unescape(stem or ""))` を適用し、全角英数字・全角カタカナ・ローマ数字（`Ⅲ` → `III` 等）を標準化する。
2. **Unicode 単語文字（文字・数字）の保持と記号・句読点のみの空白化**:
   `re.sub(r'[^a-zA-Z0-9]', ' ', stem)` を廃止し、Unicode の文字（Letter: `L`）および数字（Number: `N`）を保持し、アンダースコア `_` を含む句読点・記号・空白類のみを半角スペース `" "` に置換する。
   - 実装例（標準ライブラリ `unicodedata` + `re` を使用）:
     ```python
     stem = "".join(
         ch if unicodedata.category(ch)[0] in {"L", "N"} else " "
         for ch in stem
     )
     ```
     （※アポストロフィ `'` や `’` は注意：従来 `Don't` → `don t` または `Coward's` vs `Cowards` の比較が行われていたため、アポストロフィ類 `['’`]` は空白化ではなく除去 `""` にするか、または空白化後に比較側と一貫させること。ただし既存テストとの互換性を確認し、既存テストが `"don't"` → `"don t"` を期待している箇所があれば空白化を維持し、所有格 `'s` 等との互換性を保つこと。）
3. **先頭ゼロ除去正規表現の修正**:
   84行目の `re.sub(r'\s*0+(\d+)', r' \1', stem)` を、**独立した数値トークンの先頭ゼロのみ**を除去するように修正する：
   ```python
   stem = re.sub(r'(?:^|(?<=\s))0+(\d+)', r'\1', stem)
   ```
   これにより `"01"` → `"1"`、`"cave 02"` → `"cave 2"` は維持しつつ、`"1000"` や `"fath0m"` の途中のゼロが破壊されないようにする。

### 3.2 `MetadataBuilder.build_tag_map` (`src/sst/builder.py`: 104〜124行目) の修正
1. `clean_title` からまず `raw_clean_title = clean_title.split("::", 1)[0]` で `::file_id` を除去する。
2. 正規化には独自の `re.sub(r'[^a-zA-Z0-9]', ...)` を使わず、`TrackManager.normalize_title(raw_clean_title)` および `TrackManager.normalize_title(t_title)` を使用する。
3. **空文字一致および危険な短語前方一致の禁止**:
   - `if not fuzzy_clean_title:` の場合はファジー補完を行わない。
   - `norm_t_title` が空文字の場合はスキップする。
   - `exact_match`（`norm_t_title == fuzzy_clean_title`）がアルバム内で一意（1件のみ）に一致する場合のみ補完を許可し、`"feat"` のような汎用短語による誤爆を生む `prefix_match`（`startswith`）は廃止する（または `len(norm_t_title) >= 6` かつ一意一致かつ未割当スロットの場合に限定する）。

### 3.3 `src/sst/llm/prematch.py` の修正
[`resolve_prematch_signals`](file:///mnt/workspace/S.S.T/src/sst/llm/prematch.py#L134-L136) の136行目：
- **修正前**:
  ```python
  if not s_title or not l_title or s_title == l_title or s_title in l_title or l_title in s_title:
  ```
- **修正後**:
  ```python
  if s_title and l_title and (s_title == l_title or s_title in l_title or l_title in s_title):
  ```
  `s_title` または `l_title` が空の場合に無条件でタイトル一致とみなす挙動を廃止する。

---

## 4. 不変条件・禁止事項

- 英語タイトルに対する既存の `TrackManager.normalize_title` の挙動（先頭トラック番号の除去、末尾の `(OST)` / `[FLAC]` 等のフォーマット・サフィックス除去、小文字化、`"artifical"` → `"artificial"` 補正、`"01"` → `"1"` の先頭ゼロ正規化）を壊さないこと。
- `MetadataBuilder.build_tag_map` で `matched_v_idx` が設定されていない未割当トラックに対し、根拠の薄い前方一致でSteamスロットのタイトルやトラック番号を捏造・上書きしないこと。

---

## 5. テスト作成指示

`tests/test_id3_tag_construction.py` および `tests/test_batch_accuracy_improvements.py` に以下のテストを追加すること。

1. **`test_normalize_title_preserves_japanese_korean_cyrillic_and_nfkc`**:
   - `"01 いつかあの場所で.wav"` → `"いつかあの場所で"`（空文字にならないこと）
   - `"02 特定犯罪第５６８号調査開始（デモBGM）"` → 全角数字 `５６８` が NFKC 正規化により `"568"` になり、日本語が保持されること
   - `"01. Тёмная комната"` → `"тёмная комната"`（キリル文字が保持されること）
   - `"19 - Fath0m"` → `"fath0m"`（途中の `0` が空白で分割されないこと）
   - `"01 - 00001-01000"` → `"1 1000"`（先頭ゼロのみ除去され、末尾の `000` が壊れないこと）
2. **`test_build_tag_map_does_not_false_match_japanese_feat_track`**:
   - **設定**: AppID `689920` の再現。`store_tracklist` に `{"disc": 1, "number": "8", "title": "無色不透明(feat.鏡音リン)"}` があり、`matched_v_idx=None` の未割当トラック `clean_title = "1bitheart feat kagaminerin::abcdef1234567890"` を `MetadataBuilder.build_tag_map` に渡す。
   - **検証**: `tag_map["title"]` が `"無色不透明(feat.鏡音リン)"` に化けず、`tag_map["track_number"]` が `"8"` にならないこと。
3. **`test_japanese_titles_match_in_unassigned_reconciliation_and_slot_variants`**:
   - **設定**: Steamスロット `{"disc": 1, "number": "1", "title": "いつかあの場所で"}` に対し、日本語タイトルを持つ WAV と MP3 の2バリアント、および未割当残差確定をテスト。
   - **検証**: `build_slot_variant_index` で WAV と MP3 が同一スロット `(1, "1")` に統合され、`reconcile_deterministic_unassigned_slots` でも日本語タイトルの一致により `matched_v_idx=0` が確定すること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_id3_tag_construction.py tests/test_batch_accuracy_improvements.py tests/test_fast_track.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。
