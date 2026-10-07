# 実装・設定・文書の差分台帳

更新日: 2026-10-07

この台帳は、現行の実装・設定・実測記録と補助文書の差分を記録する。仕様上の不変条件は `docs/METADATA_SOURCE_SPEC.md`、`docs/TAGGING_RULE.md`、`docs/LOGIC.md` を正本とする。

| ID | 分類 | 正本・根拠 | 実装・文書 | 判定と対応 | 検証・残作業 |
| --- | --- | --- | --- | --- | --- |
| DOC-001 | README実績 | `report/batch_analysis_all_soundtracks_20260903.md` | `README.md`、`CHANGE_HISTORY.md` | 2026-09-03実測は344走査、音源あり304、Archive 248 (81.58%)、Review 56、音源なしSkip 40。READMEの日英にあった313/344 (90.99%) とReview 31件はこの結果と一致しないため、READMEを実測レポートへのリンク付き履歴値へ訂正した。9/5のCHANGE_HISTORY記述は過去の記録として保持し、この差異と訂正を新しい履歴に記録する。 | READMEに313/344、90.99%、9.01%が残っていないことを検索。現在の性能保証とは記載しない。 |
| DOC-002 | Fast-Track実績 | 同上、処理経路集計 | `README.md` | 230/304 = 75.66%は全344走査ではなく音源あり304件が分母。READMEで日付・分母・実数を併記した。 | reportの230件とREADMEの記述を照合。 |
| DOC-003 | 性能値の配置 | `docs/PERFORMANCE_OPTIMIZATION_RUNBOOK_jp.md` §8 | `docs/configuration.md` | 約35分、13ms、0.47ms等の計測値は実行条件を持つ履歴ベンチマークとしてrunbookに残し、一般設定説明であるconfigurationから性能保証に読める記述を除いた。 | Runbookに100件バッチの条件と測定内容を記録。複数回の再現計測値とは扱わない。 |
| CONF-001 | 設定キー同期 | `src/sst/config.py` のactive fields | `.env.example`、`docs/configuration.md`、`tests/test_config_loading.py` | Active Config fieldの環境変数名がsampleと文書に存在することをテストする。sampleの実効値とConfig既定値の差分もallowlistで管理し、Ollama推奨profile、placeholder、必須path、新priority明示値を区別する。非Noneの全fieldはガイドに既定値を1箇所だけ記載し、文字列・数値・booleanの値をConfig定義と照合する。unitを持つ74 fieldにPydantic description/canonical unit/document display unitを付け、設定ガイドの表示単位もテストする。 | `uv run pytest tests/test_config_loading.py -q`。unit labelの存在は機械照合するが、description内容の意味的正確さは引き続き手動レビューする。 |
| CONF-002 | Steam/LLM/通知timeout・retry | `Config` と各serviceへの注入 | `steam_web_api.py`、`vram_manager.py`、`notify.py`、`docs/configuration.md` | Steam API retry delay/backoff、Store Browse timeout、VRAM warm-up/health timeout、通知timeout/retry scheduleをConfigから渡す。固定nvidia-smi timeoutはnamed constant。 | 関連Config/Steam/Vramテストと既存API caller signature testsを実行済み。全体検証結果は実装状況表を参照。 |
| CONF-003 | path集約 | `Config`、起動時注入 | `main.py`、`scanner.py`、`.env.example`、`docs/configuration.md` | Steamタグcache pathを `SST_STEAM_TAG_CACHE_PATH` として追加。`ScannerCacheManager` のconstructor defaultは直接利用者向けの後方互換fallbackとして残す。 | Config、Steam tag-cache、tracklist focused tests。 |
| CONF-004 | legacy metadata priority | 新 `METADATA_FIELD_FALLBACK_PRIORITY` 優先、次に旧 `METADATA_SOURCE_PRIORITY` | `src/sst/config.py`、`docs/configuration.md` | 新fieldの既定を未指定状態にし、新設定 > legacy設定 > 共通既定値の順を実装。旧名は互換維持するが、Config生成時にwarningで新名への即時移行と旧キー削除を案内する。新旧併記時は旧名が無視される旨も出す。 | 新旧同時指定、legacy直接指定、legacy環境変数それぞれの解決順・warningをConfig testsで確認。旧名廃止時期は未決。 |
| CONF-005 | Pydantic環境変数処理と.env権限 | Pydantic Settingsを唯一の値読込経路とする | `src/sst/config.py`、`src/sst/main.py` | 手動の `load_env_overrides` 型変換を除去。互換methodから `.env` 権限検査のみを行い、CLI起動時に呼ぶことで設定ガイドに記載したwarningを有効化。 | 手動変換の対象設定と、`check_env_security` 呼び出しをfocused testsで確認。 |
| CONF-006 | 未使用設定・別名 | 現行Config fieldと呼出元 | `src/sst/config.py`、`docs/configuration.md` | 使用されない `LLM_NUM_CTX`、`LLM_COHERENCE_THRESHOLD`、`TITLE_CLEANING_TRUSTED_SOURCES` をConfigから除去。`LLM_OLLAMA_NUM_CTX` は現行設定。`metadata_source_priority` は互換用fieldとして残す。 | Config/docs key synchronization test。全環境に対する廃止名利用の運用観測は未実施。 |
| CONST-001 | 仕様固定値 | `TAGGING_RULE.md`、`METADATA_SOURCE_SPEC.md` | tagger、validator、packager | ID3v2.3、Steam構造正本、Tier優先度、Review/preflight安全ゲートなど挙動契約はConfig化しない。DBのSQLite `busy_timeout=5000ms` とrate limiterの窓・負荷しきい値も現行コードの固定アルゴリズム値として扱う。 | 変更時は契約仕様と既存合成テストを更新する。全数値リテラルの意味分類ではなく、設定変更による安全境界の変更を防ぐ分類。 |
| CODE-001 | 未使用helper | `rg`で参照先なし | `src/sst/rate_limit.py` | usage file writerは定義のみで呼出しがなく、usage記録経路も存在しなかったため削除。併せて未使用のlogs path・datetime importを削除。 | 参照検索とRuff、全テストで確認。 |
| CODE-002 | module到達性 | `sst.main`、`sst.log_browser`、`sst.__init__`をrootにしたAST import graph | `src/sst/**` | 61 module中60が静的importで到達。唯一未到達の`processing/__init__.py`はpackage marker/docstringのみのため維持。`processor_support.py`はprocessorと複数testから参照され、互換patch pathを持つため削除しない。 | 静的graphは`getattr`等の動的参照、外部利用者のimport、運用時の直接実行を証明しない。method単位の未使用判定は別途継続し、未到達moduleだけを理由に削除しない。 |
| DOC-004 | 処理契約・図 | `METADATA_SOURCE_SPEC.md`、`TAGGING_RULE.md`、`LOGIC.md`、`validator.py`、`alignment_flow.py` | `docs/data_flow_diagram.md`、`docs/LOGIC.md` | Archive thresholdは通常90/80/70、STEAM-TRUST 90/75/60で一致。`STEAM_TRUST`は実行routeではなくvalidator昇格経路、`processing_route`はFAST_TRACK / LLM_ONE_SHOT / LLM_CHUNKED、REVIEW/EARLY_REVIEW/ERRORは終端結果、SKIP_NO_AUDIOはscan resultとして分類した。LLM_ONE_SHOTはConfig tier由来の`prefer_one_shot` profile preferenceを表し、実request数を保証しないと記載。LOGICに通常thresholdおよびSTEAM-TRUSTのconfidence条件と、slot/LLM矛盾/deferred copy/tag/audio/path/archive-preflight Review条件を追加。 | 文書と既存実装の照合済み。`docs/configuration.md`、route diagram、Review一覧の変更部診断は通過。 |

## ハードコード値の分類方針

この監査の網羅対象は、deployment・host資源・外部サービス・実行条件に応じて変える合理性がある値に限定する。具体的には接続先、path、timeout/retry、外部rate制限、worker/token予算、cache容量・期間など。これらはConfig fieldから環境変数、`.env.example`、設定ガイド、実際のconsumerへの注入まで追う。全numeric literalを列挙する作業ではない。

- 対象外: validation threshold、Steam/ID3 authority、Archive/Review safety gateなど、値を変えると契約・品質保証が変わる固定値。
- 対象外: API/file inputから取得される値、およびテスト専用のsynthetic値。
- 境界例: scoring weightsは運用調整値としてConfigに残し、単位をscore pointsとして記載する。アルゴリズム閾値と挙動契約はConfig化せず、仕様とテストで保護する。

- Configへ集約する実行環境値: API URL、timeout/retry、worker数、外部rate制御、ログ・cache・userdata・output path、モデル・token予算。
- 名前付きで仕様に固定する値: Steam/ID3 authority、ReviewとArchive preflight、slot/Tier規則、SQLite busy timeoutとrate limiter内部窓・負荷しきい値。
- 入力由来として維持する値: Steam/PICS/MusicBrainz/AcoustID response、AppID、ファイル由来metadata。
- テスト専用値: synthetic paths、localhost、dummy keys。実データや認証情報をfixtureに含めない。

この分類は全numeric literalの機械的な網羅表ではない。環境差を生む設定候補はConfig・環境例・設定ガイドのkey同期で検出し、挙動契約の固定値は上記の正本とテストで保護する。
