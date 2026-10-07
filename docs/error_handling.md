# S.S.T エラーハンドリング方針

## 1. 基本方針

- No Silent Failures
- 原因不明の成功より、理由付き review を優先する
- 失敗は app_id / track_id 単位で追跡可能にする
- 元ライブラリを破壊しない

## 2. 外部データ取得失敗

### 2.1 STEAM 取得失敗

影響:

- 骨格情報が失われる
- TRCK / TIT2 / TPOS の正ソースが消える

方針:

- フォールバック可能な範囲で継続する
- ただし archive 閾値は厳しくなる
- 骨格不在が重大なら review に送る

### 2.2 ACOUSTID 失敗

方針:

- MBZ_RELEASE / MBZ_SEARCH / EMBED / LOCAL で継続する
- TPE1 の信頼度低下を明示する
- STEAM-TRUST 条件を満たさない限り archive を甘くしない

### 2.3 MusicBrainz 失敗

方針:

- STEAM と ACOUSTID が十分なら継続する
- レーベルや年など補助情報不足を理由に単独で中断しない

## 3. LLM 失敗

### 3.1 呼び出し失敗・トランケーション

- 一時的な通信エラー（HTTP 500/503、タイムアウト等）は、指数バックオフ＋ランダムジッター（±20%）を用いて `LLM_MAX_RETRIES`（既定3回）まで再試行する。
- **動的トークン天井による暴走早期打ち切り**:
  - バックエンド呼び出し時の `max_tokens` / `num_predict` には、タスク種別（identity / mapping / extraction）に応じた期待トークン予算に 25% の安全マージン（`LLM_OUTPUT_BUDGET_SAFETY_RATIO=0.25`）を加えた動的上限を設定する。
  - これにより、モデルのハルシネーションによる長文反復出力（Runaway Generation）が発生しても、期待値+25%でサーバー側が即座に打ち切り（`done_reason=length`）、長時間のソケットタイムアウト（10分等）を防止する。
- **縮退プロンプト（Adaptive Degraded Minimal Prompt）への自動適応**:
  - トランケーション（`done_reason in {"length", "max_tokens"}`）や長文起因タイムアウトによるリトライ時、温度0での同一プロンプト再生成は同じ暴走を招くため、プロンプト末尾のフォーマット指示部を「理由・思考・解説を省略し、必要最小限のキーのみを含む最小JSONを出力せよ」という縮退指示に差し替えて再試行する。
  - Prompt Cache を維持するため、プロンプト本文（Steam/MBZ/Local等のデータプレフィックス）は温存する。
  - 縮退プロンプトにより出力長を数百トークンに強制抑制し、確実に JSON を完結させて正常な判定を救出する。
- 再分割・縮退を経ても継続不能な場合は安全に review に送る。

### 3.2 構造不正

例:

- JSON 破損
- 存在しない file_id
- 同一 file_id の複数スロット割当

方針:

- バリデーションで検出する
- 自動補修で確証が得られない限り review に送る
- **早期Reviewメッセージの保全**: LLM応答欠落や事前判定ゲートによる早期Review（`handle_early_review_return`）時は、`summary_meta` に `message`（原因コードおよび理由文字列）を確実に記録し、後段の監査レポートやDBで原因が明示されるようにする。

### 3.3 低 confidence

- album_confidence, mapping_confidence, data_quality のいずれかが閾値未達なら review

## 4. ファイル処理および音声品質ハンドリング

### 4.1 変換失敗 (`audio_fail`) と 音声品質警告 (`audio_warn`) の分離

- **変換失敗 (`audio_fail`)**:
  - FFmpeg の非ゼロ終了、出力ファイル欠落、ファイルサイズ 0、タイムアウト、変換例外。
  - 変換元候補が壊れている場合は次順位フォーマットを試す。回復不能なら直ちに当該スロットまたはアルバムを Review に送る。
- **入力copy失敗 (`copy_failure`)**:
  - 共有mount等からの一時的な`OSError`は初回の有限再試行後、FFmpegへ渡さずRunnerの居残りキューに置く。
  - 通常バッチ完了後に`SST_DEFERRED_COPY_DELAY_SECONDS`（既定600秒）待機して一度だけ再試行する。保留がない場合は待たない。
  - 再試行成功後も通常の変換・Validator・Archive preflightを実施する。失敗が残った場合は再キューせず、該当AppIDを`Deferred Copy Recovery Exhausted (N)`でReview確定し、バッチの他AppIDは継続する。
- **音声品質警告 (`audio_warn`)**:
  - 変換自体は正常終了したが、FFmpeg の stderr にパケット欠落や軽微なタイムスタンプ異常などの警告が検知された状態。
  - **サイレント無視の禁止**: 本来 Archive 相当の信頼度（Fast-Track または LLM スコア充足）であっても、警告を握り潰して Archive に含めることはせず、必ず Review へ隔離する。
  - **追跡性保証**: バリデーション結果に `audio_quality_warnings=True` および対象となったトラック番号一覧（`audio_warned_tracks`）を記録し、監査レポートおよびログ上で「本来Archive相当だが微小問題を含む」旨を明示する。

### 4.2 成果物事前検証（Preflight Check）とゼロ埋め正規化契約

- **事前検証 (Preflight Check)**:
  - バリデーションで Archive 判定となった場合でも、最終 ZIP 出力直前に作業領域（`final_<AppID>_*`）の物理生成ファイルを走査し、以下を決定論的に再検査する：
    1. 期待曲数と実ファイル数の一致
    2. 全ファイルの存在およびファイルサイズ（> 0 バイト）
    3. 必須タグ（TIT2, TRCK, TPE1）の書き込み完了
    4. Steam スロットキーの完全一致
  - 不備が 1 点でもあれば直ちに Review 判定へ降格する。
- **ゼロ埋め正規化契約 (Zero-padding Normalization)**:
  - Steam ストアトラック番号（例: `"1"`）とローカルタグトラック番号（例: `"01"`）の差異に起因する偽陰性（誤った `Archive Artifact Steam Slot Mismatch` 等）を完全に排除するため、照合キー構築時に `lstrip('0') or '0'` の正規化を適用する。
  - タグ自体の書き込み値には干渉せず、照合・事前検証のみで安全に表記差を吸収する。

### 4.3 埋め込みタグ読取失敗

- 同一スロットの別フォーマットから EMBED を横断検索する
- 全滅なら EMBED 不在として次のフォールバックへ進む

## 5. コメント長超過

- COMM は UTF-16 で 2000 バイト超なら末尾タグから削る
- それでも収まらない異常ケースは review 理由に残す

## 6. Review に落とすべき代表例

- STEAM とローカル曲構造の衝突
- 50%以上のタイトルが同一で正ソース異常が疑われる
- ディスク構造が整合しない
- 必須フィールド TIT2 / TRCK / TPE1 が十分に埋まらない
- 変換元は選べても、対応スロット自体に確証がない
- 音声品質警告（`audio_warn`）を含むトラックが存在する
- アーカイブ成果物事前検証（Preflight Check）で欠落・破損・スロット不一致が検出された
- 余剰未割当ファイル（`unassigned_files`）が 1 件でも存在する

## 7. ログ要件

少なくとも次を構造化ログへ残します。

- app_id
- track_id または file_id
- source class
- confidence
- review reason
- 外部コマンド / API の失敗内容