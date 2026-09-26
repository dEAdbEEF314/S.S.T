# S.S.T 性能改善 実施手順書

## 1. 目的と適用範囲

本書は、S.S.T の全体処理時間とバッチ処理量を改善するための測定・変更・検証手順を定める。最優先条件は、Steam の構造を正本とする整列、メタデータの出典優先順位、音声品質判定、Archive 直前の物理 preflight を弱めないことである。

現時点で基準環境の実測値が揃っていないため、特定の短縮率を既成事実として扱わない。まず同一入力・同一環境で基準値を採り、各変更の効果を個別に判定する。

## 2. 現行実装から分かること

- LLM リクエストは `LLM_REQUEST_DONE` に待ち時間、所要時間、prompt/eval token 数、出力予算を記録する。LLM 結果キャッシュ、アルバム Tier、Ollama slot/VRAM に基づく並列制御も既にある。
- `JobRunner.run()` はスケジューリング用に各アルバムの音声ファイルを走査し、`LocalProcessor._init_album_context()` でもう一度走査する。これは二重走査候補だが、実測で寄与を確認してから変更する。
- `TrackManager.build_file_records()` は各音声ファイルの長さ取得に `ffprobe` を起動する。ロスレス変換時には `AudioTagger._get_audio_properties()` も別の `ffprobe` を起動する。音源数が多い場合は外部プロセス起動とディスクI/Oが候補になる。
- アルバム並列処理の内側で `max_encoding_tasks` による曲単位並列も行う。両方を同時に増やすと、FFmpeg・ディスク・メモリ・LLM backend の過負荷を招く可能性がある。
- Archive は LLM の信頼度だけでは成立せず、最終ファイル・タグ・Steam slot・件数の preflight を通過する必要がある。

これらは検証すべき仮説であり、全環境での実際のボトルネックを断定するものではない。

## 3. 不変条件と受け入れ基準

### 3.1 精度・品質の不変条件

性能改善のために次を変更してはならない。

- Archive/Review の閾値、Review へ送る条件、音声警告・失敗の扱い。
- Steam を曲順・タイトル・slot の正本とするルール、MusicBrainz/AcoustID 等の出典優先順位。
- 未知・重複・未割当slotの判定や形式variant統合の条件。
- ID3v2.3、必須タグ、音質tier、変換上限、Archive preflight。
- LLM の温度、プロンプト、出力予算、切り詰め時の再試行を速度比較のためだけに変更すること。

### 3.2 速度改善の合格基準

変更前に、プロジェクト担当者が対象環境と比較基準を記録する。初期の推奨ゲートは以下とする。

- 同一の固定入力で3回以上実行し、ウォームアップ実行を別記する。キャッシュ有効・無効の結果を混ぜない。
- バッチ総時間の中央値が10%以上短縮し、p95のアルバム処理時間が5%を超えて悪化しないこと。
- 固定入力の全件で、処理状態、Steam slot 対応、タグ必須条件、音声警告、Archive preflight 結果が基準実行と一致すること。
- 新たな不当Archive、欠落/重複slot、変換失敗、LLM切り詰め、timeout、API制限超過を発生させないこと。

データ量が少なく統計的に不安定な場合は、性能ゲートを満たしたと判断せず、計測件数を増やす。既存の実データで状態が変化した場合は差分をすべて監査し、根拠を説明できない Archive 化が1件でもあれば採用しない。

## 4. 実施手順

### フェーズ0: 実行条件を固定する

1. Git revision、Python/依存関係、OS、CPU/RAM/GPU、ストレージ、FFmpeg/ffprobe、LLM backend/model/量子化、Ollama slot 数を記録する。API利用時はモデル名と設定のみを記録し、鍵や個人情報は記録しない。
2. 代表データセットを決める。小/中/大アルバム、Fast-Track/LLM、複数形式、長尺/高解像度音源、Reviewになるケースを含める。
3. 元のSteamライブラリを書き換えない。テスト用コピー、別DB、別output/working directoryを使う。実ログ、DB、音源、資格情報をテストfixtureや公開レポートに含めない。
4. 入力ファイルの一覧とサイズ、設定、キャッシュ状態が同一であることを確認する。キャッシュ比較では新しい空キャッシュと事前暖機済みキャッシュを分ける。

### フェーズ1: 基準値を測る

1. まず全テストを実行する。

   ```bash
   uv run pytest
   ```

2. 固定データセットを各条件3回以上実行し、総経過時間、アルバム毎の中央値/p95、成功・Archive・Review・Error数、曲数、キャッシュhit率を記録する。ローカルモデルでは初回モデルロードと定常実行を分ける。
3. LLMログの `duration_seconds` / `wait_seconds` / token数と、既存の診断イベントを使い、待ち時間と実処理時間を区別する。
4. まだ処理段階別時間が取れない場合は、最初の計測改修として `time.monotonic()` による計測を追加する。最低限、scan/metadata抽出、AcoustID/MBZ、LLM各phase、変換、タグ書込み、preflight/package、DB書込みを段階別に記録する。ログは構造化し、`app_id`、stage、duration、件数を持たせる。音源パス、プロンプト本文、資格情報は性能ログへ複製しない。
5. CPU/GPU使用率、VRAM、ディスクI/O、ネットワーク/API待ち、FFmpeg/ffprobe起動数も同じ実行単位で記録し、最大の時間寄与を特定する。

### フェーズ2: 低リスクの候補を一つずつ試す

候補ごとに別ブランチまたは独立した差分として測定する。変更をまとめて投入しない。

1. **重複ファイル走査の削減**: `JobRunner` の事前走査と processor 内走査の時間を計測する。スケジューリング用件数が十分な効果を持たない場合は、Steam tracklist 件数等の既存メタデータを使った近似順序付けを比較する。スキャン結果を再利用する場合は、処理直前にファイル存在・サイズ/更新時刻を確認し、変化時の再走査経路を設ける。走査順や候補除外規則は変えない。
2. **ffprobe/メタデータI/Oの削減**: duration と音声特性取得のプロセス起動数・時間を測る。統合取得またはアルバム実行中のメモリ内メモ化を検討し、キーに実ファイル識別情報を含める。キャッシュは実行間で永続化せず、ファイル変更時の古い値利用を避ける。取得不能値の意味を変更しない。
3. **並列度の調整**: `MAX_PARALLEL_ALBUMS`、`MAX_ENCODING_TASKS`、Ollama実効slot、tier別Phase 2 workerを一つずつ変更する。LLM待ちが主因なら実効slotとRPM/TPMを超えない範囲、FFmpeg/CPUが主因ならCPU・ディスク帯域・メモリが飽和しない範囲で比較する。アルバムworker数と曲worker数の積を意識し、タイムアウト・OOM・429/5xx・Review率も同時監視する。
4. **既存キャッシュの適正利用**: LLMキャッシュの有効化とhit率を確認し、同一入力の再処理で得られる効果をcold/warm別に測る。TTL短縮やキャッシュキーの粗雑化で鮮度・同一性保証を下げない。Steam/MBZ/AcoustIDのキャッシュを新設する場合は、ソースの更新条件と無効化条件を先に仕様化する。
5. **CPU内処理**: PythonのCPUプロファイルで正規化、照合、JSON変換等が総時間の有意な割合を占めると確認できた場合だけ、アルゴリズム/データ構造改善を行う。結果の完全一致を固定fixtureで先に定義する。

候補の優先度は計測結果で決める。LLM/API待ちが支配的ならPythonから別言語へ書き換えても総時間はほぼ改善しない。FFmpeg/ffprobeやネットワーク待ちが支配的な場合も、まず起動回数・再実行・並列上限を検証する。

### フェーズ3: 言語変更を評価する

全体の書き換えは初手にしない。Python 3.12+ は既に外部処理の制御、LLM/API連携、Mutagen、SQLite、FFmpegを統合しており、コード全体の言語移行は依存ライブラリ・配布・診断・保守・精度回帰のリスクを増やす。

Rust等を検討する条件:

- フレームグラフで、CPU-boundな純Python処理が全体時間の大きな割合を占める。
- Python内の局所最適化後も性能目標未達である。
- 置換する境界を小さく切り出せ、Python版との入出力契約を固定できる。

候補順は、Rust拡張（PyO3/maturin等）でCPUホットループだけを置換し、Pythonオーケストレーションを維持する方法を第一候補とする。別プロセス/サービス化や全面移行は、単一拡張で目標を達成できない場合に限る。

比較時は固定fixtureでPython版と新実装版を並行実行し、正規化結果だけでなくslotごとの採用file、未割当理由、監査diagnostics、最終タグ値、エラー分類を比較する。全fixture一致、対象プラットフォームでのビルド/配布成功、性能ゲート合格、Python版へ戻せる切替手段がそろわなければ移行しない。

### フェーズ4: 段階展開とロールバック

1. unit/contractテストを通した後、合成fixture、sanitizedな代表アルバム、小規模バッチ、通常バッチの順に展開する。
2. 各段階で基準版との速度・精度・失敗率を比較する。Archive率上昇のみを成功と見なさず、ReviewからArchiveへ変わった全件の根拠を監査する。
3. 速度が基準未満、メトリクスが不一致、未説明の状態差、preflight差、エラー/Review増加があれば、その変更を無効化し基準設定へ戻す。閾値やvalidatorの緩和で帳尻を合わせない。
4. 採用後は変更差分、測定環境、3回以上の結果、精度差分、ロールバック方法をこの文書に追記する。

## 5. 必須検証

変更内容に応じて対象テストを追加し、少なくとも以下を通す。

```bash
uv run pytest tests/test_execution_profile.py tests/test_llm_parallelism.py tests/test_llm_cache.py
uv run pytest tests/test_fast_track.py tests/test_batch_accuracy_improvements.py tests/test_audit_contracts.py
uv run pytest tests/test_id3_tag_construction.py tests/test_archive_review_combined.py tests/test_audit_accuracy_and_audio_warn.py
uv run pytest
```

並列度やキャッシュだけの変更でも、固定入力でのslot対応・Archive preflight・音声品質警告を確認する。ファイル走査/ffprobe最適化では壊れた音源、読取不能ファイル、ファイル変更、重複形式、欠損durationをfixtureに含める。言語境界を変更する場合はPython版とのgolden比較を追加する。

## 6. 記録テンプレート

| 項目 | 記録内容 |
|---|---|
| revision / 変更 | commit hash、差分、変更した設定値 |
| 環境 | OS、CPU/RAM/GPU、ストレージ、Python、FFmpeg、backend/model |
| 入力 | 合成/sanitizedデータセットID、アルバム数、曲数、形式構成 |
| キャッシュ | cold/warm、LLM cache hit率、その他の状態 |
| 性能 | 総時間、album中央値/p95、stage別時間、CPU/GPU/VRAM、I/O |
| 品質 | Archive/Review/Error、status差分、slot/tag/preflight差分、警告/失敗 |
| 判定 | 合格/不合格、理由、ロールバック方法 |

公開レポートには匿名化した集計値と合成fixtureのみを使い、実ユーザー名、ローカルパス、資格情報、生ログ、DB、音源を含めない。

## 7. 参照資料

- [監査・中間成果物仕様](audit_and_intermediate_artifacts.md)
- [設定ガイド](configuration.md)
- [テスト観点](TEST_ENVIRONMENT.md)
- [検証を弱めない改善仕様](IMPROVEMENT_SPEC_VERIFICATION_PRESERVING.md)