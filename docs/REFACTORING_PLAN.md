# S.S.T 全体リファクタリング計画

## 1. 目的と前提

この計画は、次の4点を対象にする。

1. 未使用コード・退役コードの削除
2. ハードコードされた値の洗い出しと設定集約
3. 巨大スクリプト・モジュールの責務分割
4. 実装と仕様書・運用ドキュメントの乖離把握と解消

最優先の不変条件は、`docs/METADATA_SOURCE_SPEC.md`、`docs/TAGGING_RULE.md`、`docs/LOGIC.md` に記載された安全ゲートを弱めないこととする。特に STEAM を構造の正とすること、未割当・欠落・音声異常を Review に送ること、LLM にタグ値を創作させないこと、物理成果物を事前検証することは、リファクタリング後も契約テストで固定する。

既存ワークツリーには `GEMINI.md` の変更があるため、この計画ではその変更を上書きしない。また `data/`、`logs/`、`output/`、`sst-work/` の実データを削除対象にしない。

## 2. 現状の根拠

2026-10-07 時点で確認できた基線は次のとおり。

| 観点 | 現状 | 計画上の意味 |
| --- | --- | --- |
| テスト | `uv run pytest --collect-only -q` で 237 tests collected | 変更前の契約基線として保存する。README の「166件」は更新対象 |
| 静的解析 | Ruff が未使用 import を複数検出 | 小さな削除作業の最初の候補。ただし全削除の根拠にはしない |
| 最大モジュール | `processor.py` 1,341行、`llm/organizer.py` 1,221行、`processor_support.py` 885行 | 責務別分割の第一候補 |
| その他の大型モジュール | `report_generator.py` 565行、`llm/client.py` 534行、`main.py` 357行、`scanner.py` 357行 | 第二段階の分割候補 |
| 設定 | `Config`、`.env.example`、各モジュールの既定値、文書に分散 | 設定の単一所有者を作る必要がある |
| 運用コード | `scripts/` と `skills/` にDB・レポート・再テスト用コードが存在 | CLI本体と運用ツールを分け、到達性を明示する |
| ドキュメント | 現行文書と `docs/archive/` が併存。README に古いテスト件数が残る | 正本・履歴・アーカイブの役割を明確化する |

### 2.1 乖離候補と初回対応状況

以下は実装と文書の差分台帳に登録し、修正前に実測値を再確認する。

- worker並列数は `Config` 未指定時が `4`、`.env.example` の明示値が `2`。設定書はこの二つを区別するよう更新済み。
- MusicBrainzのトラック数ペナルティは、`Config` だけが `300` / `2000` で、識別器既定値・`.env.example`・設定書は `20` / `300`。`Config` の既定値を `20` / `300` に統一し、回帰テストを追加済み。
- `README.md` の固定テスト件数 `166` は削除済み。初回基線は 237 tests collected / 237 passed。
- `main.py` は Steam userdata timeout `10` 秒、`data/`、`logs/`、`data/sst.lock`、`data/sst_cache.json` などを直接決めている。設定仕様との所有境界を整理する。
- `Config` に `llm_num_ctx` と `llm_ollama_num_ctx` が併存し、旧設定互換項目も残っている。どれを正本とするかを決める。
- `docs/LOGIC.md`、`docs/TAGGING_RULE.md`、`docs/METADATA_SOURCE_SPEC.md` が重複して処理契約を記述している。相互矛盾がないか機械的な用語・閾値表を作る。
- `docs/data_flow_diagram.md`、README、実装の処理経路名と分岐条件を一致させる。

実装の進捗・未完了項目は [docs/refactor/IMPLEMENTATION_STATUS.md](refactor/IMPLEMENTATION_STATUS.md) を参照する。

## 3. 作業順序

### Phase 0: 現状固定と保護線の作成

**目的:** リファクタリング前後の挙動を比較できる状態を作る。

作業:

- `uv run pytest`、`uv run ruff check src tests scripts`、型チェックの実行結果を保存する。
- CLI の主要経路を合成データで確認する。少なくとも Fast-Track、LLM後Archive、Review、未割当、音声警告、Preflight失敗を含める。
- テストを契約単位に分類する。
  - Steamスロット・タグ正本
  - LLM JSON検証・未割当
  - 変換・物理ファイル・ZIP
  - Archive/Review判定
  - 設定読み込み・セキュリティ
- 本番の `data/`、音源、キャッシュ、ログをテストfixtureへ持ち込まない。既存のモック・合成データを基礎にする。
- `docs/refactor/` に差分台帳のテンプレートを作り、項目ごとに「正本」「実装箇所」「影響」「修正方針」「検証」を記録する。

完了条件:

- 変更前のテスト収集数と検証コマンドが記録されている。
- 主要なArchive/Review契約を再現するテストが存在する。
- 実行データを変更せずに再現できる。

### Phase 1: 未使用・退役コードの棚卸しと削除

**目的:** 参照されていないコードを、仕様を変えずに減らす。

調査手順:

1. Python importグラフを作り、`src/sst/main.py`、パッケージ公開API、CLIエントリポイントから到達可能なモジュールを特定する。
2. 関数・クラスごとに、静的参照、テスト参照、動的import、設定名による参照、スクリプトからの参照を確認する。
3. `pass` は削除候補とみなさない。例外時の意図的無視、任意フィールドの不正値スキップ、未実装処理を分類し、未実装なら明示的なエラーまたは仕様に沿った処理へ変更する。
4. 旧仕様互換項目、旧CLIオプション、`docs/archive` 専用のコード、手動運用スクリプトをそれぞれ別の分類にする。
5. 候補を「削除」「非推奨警告を付けて残す」「運用ツールとして残す」「未使用とは断定できない」に分ける。

初期候補:

- Ruff が検出した未使用 import。
- `main.py` から直接到達しないが、実行スクリプトから参照されるコードを含む運用補助経路。
- `Config` の互換設定と、`LLMOrganizer` / `LLMClient` の `kwargs` 受け渡しで実際に消費されていない引数。

削除手順:

- 1変更1責務で削除し、各変更後に対象テストと全テストを実行する。
- 公開・運用上の参照が不明なものは先に非推奨化し、1リリース相当の観測期間後に削除する。
- 削除した項目を `CHANGE_HISTORY.md` に記録する。

完了条件:

- 削除対象に参照調査の証跡がある。
- 未使用 import、死んだ分岐、到達不能な旧経路がゼロになる。
- 削除前後で契約テストの結果とCLIの終了分類が変わらない。

### Phase 2: ハードコード値の棚卸しと設定集約

**目的:** 環境差・性能差・外部接続差を、追跡可能な設定として管理する。ただし仕様上固定すべき値は設定化しない。

分類:

- **設定化する:** URL、timeout、retry、並列数、パス、モデル名、ログ出力先、キャッシュTTL、外部API制限。
- **コード定数として残す:** ID3v2.3の固定仕様、音声Tierの固定優先度、Review安全ゲート、1秒未満などの契約閾値。残す場合も名前付き定数と仕様書参照を付ける。
- **入力由来として残す:** Steamのトラック番号、外部レスポンスの値、ユーザー指定AppID。
- **テスト専用:** `localhost`、ダミーAPIキー、合成ログ。実環境値と混同しない命名にする。

実施内容:

- `Config` を唯一の設定所有者とし、`main.py` の timeout、ログディレクトリ、lock、cache、userdata出力先を明示的な設定へ移す。
- 各設定について、フィールド名、環境変数名、型、既定値、許容範囲、秘密情報かどうかを表にする。
- `.env.example` を `Config` から生成または検証できる形にし、手書き定義の重複を減らす。
- `Config.load_env_overrides()` の手動変換を縮小し、Pydantic Settingsの型検証を経路の正本にする。
- `LLM_NUM_CTX` と `LLM_OLLAMA_NUM_CTX`、`metadata_source_priority` と `metadata_field_fallback_priority` の互換方針を決定し、旧名を残す期間と警告を定義する。
- 設定値の文書を自動検証する。少なくとも未記載キー、コードにないキー、既定値の不一致、単位の不一致を検出する。

検証:

- 最小設定、完全設定、型不正、範囲外、秘密情報のログ漏えいをテストする。
- 設定なしでコード内部の暗黙既定値に戻る経路がないことを検索・テストする。
- 本番接続を行わず、合成設定で各コンポーネントが同じ値を受け取ることを確認する。

### Phase 3: 巨大モジュールの分割

**目的:** 挙動を維持したまま責務境界を明確にし、テスト可能性を上げる。

#### 3.1 `processor.py` 1,341行

現状はオーケストレーション、Fast-Track判定、後処理、作業ディレクトリ、遅延copy、成果物生成が集中している。次の境界に分ける。

- `processing/orchestrator.py`: アルバム処理の順序と依存性注入
- `processing/fast_track.py`: Steam slotとローカルvariantの決定論的判定
- `processing/working_files.py`: force cleanup、作業ディレクトリ、遅延copy
- `processing/enrichment.py`: artwork、通知、MBZ補完
- `processing/result_builder.py`: 最終結果と監査データの組み立て

`LocalProcessor` は当初ファサードとして残し、既存の呼び出し元とテストのAPIを壊さない。分割後に内部依存を段階的にコンストラクタ注入へ移す。

#### 3.2 `llm/organizer.py` 1,221行

- `llm/tracklist_extractor.py`: Steam説明文からのtracklist抽出と検証
- `llm/alignment.py`: one-shot/chunked alignmentとslot解決
- `llm/normalization.py`: LLM出力の正規化・互換形式処理
- `llm/coherence.py`: segment参照と大型アルバムの整合性処理
- `llm/organizer.py`: 外部公開用の薄い調停層

JSONスキーマと未割当file IDの安全検証は分割後も一箇所に集約する。

#### 3.3 `processor_support.py` 885行

- `processing/slot_variants.py`: slot/variant index、重複統合
- `processing/file_selection.py`: Tier優先の変換元選択
- `processing/artwork.py`: EMBED→MBZ→STEAMの画像取得
- `processing/unassigned.py`: 未割当の逆引き・隔離・manifest
- `processing/notifications.py`: 通知送信

#### 3.4 第二段階

- `report_generator.py`: HTMLテンプレート、batch集計、監査データ整形を分離。
- `llm/client.py`: backend adapter、retry/rate-limit、response parsing、progress/auditを分離。
- `main.py`: CLI引数、起動準備、実行サービス、終了サマリーを分離。
- `scanner.py`: Steam discovery、API取得、cache、tracklist extractionを分離。

分割ルール:

- 先に characterization test を追加し、移動後に同じテストを実行する。
- 各分割で循環importを作らない。依存方向は `models/config` → domain service → orchestration → CLI とする。
- 大規模な同時リネームを避け、公開名は互換shim経由で段階移行する。
- 各段階で `uv run pytest`、Ruff、型チェックを実行する。

### Phase 4: 仕様書・ドキュメントの正規化

**目的:** 読者が一つの正しい仕様に到達し、実装変更時に自動的に乖離を検知できるようにする。

文書の役割を次のように固定する。

- `docs/METADATA_SOURCE_SPEC.md`: データソース、優先順位、Review安全ゲートの正本
- `docs/TAGGING_RULE.md`: ID3タグと出力成果物の正本
- `docs/LOGIC.md`: 処理フロー、判定、LLMの責務の正本
- `docs/configuration.md`: 設定キー・型・既定値・単位の正本
- `docs/DEPLOYMENT_GUIDE_jp.md`: 外部サービスと運用手順
- `README.md`: 導入導線と短い概要。閾値・件数・詳細仕様を重複記載しない
- `docs/archive/`: 歴史資料。現行リンクと混同しない明示ラベルを付ける

差分台帳の項目:

| ID | 分類 | 正本 | 実装 | 現行記載 | 判定 | 検証 |
| --- | --- | --- | --- | --- | --- | --- |
| DOC-001 | 設定既定値 | `Config` | `src/sst/config.py` | `docs/configuration.md` | 要修正 | 設定値比較テスト |
| DOC-002 | テスト件数 | CI/pytest結果 | `tests/` | `README.md` | 要更新 | collect-only |
| DOC-003 | 処理経路 | `docs/LOGIC.md` | `processor`/`validator` | README/flow図 | 要照合 | 合成ケース |
| DOC-004 | タグ優先順位 | `docs/TAGGING_RULE.md` | `builder`/`processor_support` | README/metadata spec | 要照合 | タグ契約テスト |

完了条件:

- 閾値・既定値・環境変数名が一つの正本と自動チェックで一致する。
- README の実測件数や性能主張に測定日・測定条件がある。
- アーカイブ文書が現行仕様として引用されない。
- Mermaid図のノード名・経路名が実装の処理経路と一致する。

## 4. 実施順序とリリース単位

1. **保護線:** Phase 0。コード挙動は変更しない。
2. **低リスク清掃:** 未使用 import、明確な到達不能コード、文書の明白な誤記。
3. **設定集約:** 互換読み込みを保ったまま、設定表と検証を先に追加する。
4. **小さな分割:** `processor_support.py` の責務分割から開始し、`processor.py` と `llm/organizer.py` へ進む。
5. **CLI・backend分割:** 外部挙動を固定した後に第二段階を実施する。
6. **仕様正規化:** 各実装変更の直後に差分台帳を更新し、最後に重複記述を削る。

各リリース単位で、次を必須とする。

- 変更対象と不変条件の記録
- 対象テスト、全テスト、Ruff、型チェックの結果
- CLI dry-run または合成データによるArchive/Review分類の比較
- 設定キー・文書差分の検証結果
- 削除したコード・互換shim・非推奨項目の変更履歴

## 5. リスクと対策

| リスク | 対策 |
| --- | --- |
| 動的importや手動スクリプト経由のコードを未使用と誤判定 | importグラフだけで決めず、CLI、scripts、skills、設定、テストを含む到達性調査を行う |
| Fast-TrackやReviewゲートが分割中に弱くなる | 既存の契約テストを先に固定し、未割当・欠落・音声異常の否定テストを必須にする |
| 設定名の整理で既存`.env`が壊れる | 旧名の読み込みと警告を一定期間維持し、移行表を文書化する |
| LLM出力の互換形式を壊す | 正規化層を独立させ、JSON schema相当の入力テストを維持する |
| 仕様書を更新して実装の誤りを隠す | 先にコード・テスト・実測を正本候補として比較し、仕様変更は別の意思決定として承認する |
| 実データ・秘密情報をテストへ取り込む | 合成fixture、モック外部API、秘匿済みログだけを使う |

## 6. 最終完了基準

- 未使用コードの削除候補に根拠があり、削除後の到達性とテストが確認済み。
- 実行条件に関わるハードコード値が設定または名前付き不変定数へ分類されている。
- 1,000行超のオーケストレーション・ドメイン処理が責務別モジュールへ分かれ、公開互換層が薄くなっている。
- 仕様書の正本、設定表、README、データフロー図の役割が重複しない。
- 変更前後でArchive/Review判定、タグ優先順位、物理成果物の安全ゲートが一致する。
- `uv run pytest`、`uv run ruff check src tests scripts`、型チェック、設定文書検証が再現可能である。
