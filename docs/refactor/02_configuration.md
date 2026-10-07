# 作業者2: 設定集約とハードコード値

## 目的

環境差・接続先・性能条件に関わる値を `Config` に集約し、コード、`.env.example`、設定書の三者を検証可能にする。仕様として固定すべき値は、無理に設定化しない。

## 対象

- `src/sst/config.py`
- `.env.example`
- `docs/configuration.md`
- `src/sst/main.py`
- URL、timeout、retry、並列数、パス、モデル名、cache TTL、ログ出力先を持つ全モジュール
- `LLM_NUM_CTX` / `LLM_OLLAMA_NUM_CTX`、旧metadata priority設定

## 依存関係

作業者1の基線確定後に開始する。作業者3・4が利用する設定契約を先に文書化する。

## 作業内容

1. ハードコード値を次の4分類で台帳化する。
   - 設定化: URL、timeout、retry、並列数、パス、モデル、cache TTL、外部API制限
   - 名前付き不変定数: ID3v2.3仕様、音声Tier、Review安全ゲート、1秒未満など
   - 入力由来: Steam値、外部レスポンス、AppID
   - テスト専用: localhost、ダミーキー、合成ログ
2. 既知候補を確認する。
   - `main.py` の Steam userdata timeout `10`
   - `data/`、`logs/`、`data/sst.lock`、`data/sst_cache.json`
   - モジュール内の環境変数読み込みと暗黙既定値
3. `Config` を唯一の設定所有者として、必要なフィールド、型、範囲、単位、秘密情報区分を整理する。
4. `Config.load_env_overrides()` の手動変換を縮小し、Pydantic Settingsの型検証に寄せる。既存 `.env` を壊さない互換読み込みと警告を設計する。
5. `LLM_NUM_CTX` と `LLM_OLLAMA_NUM_CTX`、`metadata_source_priority` と `metadata_field_fallback_priority` の正本・旧名・廃止時期を決める。
6. `.env.example` と `docs/configuration.md` のキー、既定値、単位をコードから検証するテストまたは検証スクリプトを追加する。
7. 最小設定、完全設定、型不正、範囲外、秘密情報ログ漏えいを合成データでテストする。

## 初回調査で見つかった設定差分

- `llm_request_parallelism_max_workers`: `Config` 未指定時は `4`、`.env.example` は `2`。文書は両者を区別するよう更新済み。
- MusicBrainz track count penalty: `Config` 既定値だけが `300` / `2000` だった。識別器既定値・`.env.example`・設定書に合わせ、`20` / `300` へ変更して回帰テストを追加済み。

以降の設定値も同じ手順で実効値を調査し、台帳へ根拠とともに記録する。

## 禁止事項

- ID3・Archive/Review・STEAM正本などの固定仕様を性能設定として外出しすること
- 秘密情報を `.env.example` やテストに実値で記録すること
- 作業者3・4のコードを直接同時編集すること
- 旧設定を予告なく削除すること

## 成果物

- ハードコード分類台帳
- `Config` と環境変数の変更
- `.env.example` と設定検証
- 設定テスト
- 旧設定からの移行表

## 完了条件

- 実行条件に関わる暗黙既定値が残っていない、または名前付き固定値として根拠がある。
- コード・`.env.example`・設定書のキーと既定値が一致する。
- 既存設定の互換方針が明記され、テストされている。
