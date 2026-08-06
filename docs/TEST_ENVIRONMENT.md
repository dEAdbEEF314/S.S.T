# S.S.T テスト観点

## 1. 目的

新仕様で確認すべきなのは、単なる実行成功ではなく、STEAM を正本にした整列とタグ構築が期待どおり機能することです。

## 2. 最低限の実行確認

### 2.1 静的・単体確認

```bash
uv run pytest
uv run pytest tests/test_config_loading.py -v
uv run pytest tests/test_apic_comm_pickup.py -v
uv run pytest tests/test_id3_tag_construction.py -v
uv run pytest tests/test_archive_review_combined.py -v
```

必要に応じて対象テストのみを選択して実行します。

設定面の実装を進める最初の段階では、次を先に確認します。

- `.env.example` の変数名と `Config` のフィールドが一致する
- 新設定名が優先され、旧設定名は互換としてのみ扱われる
- 音質優先順が `wav -> flac/alac/aiff/aif -> ogg/aac/m4a -> mp3` の Tier 方針に沿う

### 2.2 実アルバムのスモークテスト

以下の代表ケースを少数で回します。

- STEAM トラック数とローカル曲数が完全一致するアルバム
- 複数フォーマット混在のアルバム
- 埋め込み APIC が一部フォーマットにしかないアルバム
- STEAM トラック一覧が不完全なアルバム
- ACOUSTID が一部しか当たらないアルバム

## 3. 判定パス別チェックリスト

### 3.1 ファストトラック

- 全曲にトラック番号がある
- 重複除外後の曲数が STEAM と一致する
- 同一番号の異フォーマットで duration 差が 1 秒未満
- LLM を呼ばずに archive できる

### 3.2 LLM アライメント

- slots に存在しない file_id が出ていない
- 同一 file_id が複数スロットへ重複割当されていない
- confidence が各スロットに存在する
- concerns と unassigned_reason が残る

### 3.3 STEAM-TRUST

- ACOUSTID 不在でも STEAM 構造一致で救済される
- ただし data_quality 低下時は review に落ちる

## 4. タグ検証

### 4.1 必須フィールド

- TALB
- TRCK
- TIT2
- TPE1
- TPE2
- TPOS
- TYER
- TCON
- TIT1
- COMM
- TLAN
- TCOM
- APIC

### 4.2 仕様チェック

- ID3v2.3 で書き込まれている
- TYER を使い TDRC を使っていない
- COMM が 2000 バイト超時に末尾から短縮される
- APIC が同一スロットの別フォーマットから拾える
- 変換元と APIC 取得元が異なっても成立する

## 5. Review 送りを確認すべきケース

- STEAM との 1:1 対応が崩れる
- title や track number の矛盾が解消できない
- LLM 出力 JSON が壊れる
- confidence は高いが必須フィールドが埋まらない

## 6. 監査ログ

少なくとも次を追跡できることを確認します。

- app_id
- track_id または file_id
- どのソースから各フィールドを採用したか
- archive / review の最終理由

## 7. 実装フェーズ別の停止点

### 7.1 設定整理フェーズ

- `tests/test_config_loading.py` が通る
- 既存の実行プロファイル関連テストが壊れていない

### 7.2 ファストトラック再実装フェーズ

- 条件ごとの失敗理由を個別に確認できる
- LLM スキップ経路が単体テストで確認できる

### 7.3 LLM 入出力刷新フェーズ

- 出力 JSON の必須フィールドが揃う
- file_id 重複割当や未知参照が検出される
- 旧 `track_instructions` から新 `slots` 形式への互換変換が単体テストで確認できる
- `album_confidence`, `mapping_confidence`, `data_quality`, `concerns` の別名が揃う

### 7.4 タグ構築・判定フェーズ

- APIC / COMM 横断取得テストが通る
- 3 軸判定の 4 経路が確認できる
- 決定論的 ARCHIVE、LLM 後 ARCHIVE、STEAM-TRUST、REVIEW を個別に止めて確認できる

推奨コマンド:

```bash
uv run pytest tests/test_apic_comm_pickup.py tests/test_improvements.py -v
uv run pytest tests/test_id3_tag_construction.py tests/test_archive_review_combined.py -v
```