# S.S.T 監査・中間成果物仕様

## 目的

S.S.T は Steam の公式スロット構造を正本として、物理出力と判断根拠を後から再検証できる状態で保存する。Archive は「LLM がそう判断した」だけでは成立せず、最終ファイル、タグ、Steam slot、件数を再走査した preflight を通過しなければならない。

## 判定と監査

- Steam に存在する `Unknown` / `Unknown (Unused)` は正規タイトルとして扱う。
- Steam の同一 slot が通常タイトルなのに、最終タグだけ `Unknown` の場合は異常 Unknown とする。
- 同一 Steam slot に複数形式の候補がある場合は、形式違い候補として品質 tier の高い1ファイルへ統合する。
- 同一 slot の最終重複は、形式違い候補の統合後にも残った場合だけ構造異常とする。
- Review 理由は `primary_review_cause` と `secondary_review_causes` に分けて保存する。
- 未割当ファイルは、slot 不一致、候補過剰、LLM 未割当、変換失敗などの上流理由を保持する。

各処理結果の監査情報には、Steam期待slot数、最終採用slot数、重複slot数、正規Unknown数、異常Unknown数、入力数、採用数、未割当数、Archive preflight問題を含める。

## LLM

LLM 応答の `done_reason=length` / `max_tokens` は成功扱いにしない。再試行し、各試行の所要時間、終了理由、prompt/eval token 数、切り詰めフラグを `llm_log.json` に保存する。JSON はオブジェクトであることを検証し、配列や壊れた応答を downstream に渡さない。

チャンクサイズは固定値ではなく、実行 tier、推定 prompt、track あたり出力 token、安全率から制御する。チャンクが大きすぎる場合は縮小し、整列を安全側へ倒す。

## SST_WORKING_DIR

- 通常の INFO 実行: `final_<AppID>_*`、`buffer_<AppID>_*`、`early_review_<AppID>_*` を処理終了時に削除する。
- `--dev` 実行: 中間成果物を保持する。
- `LOG_LEVEL=DEBUG`: 中間成果物を保持する。
- `--force` かつ保持モード: 既存成果物を事前削除しない。
- `--force` かつ通常モード: 対象 AppID の既存試行だけを事前削除する。
- 専用 cleaner の明示実行は、保持モードとは独立した手動操作である。

保持時は AppID、パス、保持理由をログへ出力する。中間成果物は機密情報を含み得るため、共有フォルダへ無制限に置かず、確認後に専用 cleaner で削除する。

## 回帰テスト方針

Steam の正規 Unknown、通常タイトルに対する異常 Unknown、形式違い候補、重複 slot、LLM 切り詰め、INFO/DEBUG/`--dev` の cleanup を合成 fixture で検証する。既存の実データレポートは書き換えず、将来生成されるレポートと DB metadata の契約を検証する。
