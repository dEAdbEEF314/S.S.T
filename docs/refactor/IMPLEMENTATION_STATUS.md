# リファクタリング実装状況

更新日: 2026-10-07

この記録は [全体計画](../REFACTORING_PLAN.md) の初回実装状況を示す。作業者別の指示は同じディレクトリの `01_`〜`05_` 文書を参照する。

## 変更前基線

- `uv run pytest`: 237 passed
- `uv run ruff check src tests scripts`: 未使用importを4件検出
- Ruff指摘: `scripts/run_review_retest.py` の `Path`、`tests/test_performance_optimizations_v2.py` の `pytest` / `Path` / `sqlite3`

## 担当別の進捗

| 担当 | 状態 | 実施内容 | 残作業 |
| --- | --- | --- | --- |
| 1. 基線・未使用コード | 進行中 | 変更前237件基線、未使用import 4件を削除。`rate_limit.py` の参照されないusage-file helperも削除。AST import graphではCLI `python -m sst.main` / log-browserをrootに61 module中60へ到達し、未到達の`processing/__init__.py`はdocstringだけのpackage markerとして保持。`processor_support.py`の10 re-export、`LLMOrganizer`の互換wrapper、および`LocalProcessor`の責務・compatibility候補を一覧化。 | 静的graphと既知の互換surface一覧は作成済み。削除候補ごとに動的参照・外部利用者・運用scriptの確認を続け、一覧外だからという理由だけで削除しない |
| 2. 設定・ハードコード | 進行中 | Steam/通知/VRAM/FFmpeg等のtimeout/retryをConfigへ集約。Pydantic Settingsを値読込の唯一経路とし、旧metadata priority利用時は即時移行warningを出す。既定値同期に加え、unitを持つ74 Config fieldにdescription/canonical unit/display unit metadataを付与し、設定ガイドの単位一致テストを追加。監査範囲は外部環境で変わる値に限定。 | unit labelと既定値の機械照合は実装済み。descriptionの意味的精査、constructor fallbackの実利用分類、旧priorityの廃止release決定 |
| 3. コア処理分割 | 進行中 | `processing/fast_track.py`、`artwork.py`、`slot_variants.py`、`file_selection.py`、`unassigned.py`、`notifications.py`、`duplicate_mappings.py`、`track_batch.py`、`album_context.py`、`deferred_copy.py`、`package_output.py`、`package_metadata.py`、`package_validation.py` と `alignment_flow.py` へ抽出済み。`processor_support.py` は互換ファサード。`LocalProcessor`は委譲wrapperを維持。 | 残存methodの責務一覧と所有moduleを下表で分類。`process_album`制御ループ、Fast-Track判定、physical archive preflight等はProcessorに残存。互換shimの動的呼出し調査とcharacterization testを進める |
| 4. LLM処理分割 | 進行中 | `normalization.py`、`assignment_validation.py`、`identity.py`、`tracklist_extractor.py`、`backend_request.py`、`response_parser.py`、`coherence.py`、`alignment_segments.py`、`retry_policy.py`へ責務抽出。再試行境界、HTTP/例外/truncation別縮退条件、jitter/backoff、Ollama出力予算拡張をcharacterization testで保護。既存`LLMOrganizer` methodは互換wrapperとして維持 | backend応答処理とorganizer調停層をさらに整理。既存振る舞いを維持するcharacterization testsを継続 |
| 5. 文書整合 | 進行中 | `DOCUMENTATION_DRIFT.md` を追加。README実績と分母、性能値のrunbook分離に加え、route分類・One-Shot tier preference・全Review条件をsource spec/LOGIC/diagramへ反映。Config既定値/unit metadataの文書同期を自動テスト化。 | README/CHANGE_HISTORYの既存Markdown書式警告は今回の範囲外。要件化されていない説明文の手動精査を継続 |

## Processor責務と削除gate

| `LocalProcessor`内の責務 | 現状 / 所有先 | 分割判断 |
| --- | --- | --- |
| `process_album` | album処理全体の制御・エラー境界・作業dir cleanup | orchestratorとして残す。各stageの業務ロジックは隣接moduleへ委譲する |
| `_init_album_context` / `_execute_alignment_flow` / `_encode_and_tag_tracks` | `processing/album_context.py`、`alignment_flow.py`、`processing/track_batch.py`へ委譲 | 薄いcompatibility wrapperとして保持し、直接callerを調査してから廃止可否を決める |
| `_finalize_album_package` | validator、summary metadata、通知、package outputを順に結合。各責務は`processing/package_validation.py`、`package_metadata.py`、`notifications.py`、`package_output.py`へ抽出済み | stage coordinatorとして残す。個別責務を再抽出しない |
| `_check_fast_track` / slot map builders | Fast-Track証拠・構造一致を判定。slot normalization/mapは`processing/fast_track.py` | 判定predicateとglobal identity組立の残部を分離するかcharacterization test後に判断 |
| deferred-copy methods | retry queue・finalizer lifecycleを制御し、処理本体は`processing/deferred_copy.py`へ委譲 | queue ownershipはProcessorに残し、結果整形のみ必要に応じて抽出 |
| `_fetch_album_artwork` | 遅延MBZ candidate providerを作成して`processing/artwork.py`へ委譲 | callback・互換patch pathの参照を確認するまでwrapperを保持 |
| `_validate_archive_artifacts` | 実出力path/file/tag/Steam slotを再検証する最後のArchive gate | safety boundaryとしてProcessorに置く。分離する場合は同じpreflightを必須にする |
| `_normalize_processed_tracks` / duplicate count | slot単位の選択・diagnostic集計 | 呼出元・test patch pathを確認し、独立価値が薄ければ近接validation moduleにまとめる |
| `_build_album_execution_profile` | Config tierからnum_ctx・worker・prefer_one_shotを選択 | tier境界の責務としてProcessorに残すか、`execution_profile.py`へ抽出する候補 |
| `_send_notifications` / `_resolve_duplicate_mappings` | `processor_support.py`やprocessing helperへのcompatibility wrapper | 外部参照がないことを確認するまでAPI surfaceとして保持 |

互換API/Wrapperとして現在明示的に保護するsurface:

- `processor_support.py`: `apply_mbz_track_artists_to_fast_track`、`fetch_album_artwork`、`safe_download_image`、`build_slot_variant_index`、`merge_embedded_tags_for_slot`、`adopt_best_file_per_slot`、`select_best_unassigned_files`、`reconcile_deterministic_unassigned_slots`、`send_notifications`、`resolve_duplicate_mappings`。processor/test import・patch pathとして参照される。
- `LLMOrganizer`: `_call_llm`（parallelism/organizer testsが直接patch）、`_normalize_track_mapping_result`（schema testsが直接呼出し）、`_resolve_album_identity`、`_extract_deterministic_prematches`、および抽出済みnormalization/validation helperの既存wrapper。
- `LocalProcessor`: `process_album`、`set_vram_manager`、`resolve_deferred_copy_retries`、`cleanup_force_working_dirs`と上表のstage/wrapper method。processor testsとrunner callbacksから到達する。

この一覧は削除許可リストではなく、既知の保持対象である。一覧外のprivate methodも、静的未参照だけで削除せず、dynamic lookup・external import・script/test patch pathを調査してから削除可否を決める。

## 初回実装の対象検証

- `uv run pytest tests/test_config_loading.py -q`: 9 passed
- `uv run pytest tests/test_fast_track.py tests/test_apic_comm_pickup.py -q`: 28 passed
- `uv run pytest tests/test_llm_schema_normalization.py tests/test_analysis_accuracy_fixes.py tests/test_audit_accuracy_and_audio_warn.py -q`: 19 passed
- 担当範囲のRuffチェック: 通過

## 設定集約の追加検証

- `uv run pytest tests/test_config_loading.py tests/test_logging.py tests/test_main_configuration.py`: 12 passed
- Config環境変数読み込み、カスタムログディレクトリ、Steam userdataの設定timeoutとネスト保存先を検証
- `uv run pytest tests/test_config_loading.py`: 12 passed
- 通知timeout、試行回数、retry delay/backoffの環境変数読み込みとHTTP再試行scheduleを検証
- `uv run pytest tests/test_performance_and_security.py -k audio_tagger`: 3 passed
- ConfigのFFmpeg timeoutが変換subprocessへ渡ることと、Mutagen/ffprobe既存経路を検証
- `uv run pytest tests/test_fast_track.py tests/test_apic_comm_pickup.py tests/test_batch_accuracy_improvements.py tests/test_batch_edge_cases.py tests/test_differential_alignment.py tests/test_improvements.py`: 70 passed
- Fast-TrackのMBZ補完を専用モジュールへ移した後、slot mapping・unassigned reconciliationを含む既存テストを検証
- `uv run pytest tests/test_analysis_accuracy_fixes.py tests/test_cover_artwork_priority.py tests/test_performance_and_security.py tests/test_security_phase1.py tests/test_fast_track.py`: 59 passed
- artworkのソース優先度、SSRF/サイズ制限、legacy import経路を検証
- `uv run pytest tests/test_apic_comm_pickup.py tests/test_batch_accuracy_improvements.py tests/test_batch_edge_cases.py tests/test_differential_alignment.py tests/test_improvements.py tests/test_fast_track.py`: 70 passed
- slot variant構築とTier優先ファイル選択のlegacy import経路を検証
- `uv run pytest tests/test_batch_accuracy_improvements.py tests/test_differential_alignment.py tests/test_improvement_batch_fixes.py`: 21 passed
- 未割当slot照合の一致条件とlegacy import経路を検証
- `uv run pytest tests/test_audit_accuracy_and_audio_warn.py tests/test_audit_contracts.py tests/test_batch_accuracy_improvements.py tests/test_fast_track.py`: 51 passed
- 通知payload・音声警告・legacy import経路を検証
- `uv run pytest tests/test_batch_edge_cases.py tests/test_improvement_batch_fixes.py tests/test_sanitize_and_multivariant.py`: 16 passed
- 重複variant統合、multi-disc修復、legacy import経路を検証
- `uv run pytest tests/test_runner_resilience.py tests/test_fast_track.py tests/test_batch_accuracy_improvements.py`: 45 passed
- track batchの委譲引数、Deferred copy再試行、既存track callback差し替えを検証
- `uv run pytest tests/test_fast_track.py tests/test_runner_resilience.py`: 33 passed
- alignment分岐、Fast-TrackのLLM bypass、既存class/module callback差し替えを検証
- `uv run pytest tests/test_performance_and_security.py -k pre_scanned`: 1 passed
- album contextのpre-scanned file引き渡しが再スキャンを起こさないことを検証
- `uv run pytest tests/test_runner_resilience.py`: 9 passed
- deferred-copy再試行、結果診断、package finalizer呼び出しの既存契約を検証
- `uv run pytest tests/test_batch_accuracy_improvements.py`: 12 passed
- LLM slot矛盾検査の既存policyと互換wrapperを検証
- `uv run pytest tests/test_fast_track.py`: 24 passed
- package出力生成・保存の委譲と `processor.PackageManager` patch pathを検証
- 初回全体検証: `uv run pytest` 243 passed。以降の最新結果は下記「全体検証結果」を参照。

## 全体検証結果

- 2026-10-07 最終検証: `uv run pytest -q` 261 passed、`uv run ruff check src tests scripts` 通過、`uv run pyright src/sst` 0 errors / 0 warnings、`git diff --check` 通過。
- Config単位同期、legacy migration warning、LLM retry policy、local/UTC timestampのfocused tests通過。MBZ app-name Config fieldを既存baseline値・`.env.example`・設定ガイドと整合するよう復元。
- 変更対象のMarkdown diagnostics: `configuration.md`、`data_flow_diagram.md`、`LOGIC.md`、refactor台帳は0件。`METADATA_SOURCE_SPEC.md`には変更箇所外の既存MD040/MD060警告が残る。
- 継続監査: `uv run pytest tests/test_config_loading.py -q`: 20 passed。dotenvをpytest環境変数として注入する環境でもlegacy fallbackと明示env-fileテストが分離するよう、関連環境変数をfixtureで除外。`notify.py` の既存DeprecationWarningが1件。
- 設定既定値同期: `uv run pytest tests/test_config_loading.py::test_documented_config_defaults_match_config_fields -q`: 1 passed。すべての非None Config defaultに対して、設定ガイドの記載値と一意なbulletを確認。

- `uv run pytest`: 前回基線256 passed。以後Config metadata、retry policy、timestamp testsを追加。最新の全体実行結果は本表の末尾へ追記する。
- `uv run ruff check src tests scripts`: 通過
- `uv run pyright src/sst`: 0 errors / 0 warnings。前回の27件を11 module単位のOptional narrowing、引数型、Mutagen File import修正で解消。
- 変更対象の `main.py`、`scanner.py`、`alignment_flow.py`、`llm/prematch.py`、`processor.py` を個別Pyright検査し0 errors。ConfigおよびVRAM設定の対象診断もなし。
- scanner設定伝播を含むfocused tests、Fast-Track/prematch/runner回帰37件を通過。
- 新設・更新した計画/担当文書と `docs/configuration.md`: Markdown diagnosticsなし
- README・CHANGE_HISTORY: 既存箇所を含むMarkdown書式警告あり。全体整形は今回の対象外
- `git diff --check`: 通過

全体検証と互換surface外のmethod reachability分類が完了するまで、全体リファクタリングを完了扱いにしない。
