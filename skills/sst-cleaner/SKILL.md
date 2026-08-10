---
name: sst-cleaner
description: データベース、中間生成物、一時ファイル、キャッシュを削除してS.S.Tシステムを初期化します。システムをクリーンな状態に戻したい場合に使用します。
---

# sst-cleaner

このスキルは、S.S.Tシステムの運用中に生成された不要なデータ（データベース、ログ、キャッシュ、中間生成物）を一括で安全に削除します。

## 🛠 削除対象
以下のディレクトリおよびファイルが削除されます：
- **データベース**: `data/sst_local_state.db*`
- **スキャナ／スキルキャッシュ**: `data/sst_cache.json`, `data/scout_cache.json`（`--clear-all-cache`時）

- **ログ**: `logs/*.log`
- **中間生成物**: `output/` 配下の全ファイル（※出力されたZIPアーカイブ等もテスト環境リセットのため削除対象となります）

## 🚀 実行手順
初期化のリクエストがあった場合、以下のスクリプトを実行してください。

```bash
uv run python <path-to-skill>/scripts/clean_system.py
```

オプション引数：
- `--keep-prefetch`: 事前フェッチした情報（`api_cache`、`steam_store_data`）は維持したまま、履歴や出力物だけを初期化します。（※これがデフォルトの挙動です。明示的に指定したい場合に使用します）
- `--clear-all-cache`: この引数を指定すると、事前フェッチされた情報を含むすべてのデータベース情報と、スキャナ／スキルキャッシュを完全に初期化します。
- `--appid A,B`: 指定AppIDだけを対象に、処理履歴、AppID固有cache、対象ZIP、`final_<AppID>_*` / `buffer_<AppID>_*`を削除します。共有cache、他AppID、batch report、ログは保持します。

`--appid`指定時は全体初期化を行いません。`--clear-all-cache`と併用した場合も、cache削除の範囲は指定AppIDに限定されます。`--force`はこのスキルの削除処理とは異なり、対象AppIDを新規処理として再取得・上書きするS.S.T本体の動作です。

S.S.T本体の`--force`は、処理開始前に対象AppIDの`SST_WORKING_DIR/final_<AppID>_*`と`buffer_<AppID>_*`だけを削除します。`--dev`でも今回の実行成果物は保持され、他AppID、元ライブラリ、`output/`のZIP、共有cacheは削除されません。

実行後、削除された項目数を確認し、ユーザーに報告してください。

## ⚠️ 注意事項
- アーカイブ済みのサウンドトラック（Steamライブラリ内）は**一切削除されません**。
- 実行前に、進行中の処理がないか確認してください。
- 削除されたデータベースやログは復元できません。
