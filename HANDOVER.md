# 引継ぎ文書 (Handover Document)

## 1. 現在のステータス (Current Status)

現在、`chache_more` ブランチにて「ツーフェーズ・アーキテクチャ (Two-Phase Pipeline) とキャッシュ層の導入」を完了し、テスト待ちの状態です。
LLMの待ち時間を排除し、事前に外部API (AcoustID, MBZ) のデータを取得・SQLiteへキャッシュする仕組みの実装が終わりました。

## 2. これまでに実施した作業 (Completed Tasks)

- **仕様策定**: `docs/cache_architecture.md` を作成し、ツーフェーズの仕様を定義しました。
- **データフロー図の更新**: `docs/data_flow_diagram.md` を Phase 1 と Phase 2 の構造に更新しました。
- **Step 1 (DBキャッシュ層)**: `src/sst/db.py` に `api_cache` テーブルと読み書きメソッドを追加しました。
- **Step 2 (APIクライアント)**: `acoustid.py` と `mbz.py` を改修し、通信前にDBキャッシュを利用するようにしました。
- **Step 3 & 4 (Pre-Fetchランナー)**: `src/sst/prefetcher.py` を作成し、`main.py` にフックすることでLLM推論前のマルチスレッドな一括データ収集 (Phase 1) を実現しました。

## 3. 次のアクション・残課題 (Next Steps & Pending Items)

### 3.1 優先事項 (Priority)

1. **実装のテスト**: `--fingerprint-all` オプションなどを用いた実戦テストを実施し、キャッシュヒット時の動作や全体の速度向上、レートリミットが正常に機能しているか検証してください。
2. **本流へのマージ**: テストが成功したら `main` ブランチへマージしてください。

### 3.2 未着手のドキュメント・仕様作成 (Pending Documentation)

ユーザーからは以下の機能追加・ドキュメント作成の要望が挙がっています。テストが完了し安定した後に着手してください。

- [x] Discord Integration の仕様策定と実装 (`docs/discord_integration.md` にて完了)
- [x] Smart Duplicate Resolution に関する独立したドキュメント作成 (`docs/smart_duplicate_resolution.md` にて完了)
- [x] Error Handling に関するドキュメント作成 (`docs/error_handling.md` にて完了)
- [x] Data Flow Diagram (データフロー図) の作成 (`docs/data_flow_diagram.md` にて完了)
- [x] API Rate Limit に関するドキュメント作成 (`docs/api_rate_limit.md` にて完了)
- [x] WSL Path Conversion Specification のドキュメント作成 (`docs/wsl_path_conversion.md` にて完了)

## 4. 特記事項 (Notes)

- **Steam Library への書き込み厳禁**: Steam ライブラリディレクトリへのアクセスは必ず **READ-ONLY** とし、すべての出力は `SST_OUTPUT_DIR` (`output/`) に行わなければなりません（ルール絶対遵守）。
- **ユーザーコミュニケーション**: 技術的なタスクに着手する前には、必ず**日本語**で作業内容、理由、影響範囲、期待する結果を説明してください。
- **LLMサーバー環境**: ユーザーは自宅内の本番LLMサーバー (`192.168.11.246:11434`, `LLM_BACKEND=OPENAI_COMPATIBLE`, カスタム `llama.cpp`) を使用しています。

---

*Created at: 2026-06-11T16:15:00+09:00*
