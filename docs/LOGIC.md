# S.S.T 処理ロジック

## 1. 基本原則

- 構造の正は STEAM。
- 補助ソースは STEAM の不在または異常時にのみ使う。
- LLM はアライメント担当であり、タグ値の創作担当ではない。
- 同一 STEAM スロットに複数フォーマットが割り当たっても、変換元選択は機械的に行う。
- あいまいさが残る場合は archive せず review に送る。

## 2. 処理フロー

### 2.1 STEAM アルバムメタデータセット構築

AppID を起点に次を集め、全体の骨格とします。

- アルバム名
- 開発元 / パブリッシャー
- リリース年
- 親ゲーム情報
- ジャンル
- ストア上のトラック一覧

ここで得たスロット一覧が、以後のトラック整列の基準です。

### 2.2 シグナル収集

ローカルの全音声ファイルを独立個体として扱い、次のシグナルを集めます。

- フォーマットと Tier
- 再生時間
- ファイル名由来のトラック番号
- 埋め込みタグ
- ACOUSTID 結果
- ディスク推定

この段階ではフォーマット重複の統合を行いません。

### 2.3 AcoustID の実行戦略

AcoustID は全ファイル一律ではなく、一次候補フォーマット群に対して優先実行します。

一次候補の評価軸:

- カバー率 = ファイル数 / STEAM トラック数
- メタデータ充足度

一次候補のアライメント成功率が 50% 未満なら、次点フォーマット群へ昇格します。

### 2.4 ファストトラック判定

次をすべて満たす場合、LLM を呼ばずに確定します。

1. STEAM トラックリストが存在する。
2. フォーマット重複除外後のローカル曲数が STEAM 曲数と一致する。
3. 全ファイルが、トラック番号または正規化タイトルで一意にSTEAMスロットへ対応する。
4. 対応はSTEAMスロットと 1:1 で、未割当・欠落・STEAM範囲外を残さない。
5. 同一トラック番号の複数フォーマット間で再生時間差が 1.0 秒未満である。

フォーマット重複除外とは、同一トラック番号かつ再生時間差 1.0 秒未満の群を 1 曲として数えることです。

### 2.5 LLM アライメント

ファストトラック条件を満たさない場合にのみ、LLM が各ファイルを STEAM スロットへ割り当てます。

LLM が行うこと:

- スロットへの割り当て
- 同一曲の異フォーマット認識
- シグナル矛盾の解消
- confidence と reason の出力

LLM が行わないこと:

- 変換元ファイルの選択
- タイトルの生成や修正
- フィールドごとの最終フォールバック決定

LLM 出力は少なくとも次を持つ前提です。

- slots
- unassigned_files
- unassigned_reason
- album_confidence
- concerns

### 2.6 変換元ファイルの選択

各スロットに割り当てられたファイル群は、次の固定優先度で並べます。

- Tier 0: wav
- Tier 1: flac > alac > aiff
- Tier 2: ogg > aac > m4a
- Tier 3: mp3

採用ポリシー:

- Lossless 系は AIFF へ変換
- Lossy 系は MP3 320kbps へ変換
- LLM に拒否権はない

### 2.7 EMBED スロット横断ピックアップ

APIC や既存 COMMENT のように EMBED が必要な場合、同一 STEAM スロットに割り当てられた全ファイルから、フォーマット優先度順に検索します。

このため、変換元が FLAC でも APIC は MP3 から採れる場合があります。

### 2.8 タグ構築

最終タグは STEAM 骨格に各フィールドのフォールバック規則を適用して構築します。詳細は [docs/TAGGING_RULE.md](docs/TAGGING_RULE.md) を参照してください。

### 2.9 判定

判定パスは次の 4 種です。

- 決定論的 ARCHIVE: ファストトラック成立
- LLM 後 ARCHIVE: album >= 90, mapping >= 80, data >= 70
- STEAM-TRUST: album >= 90, mapping >= 75, data >= 60
- REVIEW: 上記以外

最終判定の強制Review条件:

- STEAMトラックリストが空。
- 最終tracksにSTEAM slotの欠落または範囲外slotがある。
- LLMまたは決定論的整列に未割当ファイルが1件以上ある。
- これらはconfidenceやSTEAM-TRUST文字列によって上書きしてはならない。

指標の意味:

- album_confidence: アルバム同一性
- mapping_confidence: トラック整列の品質
- data_quality: 必須フィールド充足率

### 2.10 STEAM トラックリスト不在時

STEAM の曲構造が不在な場合でも処理は継続できますが、全フィールドがフォールバック依存になります。

この場合:

- TRCK / TIT2 / TPOS の正ソースが失われる
- LLM アライメントは MBZ_RELEASE や MBZ_SEARCH を代替骨格として扱う
- archive より review に寄りやすくなる

### 2.11 `--force` 再処理

`--force` は対象を新規処理として扱う再取得・再評価モードである。処理開始前に、対象AppIDの既存中間生成物だけを`SST_WORKING_DIR`から削除する。

- 削除対象は `final_<AppID>_*` と `buffer_<AppID>_*` に限る。
- `--appid`指定時は指定AppIDだけを対象とする。
- `--appid`なしでは今回のスキャン対象AppIDを確定してから対象を決める。
- 他AppIDの中間生成物、元ライブラリの音源、`output/`のZIPは削除しない。
- singleton lock取得後、音声処理開始前に実行する。
- `--dev`でも旧試行を削除し、今回の試行成果物だけを保持する。
- 削除件数と対象AppIDを構造化ログへ記録する。

### 2.12 未割当file IDの隔離

LLMの`alignment_res.unassigned_files`は、track groupの有無ではなくfile IDを正として扱う。未割当file IDは全件を物理候補へ逆引きし、同一未割当論理群からTier最高の1ファイルを選出して変換し、`unassigned/`へ隔離する。

- 未割当file IDが1件でもあれば必ずReview。
- `metadata.json`と`review_manifest.json`の未割当件数はalignmentの未割当件数と一致させる。
- 対応する物理候補が見つからないfile IDは、隔離失敗理由をmanifestへ記録する。
- 未割当音源の既存タグは保持し、S.S.Tの未確定マーカーと理由を追加する。

## 3. 信頼度計算

### 3.1 mapping_confidence

LLM 出力各スロットの confidence の最小値 × 100 です。

### 3.2 data_quality

必須フィールド TIT2, TRCK, TPE1 の充足率です。

### 3.3 ファストトラック時の album_confidence

次を加点し、100 を上限とします。

- ACOUSTID 積集合で単一 Release 特定: +40
- MBZ_RELEASE に Steam / SteamDB リンクあり: +30
- STEAM 曲数 == ローカル曲数: +15
- 全トラック再生時間差が ±3 秒以内: +10
- ACOUSTID ヒット率 80% 以上: +5

## 4. 成果物と失敗時の安全ゲート

### 4.1 LLM入力・出力

Steamストア説明文など外部由来のテキストは不信データとして扱う。説明文内の命令やプロンプトは実行せず、LLMは既存シグナルの整列だけを行う。LLM出力はJSON契約に限定し、`file_id`、`matched_v_idx`、スロット、actionの参照範囲、重複、未割当、文字列長をコード側で検証する。検証不能な出力はReviewとする。

### 4.2 Archive判定

LLMのconfidence値だけでArchiveしない。Archiveには、Steamトラックリストの存在、Steamスロットの完全被覆、出力曲数一致、重複・未割当なし、必須タグ充足、音声変換失敗なしを決定論的に要求する。`STEAM-TRUST`とfast-trackも、この物理条件を満たす場合に限る。

### 4.3 FFmpegと中間生成物

FFmpegの非ゼロ終了、出力ファイル欠落・サイズ0、タイムアウト、変換例外は音声処理失敗としてReviewへ送る。stderrの既知警告もReviewへ送る。通常のINFO運用では処理完了後に`SST_WORKING_DIR`の`final_<AppID>_*`と`buffer_<AppID>_*`を削除し、DEBUGまたは`--dev`では診断のため保持する。

### 4.4 Archive前の成果物再検証

Archive判定時は、`final_<AppID>_*`内の生成ファイルを再走査し、期待曲数・各ファイルの存在・サイズ・タグ（少なくともTIT2/TRCK/TPE1）を確認する。検証失敗時はZIPをArchiveへ保存せずReviewへ降格する。

## 5. 実装上の禁止事項

- LLM にメタデータを発明させない
- Bandcamp 系リリースを MBZ の優先候補にしない
- MusicBrainz tie-break で Digital Media 優先を崩さない
- 元ライブラリにタグを書き戻さない
- 確証不十分なアルバムを黙って archive しない