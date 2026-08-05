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

### 3.1 呼び出し失敗

- 再試行可能な通信エラーなら限定的に再試行する
- 継続不能なら review に送る

### 3.2 構造不正

例:

- JSON 破損
- 存在しない file_id
- 同一 file_id の複数スロット割当

方針:

- バリデーションで検出する
- 自動補修で確証が得られない限り review に送る

### 3.3 低 confidence

- album_confidence, mapping_confidence, data_quality のいずれかが閾値未達なら review

## 4. ファイル処理失敗

### 4.1 変換失敗

- 変換元候補が壊れている場合は次順位フォーマットを試せる範囲で試す
- 回復不能なら当該スロットまたはアルバムを review に送る

### 4.2 埋め込みタグ読取失敗

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

## 7. ログ要件

少なくとも次を構造化ログへ残します。

- app_id
- track_id または file_id
- source class
- confidence
- review reason
- 外部コマンド / API の失敗内容