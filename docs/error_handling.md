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

- 一時的な通信エラー（HTTP 500/503、タイムアウト等）は限定的に再試行する。
- バックエンド出力上限到達によるトランケーション（`done_reason in {"length", "max_tokens"}`）は、温度0において同一条件でのリトライが無意味であるため即時中止し、チャンクサイズ半減による再分割（`_is_truncation_log`）へ即時遷移する。
- 継続不能なら review に送る。

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