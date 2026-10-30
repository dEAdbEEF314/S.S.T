# 修正指示書 01: ResultValidator の過剰検知防止と自スロット適合先行判定

## 1. 背景と課題

`fix_0.3 指示書 06` で導入された `ResultValidator` のクロススロット衝突検査（`_validate_official_title_mismatch`）は、ファイル名やタグから抽出したタイトルの括弧内表記（例: `(New Tokyo)`）を除去した基底タイトルを用いてアルバム内の他スロットとの衝突を検査し、曲の取り違え（AppID `4206020` 等）を防御する設計であった。

しかし、この検査が**「割り当てられた自スロットとすでに合致しているか」**の条件を無視して無差別に他スロット衝突を検査していたため、以下の重大な過剰検知（誤Review）が発生していた：
- 同一アルバム内に原曲 `In My Heart` と拡張版 `In My Heart (Extended Ver.)` や `In My Heart (Remix)` が共存する場合、拡張版スロットに正しく `02. In My Heart (Extended Ver.).mp3` が割り当てられているにもかかわらず、括弧除去後の `in my heart` がスロット 1（原曲）のタイトルと完全一致し、「別スロットのタイトルと一致した」と誤認され `Official Title Mismatch` に送られていた。
- これにより、DJMAXシリーズ13作品をはじめ、TRIZEAL、BLUE REVOLVER、Katana ZEROなど全20件が不当にReview送りとなっていた。

## 2. 解決方針

1. **自スロット適合判定（`matches_assigned`）の先行実施**:
   - 抽出されたローカルタイトル群（ファイル名ステム、タグ、クリーンタイトル、および括弧除去バリアント）が、割り当てられた当該スロットのSteam公式タイトル（またはそのバリアント）とすでに合致している場合、自スロット適合とみなし、**他スロット衝突検査をバイパス**する。
2. **真の取り違え検知の維持**:
   - 当該スロットのタイトルと一切合致せず、かつアルバム内の別スロットと合致する場合のみ、真の入れ替わり・誤割当（`4206020`型）として検知し `Official Title Mismatch` を発報する。
3. **Steamタイトル側のバリアント展開（`_expand_title_variants`）**:
   - ローカル側だけでなくSteam公式タイトル側にも対称的にバリアント展開を適用し、公式側が括弧表記（`Title (Original Mix)` 等）を持つ場合でも相互に正しく適合判定できるようにする。

## 3. 実装詳細

### `src/sst/validator.py`
- `_expand_title_variants(title: str) -> List[str]` ヘルパー関数を新設。
- `assigned_norm_titles` を `_expand_title_variants` により展開。
- `matches_assigned` フラグを新設し、自スロットの候補タイトル群と `assigned_norm_titles` を照合。
- `matches_assigned == False` の場合のみ `for other_key, other_norm_titles ...` の他スロット衝突ループを実行。

