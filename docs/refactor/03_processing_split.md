# 作業者3: コア処理モジュールの分割

## 目的

処理順序と責務を維持したまま、`processor.py` と `processor_support.py` を分割する。公開APIとArchive/Review判定を壊さず、`LocalProcessor` を薄い互換ファサードへ近づける。

## 対象

- `src/sst/processor.py` 1,341行
- `src/sst/processor_support.py` 885行
- `src/sst/processor_tracks.py`
- `src/sst/processor_pipeline.py`
- 関連する `validator.py`、`builder.py`、`packager.py`、`report_generator.py`
- 関連テスト

## 依存関係

作業者1の契約テスト基線と、作業者2の設定契約を使用する。`llm/` 内部の責務分割は作業者4の担当なので編集しない。

## 作業内容

1. 既存テストを characterization test として確認し、不足する次の否定ケースを合成fixtureで追加する。
   - Steam slot欠落・範囲外
   - 未割当file ID
   - duplicate physical path
   - audio warning / audio failure
   - Preflight不一致
2. `processor_support.py` を次の責務へ移す。
   - `processing/slot_variants.py`: slot/variant index、重複統合
   - `processing/file_selection.py`: Tier優先の変換元選択
   - `processing/artwork.py`: EMBED→MBZ→STEAM
   - `processing/unassigned.py`: 未割当逆引き・隔離・manifest
   - `processing/notifications.py`: 通知送信
3. `processor.py` を次の責務へ段階分割する。
   - `processing/orchestrator.py`
   - `processing/fast_track.py`
   - `processing/working_files.py`
   - `processing/enrichment.py`
   - `processing/result_builder.py`
4. `LocalProcessor` を互換ファサードとして残し、移動した関数の呼び出しを委譲する。呼び出し元を一度に変更しない。
5. 依存方向を `models/config` → domain service → orchestration → CLI にする。循環importは作らない。
6. `report_generator.py`、`main.py`、`scanner.py` は第一段階では大規模変更せず、分割候補と後続作業を記録する。担当範囲を越える場合は作業者5へ文書化して渡す。

## 不変条件

- Fast-Trackの判定条件と最高Tier選択を変えない。
- LLMは変換元選択、タグ生成、最終fallbackを決めない。
- 未割当が1件でもあればReview。
- 成果物の物理パス重複・欠落・ZIP不一致はReview。
- `matched_v_idx`、Steam title、Steam track numberを推測で置き換えない。

## 禁止事項

- 大量の一括リネーム
- 公開APIの削除
- 仕様閾値や判定条件の変更
- 実データを使ったテストの追加

## 成果物

- 新しい `processing/` モジュール群
- 互換ファサードを維持した `LocalProcessor`
- 移動前後のテスト
- 循環importがないことの検証結果
- 第二段階候補の引き継ぎメモ

## 完了条件

- 既存テストが通り、追加した否定テストも通る。
- 分割後もArchive/Review判定と監査データが同一である。
- `processor.py` と `processor_support.py` の責務が明確に減っている。
- 公開呼び出し元の変更が最小限である。
