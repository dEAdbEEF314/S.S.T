# S.S.T メタデータソース定義書「真の真」 — Draft v0.2

> **大前提**: 本システムは「Steamで購入したサウンドトラック商品」のメタデータを整備するシステムである。  
> 通常はSTEAMを正とする。ただし、対象AppIDへのMusicBrainz Releaseからの直接Steamリンクが一意であり、全ローカル音源ファイルがAcoustIDで当該Release内のRecording IDへそれぞれ一意に照合され、ローカル音源群がReleaseの全Recordingを網羅した場合に限り、そのReleaseを検証済み正本として構造・MBZ由来のタグ情報に優先する。同じRecordingを指す形式違いのファイルは同一MBZスロットのバリアントとして扱う。条件を満たさない場合はSteamを正とする従来経路を維持する。

---

## 1. 情報ソース分類（信頼度の根拠による6分類）

| ソース名 | 信頼度の根拠 | 取得元 |
| ---------- | ------------- | -------- |
| **STEAM** | Valve公式の商品登録情報 | PICS API, Steam Web API, Steamストアページ |
| **ACOUSTID** | 音声波形の物理的一致 | AcoustID API → MusicBrainz Recording 直接属性 |
| **MBZ_RELEASE** | ACOUSTIDで物理同定された Release | MusicBrainz Release API（積集合で特定） |
| **MBZ_SEARCH** | アルバム名テキスト検索 | MusicBrainz Search API + NWO Hybrid Scoring |
| **EMBED** | ファイル内蔵メタデータ | Mutagen等によるタグ読み取り |
| **LOCAL** | ファイルシステム情報 | パス・ファイル名のパース |
| **MBZ_STEAM_VERIFIED** | 対象Steam AppIDへの直接リンクと全曲のAcoustID Recording一致の積集合 | MBZ Release + AcoustID |

---

## 2. 処理フロー概要

```
┌─────────────────────────────────────────────────────────┐
│ 1. STEAMアルバムメタデータセット構築                        │
│    AppID → STEAM情報取得 → 正規アルバム構造を作成           │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ 2. 直接リンク候補の全曲検証                                 │
│    対象AppIDへのMBZ直接リンク + 全音源の一意Recording照合?  │
│    YES: MBZ Releaseの曲数・曲順・ディスクを正本化          │
│    NO : 通常のSteam正本フローを維持                         │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ 3. 物理ファイルスキャン & トラックグループ化                │
│    ローカル音源の存在確認 / トラック番号・再生時間の一次抽出  │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ 3. 決定論的 Fast-Track 先行判定 (最優先評価)             │
│    Steamスロットとファイル名・トラック番号・音源長が1:1完全一致? │
└──────┬───────────────────────────────┬──────────────────┘
       │YES (約73%のアルバム)           │NO (揺れ・バリアントあり)
       ▼                               ▼
┌──────────────────────────┐  ┌────────────────────────────────────────────┐
│ ⚡ FAST_TRACK 確定        │  │ 4. オンデマンド信号収集 & One-Shot LLM整列 │
│ ・LLM推論を完全バイパス   │  │    ・CPU並列 fpcalc による波形計算        │
│ ・artistはAPIC用MBZ_SEARCHから一意補完│  │    ・未解決トラックのみ AcoustID/MBZ 照会 │
│ ・APIC欠落時のみMBZ画像検索   │  │                                            │
│ ・照会時の所要時間はAPI依存│  │    ・Tesla V100 による One-Shot スロット整列│
└──────┬───────────────────┘  └──────────────────┬─────────────────────────┘
       │                                         │
       ▼                                         ▼
┌─────────────────────────────────────────────────────────┐
│ 5. 音源ファイル採用（機械的・絶対）                          │
│    各スロット内で最高Tierフォーマット（WAV > FLAC > MP3等）を選択 │
│    ※ LLMに拒否権なし                                      │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ 6. タグマップ構築 & 音声エンコード (CPU並列)                │
│    STEAMアルバムメタデータ + 正本フォールバック優先順位を適用  │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ 7. ResultValidator 厳格検証 → ARCHIVE or REVIEW 振り分け  │
│    ・処理経路 (Processing Route) を Discord / HTML に出力 │
└─────────────────────────────────────────────────────────┘
```

---

## 2.1 処理経路 (Pipeline Route) の定義と監査証跡

アルバム処理の透明性と監査性を担保するため、実行route、validatorの昇格経路、終端結果を区別して分類し、**「Discord通知」** および **「各アルバムZIP内の AUDIT_REPORT.html」** に明記しなければならない。`processing_route`は実行routeを示し、終端結果やvalidatorの昇格経路とは別の値である。

| 名称 | 分類 | 判定条件 | 外部API / LLMの挙動 |
| :--- | :--- | :--- | :--- |
| `MBZ_STEAM_VERIFIED` | `🔗 MBZ_STEAM_VERIFIED` | 実行route (`processing_route`) | 対象AppIDへの直接Steamリンク候補が1件だけあり、全ローカル音源ファイルが同じRelease内のRecordingへ各1件だけ一致し、ReleaseのRecording集合を網羅する場合。全トラックを照会し、MBZの曲数・順序・ディスク・曲名・Recording artist・アルバムアーティスト・年を採用する。LLMをバイパスする。通常の物理・成果物検証はすべて継続 |
| `FAST_TRACK` | `⚡ FAST_TRACK` | 実行route (`processing_route`) | Steamスロットとローカルファイル名・トラック番号・音源長が1:1完全一致。**LLM・独立AcoustID照会・通常のMBZ候補選定をバイパス**。埋め込みAPICがない場合のみMBZ_SEARCHを遅延実行し、同じ候補のtrack artistを厳格な一意一致で任意補完 |
| `LLM_ONE_SHOT` | `🧠 LLM_ONE_SHOT` | 実行route (`processing_route`) | Fast-Track不成立かつexecution profileの`prefer_one_shot=true`。profileはConfig tier境界から選ばれる。これはOne-Shot優先profileを示すroute labelであり、token budgetや安全上限による内部segment分割を否定しない |
| `LLM_CHUNKED` | `🧩 LLM_CHUNKED` | 実行route (`processing_route`) | Fast-Track不成立かつexecution profileの`prefer_one_shot=false`。chunk sizeはtoken budget等で調整される |
| `STEAM_TRUST` | `🛡️ STEAM-TRUST` | validatorの昇格経路 | Phase1 strategyがSteam-based条件に合致し、album/mapping/data confidenceが90/75/60以上の場合に通常thresholdの代替経路として使う。物理・整合性Review条件は引き続き適用 |
| `REVIEW` | `🔍 REVIEW` | 終端結果 | validatorまたはArchive preflightにReview条件が1つ以上ある場合 |
| `EARLY_REVIEW` | `🔍 EARLY_REVIEW` | 早期終端結果 (`review_phase`) | alignment後の通常検証へ進まず、早期Review返却処理が成果物を生成 |
| `SKIP_NO_AUDIO` | `⏩ SKIP_NO_AUDIO` | スキャン結果 | ディレクトリ内に音声ファイルが存在しない場合にスキップ（DB保存なし） |
| `ERROR` | `❌ ERROR` | 終端結果 | ファイル破損や致命的エラーが発生した場合にエラー記録 |

バッチ集計でFast-Track実行件数を数える場合は、実行routeの`processing_route == "FAST_TRACK"`を使用する。メッセージ文言やvalidator昇格経路の`STEAM_TRUST`から実行routeを推定してはならない。Archive事後監査はSteamのdisc/track slot集合と最終track集合を比較し、件数が同数でもmissing/unexpected slotを検出する。Steamが正規に`Unknown`を示すslotは許容し、それ以外のUnknownやtrack 0は監査対象とする。Review原因の集計は複数要因の同時存在を保持し、物理I/O、構造、未割当等の一要因へ潰してはならない。

FAST_TRACK のTPE1補完では、APIC欠落時にだけ実行される遅延MBZ_SEARCHの選択候補を再利用し、追加のAcoustID全曲走査やMBZ API要求は行わない。Steam slot titleとMBZ recording titleが正規化後に双方で一意一致し、artist-creditが存在する場合だけそのTPE1へ適用する。候補は既存の`min_mbz_search_score_threshold`を通過した場合に限り、候補選定やアルバムレベルメタデータには使わない。埋め込みAPICがある場合、候補が閾値未満の場合、一意一致しない場合、またはartist-creditがない場合はartistを補完しない。検索失敗はFAST_TRACKの成立・検証結果へ影響しない。

FAST_TRACK の APIC 例外では、埋め込み画像を先に検索し、見つからない場合にのみ MBZ_SEARCH を遅延実行する。既存の`min_mbz_search_score_threshold`を適用し、候補MBIDはカバーアート取得に使用する。候補または画像を取得できない場合はSteam画像へフォールバックする。

FAST_TRACKでは、タグ構築時に`matched_v_idx`が未設定の場合、Steamの`(disc, track_number)`と1:1で一意対応するindexだけを補完する。このindexが指すSteam titleをTIT2の正本とする。番号対応が欠落または重複する場合は推定しない。

### 2.2 MBZ_STEAM_VERIFIED の昇格条件と適用範囲

MBZの通常の検索順位やリンク加点だけでは、Steam構造を置き換えない。次の条件をすべて満たした場合だけ`MBZ_STEAM_VERIFIED`を成立させる。

1. MBZ Releaseに対象AppIDの正確なSteam Store URL (`store.steampowered.com/app/{AppID}`) が含まれ、そのRelease候補が一意である。親ゲームリンク、SteamDBリンク、部分一致URLは代用不可。
2. 直接リンク候補が見つかった場合、サンプリング設定を無視して全ローカル音源ファイルをAcoustID照会する。APIエラー、未照合、候補不在は一致として扱わない。
3. 各物理ファイルが当該ReleaseのRecording IDにちょうど1件一致すること。複数Recordingに一致するファイル、0件のファイルがあれば不成立。
4. 当該Release内のRecording IDとスロットがそれぞれ一意であり、ローカルファイル群がReleaseのRecording全体を漏れなく覆うこと。異なる形式の同一Recordingは同じMBZスロットのバリアントとして扱う。
5. 成立時はLLMを呼ばず、ファイルをRecording IDからMBZ `(disc, position)` へ割り当てる。タイトルや番号を推測・生成しない。
6. 曲名、曲順、ディスク、曲数、Recording artist、アルバム名、アルバムアーティスト、年はMBZ Releaseを優先する。Steam由来のジャンル、ゲームグルーピング、コメント、AppID、商品画像等、Releaseにない商品情報はSteamを維持する。作曲者クレジットは既存のフィールド別規則を維持する。
7. 失敗時はSteam構造を置換しない。既存のLLM/Review経路に戻し、信頼度やReview閾値を緩和しない。
8. 信頼モードでも重複slot、未割当、音声変換失敗、package/preflightの物理検証を省略しない。これらの異常は従来どおりReviewとする。

---

## 3. STEAMアルバムメタデータセットの構築

AppIDを起点に、以下のフィールドを持つ正規アルバム構造を構築する。  
これが**全処理の基準骨格**となる。

### 3.1 アルバムレベル情報

| フィールド | ソース | 構築ルール |
| ----------- | -------- | ----------- |
| アルバム名 (TALB) | 通常: STEAM / `MBZ_STEAM_VERIFIED`: MBZ_RELEASE | verified時はRelease title |
| アルバムアーティスト (TPE2) | 通常: STEAM / `MBZ_STEAM_VERIFIED`: MBZ_RELEASE | 通常は`{Developer}, {Publisher}`（重複排除しない） |
| 年 (TYER) | 通常: STEAM / `MBZ_STEAM_VERIFIED`: MBZ_RELEASE | verified時はRelease dateの西暦4桁 |
| ジャンル (TCON) | STEAM | `"STEAM VGM, "` + 全ジャンル |
| グルーピング (TIT1) | STEAM | `{親ゲーム名}, Steam` |
| 言語 (TLAN) | Config | `.env` USER_LANGUAGE → ISO 639-2 |

### 3.2 トラックレベル情報（通常はSTEAMスロット）

通常はSTEAMストアトラックリストの各エントリが1スロットとなる。`MBZ_STEAM_VERIFIED`成立時はMBZ Releaseの各Recordingをスロット正本とし、disc/position/titleを採用する。

| フィールド | ソース | 算出・正規化規則 |
| ----------- | -------- | ---------------- |
| スロット番号 | STEAM `number` | 文字列（比較時はゼロ埋め正規化） |
| 曲名 (TIT2) | STEAM `title` | 特殊エンティティを unescape |
| ディスク番号 (TPOS) | STEAM `disc`（不在時は `1`） | 整数値 |
| 再生時間 (秒) | STEAM `duration_s` | PICS `m` (分) と `s` (秒) より `int(m)*60 + int(s)` で秒換算（分情報の脱落厳禁） |

### 3.3 コメント (COMM) の構築

```
{EMBED 既存コメント（存在する場合）}, {STEAM 親ゲームタイトル}, {STEAM 親ゲームストアURL}, [{STEAM 親ゲームのユーザー定義タグ（"/ " 区切り）}]
```

UTF-16で2000バイト超の場合、末尾のタグ要素から `pop()` で調整。

### 3.4 Steamユーザータグのローカル辞書

親ゲームの`common.store_tags`は数値の`tagid`だけを提供するため、タグ名称は対象親ゲームの公式Steamストアページから取得する。取得URLの言語は`.env`の`USER_LANGUAGE`を使用し、`ja`は日本語、`en`は英語に変換する。Steamストアページに埋め込まれた`tagid`と`name`の組を抽出し、`data/steam_tags.json`へローカルキャッシュとして蓄積する。

キャッシュの運用規則は次のとおりとする。

1. 既存辞書に対象`tagid`があり、言語が一致し、最終更新から`STEAM_TAG_CACHE_REFRESH_DAYS`（既定30日）未満なら公式ページへ再問い合わせしない。
2. 未登録の`tagid`がある場合、または言語が変更された場合、対象親ゲームの公式ストアページを取得し、ページ内で取得できた全`tagid/name`を辞書へマージする。
3. 更新期限に達した場合は、既存名称を保持したまま公式ページで再検証し、名称変更があれば上書きする。ページに存在しないIDは削除せず、次回取得時の再検証対象として残す。
4. 取得失敗や名称解決不能を「Steam上にタグがない」とみなしてはならない。`store_tags`にIDがある限り、未解決状態として扱い、既存の空タグキャッシュだけを根拠に処理を確定しない。
5. キャッシュは処理対象アプリのページから段階的に育つため、Steam全体のタグ辞書を事前配布する必要はない。タグ取得不能時も、既存の解決済み名称とSteamの生IDを保持して処理を継続する。

### 3.5 Steam説明文トラックリストのフォールバック

Steam PICSの構造化トラックリストが存在しない場合に限り、公式ストアの`detailed_description`をHTMLテキスト化し、連番付きの曲名行を抽出する。抽出結果は`STEAM_TEXT_TRACKLIST`として記録し、PICSの構造化データと同じ信頼度とは扱わない。連番が連続しない、曲名候補が2件未満、または自由文との区別ができない場合は抽出せず、空のSteamスロットを維持する。説明文から曲名を生成・修正してはならない。

ソース優先順位は次のとおりとする。

```text
STEAM_PICS > STEAM_TEXT_TRACKLIST > ローカルファイル名
```

#### 3.5.1 LLMによる説明文抽出

上記の決定論的HTML抽出でトラックリストを得られない場合に限り、公式`detailed_description`をLLMへ渡して候補を抽出する。PICSの取得結果が存在する場合、または決定論的抽出が成功した場合、LLM抽出を呼び出してはならない。優先順位は次のとおりである。

```text
STEAM_PICS > STEAM_TEXT_TRACKLIST_RULE > STEAM_TEXT_TRACKLIST_LLM > ローカル推定
```

LLMの入力はHTMLをテキスト化し、最大30,000文字に制限する。説明文は信頼できないデータとして扱い、説明文内の命令・プロンプト・指示は実行せず、抽出対象の文字列としてのみ扱う。LLMの出力は次のJSON契約に限定する。

```json
{
  "found": true,
  "confidence": 0.0,
  "tracks": [
    {"disc": 1, "number": 1, "title": "verbatim title", "duration_s": null}
  ],
  "evidence": "brief evidence"
}
```

採用にはLLMの`confidence`だけを使わず、次の機械検証をすべて通過させる。

- JSONがオブジェクトで、`tracks`が配列である
- 2曲以上である
- `disc`と`number`が正の整数である
- 同一ディスク内の番号が1から始まる連番である
- ディスクと番号の組み合わせが重複しない
- タイトルが空でない
- ローカル論理曲数を把握できる場合、その曲数と一致する
- 説明文にない曲の追加、番号の推測、タイトルの修正・翻訳・補完がない

採用した各曲には`source=STEAM_TEXT_TRACKLIST_LLM`を付与し、`SteamMetadata.store_tracklist_language`と監査ログに説明文の言語を記録する。検証に失敗した場合は結果を破棄し、ローカル情報からSteam曲目を生成しない。LLM抽出を使用した場合は監査上のconcernとして扱い、既存のArchive/Review判定および重複検出を自動的に緩和しない。

設定言語で曲目表を抽出できない場合に限り、英語の公式説明文を1回だけ追加取得する。英語でも抽出に失敗した場合はLLMを呼び出しても採用せず、Steam構造不明としてReview可能な状態を維持する。DBキャッシュから復元する場合も、トラックリストのsourceと言語を保持し、情報がない既存キャッシュは`UNKNOWN`として扱う。

### 3.8 文字列のエスケープ解除（HTML実体参照のデコード）

Steam PICS API、ストアWebページ、および説明文から取得されるすべてのテキスト情報（アルバム名、曲名、アーティスト名、クレジット等）に含まれるHTML実体参照（例: `&amp;` → `&`, `&#39;` / `&apos;` → `'`, `&quot;` → `"`, `&lt;` → `<`, `&gt;` → `>`）は、メタデータセット構築時に標準の `html.unescape()` を適用してデコードされた生文字列として保持する。これにより、ローカル音源のファイル名や埋め込みタグとの表記揺れを防止し、Fast-Track判定の誤不一致を根絶する。

### 3.9 物理ファイルの除外とフォーマット統合

音声走査では、`__MACOSX`、`.DS_Store`、`._*` AppleDoubleファイル、および隠しファイルを処理対象から除外する。大文字小文字の違いも同一視する。

同一Steamスロットに複数フォーマットの物理ファイルが割り当てられた場合、それらは重複曲ではなく同一曲の候補群である。Tier優先順位に従い最高品質の1ファイルだけを変換・最終検証対象として残す。低Tierの候補を理由に`Duplicates`を発生させてはならない。最高Tier選択後の最終`tracks`配列にも1スロット1レコードだけを許可する。

### 3.10 ディスク番号の出所

ディスク番号は、PICSの`discnumber`、ローカルパスの`Disc N`/`CD N`、既定値`1`の順で決定する。PICS由来の番号は推測値ではなく、`STEAM_PICS`由来の構造情報として保持する。フラットな音源ディレクトリでも、Steamが`discnumber=3`を提供した場合は`disc_3`へ出力する。

---

## 4. シグナル収集

ローカルの全音声ファイルに対して、以下のシグナルを収集する。  
**フォーマットによる統合・グルーピングは行わない。** 全ファイルが独立した個体として扱われる。

| シグナル | 取得方法 | 備考 |
| --------- | --------- | ------ |
| フォーマット / Tier | 拡張子判定 | wav=Tier0, flac/aiff/alac=Tier1, ogg/aac/m4a=Tier2, mp3=Tier3 |
| 再生時間 | ffprobe | 秒単位 (float) |
| ファイル名トラック番号 | 正規表現 `^(\d+)` | 先頭の数字（自由文字列中間への過剰マッチは行わない） |
| ファイル名Stem | パス解析 | 拡張子除去 |
| 埋め込みタグ | Mutagen | title, artist, track_number, disc_number, comment, cover_art等 |
| ACOUSTID結果 | AcoustID API | Recording MBID, Recording title, Recording artist_credit, 関連Release上のposition |
| ディスク推定 | 埋め込みタグ or フォルダ構造 | `Disc N/`, `CD N/` パターン |

### 4.1 ACOUSTID実行の効率化

全ファイルにACOUSTIDを実行するのはAPIコスト上非効率。以下の戦略を取る：

1. **一次候補フォーマットの選定**: `カバー率（ファイル数/STEAMトラック数）× メタデータ充足度` が最高のフォーマットグループを選定
2. **一次候補のみACOUSTID実行**: 他フォーマットはSignal 2〜5 + 後段のクロスバリデーションで処理
3. **一次候補が壊滅した場合（アライメント成功率 < 50%）**: 次のフォーマットグループを昇格してACOUSTID実行

---

## 5. ファストトラック判定（LLMバイパス条件）

以下の条件を**すべて**満たす場合、LLMを呼ばずに機械的にアライメントを確定する：

| # | 条件 | 根拠 |
| --- | ------ | ------ |
| 1 | STEAMトラックリストが存在する | 正ソースが利用可能 |
| 2 | ローカルファイル数（フォーマット重複除外後）== STEAMトラック数 | 曲数完全一致 |
| 3 | 全ファイルにトラック番号または正規化タイトルがある | アライメントが自明 |
| 4 | トラック番号/正規化タイトルがSTEAMスロットと1:1で対応 | 重複・欠番・範囲外なし |
| 5 | 同一スロットに割り当てられた複数フォーマットは再生時間差 < 1.0s | フォーマット違いの物理検証 |

**フォーマット重複除外（バリアント統合）**:

- 同一の `(disc, track_number)` を持つファイル群、または正規化タイトル（HTML実体参照デコード、記号・ピリオド・空白・大文字小文字の差異を吸収）が一致し再生時間差 < 1.0s のファイル群を1つの「バリアント束」として集約する。
- 集約後のバリアント束数が STEAM トラック数と完全一致し、各スロットと 1:1 に過不足なく対応する場合に Fast-Track が成立する。
- 変換元フォーマットには、後続処理（§7）にてスロット内の最高 Tier 音源が機械的・自動的に採用される。
- **単曲アルバムのトラック番号保持**: 単曲アルバム（曲数=1）において、Steam上のトラック番号がアルバム通番（例: Track 07）である場合、ナンバリング破損と判定せず Steam のトラック番号を正本としてそのまま出力タグへ反映する。
- **監査レポート（AUDIT_REPORT.html）の整合性**: Fast-Track 判定を通過したアルバムであっても、後段のバリデーションや音声変換で REVIEW に倒れた場合は、Fast-Track 成功文言で上書きせず、実際の REVIEW 要因（音声物理破損、スロット不一致等）を明示する。

---

## 6. LLMアライメント（コア機能）

ファストトラック条件を満たさない場合に実行。  
LLMが**全ファイルをSTEAMスロットに割り当てる判断**を行う。

### 6.1 LLMの役割

| やること | やらないこと |
| --------- | ------------- |
| 各ファイルがSTEAMのどのスロットに対応するか判断 | 変換元フォーマットの選択（システムが行う） |
| 同一曲の異なるフォーマット（再生時間が近い等）の認識 | タイトルの生成・修正 |
| シグナル間の矛盾解消（文脈に基づく判断） | フォールバック先の決定（フィールド定義に従う） |
| 各割り当ての信頼度と根拠の提示 | |

### 6.3 差分推論 (Differential Alignment) 規約

長大なプロンプトによるトークン枯渇（Truncation）やスロット書き忘れを根本防止するため、以下の「差分推論」を適用する：

1. **確定スロットの機械的事前解決 (Prematch)**:
   - AcoustID / MBZ_RELEASE の完全一致、または「トラック番号 ＆ 正規化タイトルが Steam スロットと 1:1 完全一致」する自明なトラックは、LLM 呼び出し前に機械的に確定する。
2. **LLM 入力の差分化**:
   - 事前確定したスロットは LLM プロンプトから除外する。
   - LLM には **「未確定のローカルファイル」と「未充足の空き Steam スロット」のみ** を送信する。
3. **One-shot 完結 (非チャンク化)**:
   - 差分トラック数は通常数曲〜十数曲程度に収まるため、セグメント分割（並列チャンク）を行わず、1 回の短文リクエスト（One-shot）で安全・高速に完結させる。
4. **結果のマージ**:
   - LLM から返却された差分アライメント結果と、機械的確定スロットを結合して最終的なスロット割り当てを構築する。
5. **全スロット確定時の確信度保証 (Deterministic Bypass)**:
   - 全ローカルファイル（フォーマット重複除外後）が決定論的プレマッチにより過不足なく Steam スロットへ 1:1 確定した場合、マッピングの自明性に基づき `album_confidence=100`, `mapping_confidence=100`, `integrity_quality=100`, `data_quality=100`, `strategy="STEAM_BASED"`, `archive_vs_review_ratio={"archive": 100, "review": 0}` を設定し、LLM Phase 2 をバイパスして安全に Archive 判定へ引き渡す。
6. **スロットキー正規化（0-indexed / 1-indexed 互換契約）**:
   - LLM が出力する `slots` オブジェクトのキーが `"0"` で開始される 0-indexed であっても、`"1"` で開始される 1-indexed であっても、決定論的かつ安全に Steam スロットへ解決する。キー `"0"` は先頭スロット（`v_idx=0` / Steam Track 1）にマッピングされ、負のインデックス（`-1`）として拒絶・破棄してはならない。
7. **プレマッチ採番におけるマルチディスク複合ファイル名認識**:
   - ファイル名先頭が `1_1`, `2_1`, `01_01` 等のアンダースコア区切りパターンを持つ場合、前者を Disc 番号、後者を Track 番号として抽出し、先頭の Disc 番号のみを誤ってトラック番号と判定してスロット集中を招くことを防止する。

### 6.2 入力データ

```
# A. STEAMアルバム（Ground Truth）
スロット一覧: [{number, title, disc, duration(あれば)}, ...]

# B. ローカルファイル一覧（全フォーマット混在、未整列）
各ファイル: {
  id: "ファイル識別子",
  filename: "01 - Battle Theme.flac",
  format: "flac",
  tier: 1,
  duration_sec: 180.5,
  signals: {
    acoustid: {hit: true, recording_title: "Battle Theme", artist: "Koji Kondo", release_position: 1} | {hit: false},
    embedded_track_number: 1 | null,
    embedded_title: "Battle Theme" | null,
    filename_track_number: 1 | null,
    disc_estimate: 1
  }
}

# C. 補助情報
MBZ_RELEASE: {album, artist, label, year, track_count} | null
MBZ_SEARCH: {album, artist, label, year, score} | null
```

### 6.3 出力フォーマット

```json
{
  "slots": {
    "1": {
      "files": ["file_id_A", "file_id_B"],
      "confidence": 0.95,
      "reason": "ACOUSTID・トラック番号・タイトル全一致。file_Bは再生時間差0.2sでMP3版"
    },
    "2": {
      "files": ["file_id_C"],
      "confidence": 0.90,
      "reason": "..."
    }
  },
  "unassigned_files": ["file_id_X"],
  "unassigned_reason": "STEAMトラックリストに該当なし。ボーナストラックの可能性",
  "album_confidence": 90,
  "concerns": ["スロット5の割り当てはタイトル照合のみで確定、再生時間の裏付けなし"]
}
```

### 6.4 LLM呼び出し条件

| 条件 | 理由 |
|------|------|
| ファストトラック条件を満たさなかった | シグナルだけでは確定できない |
| STEAMトラックリストが不在 | 全体がフォールバック依存 |

→ **整った状態のサウンドトラックはLLMを経由せずにARCHIVEされる。LLMは「あいまいさがある場合の判断者」として機能。**

---

## 7. 音源ファイル採用（絶対ポリシー）

LLMアライメント（またはファストトラック）の結果、各STEAMスロットに1つ以上のファイルが割り当てられる。

**変換元ファイルの選択は機械的・絶対であり、LLMに拒否権はない。**

```
各スロットについて:
  割り当てられたファイル群をTier順でソート:
    Tier 0 (wav) > Tier 1 (flac, alac, aiff) > Tier 2 (ogg, aac, m4a) > Tier 3 (mp3)
    同一Tier内: wav > flac > alac > aiff（Tier 0-1）, ogg > aac > m4a（Tier 2）

  → 最上位のファイルを変換元として採用
  → Tier 0-1: AIFF (.aif) に変換
  → Tier 2-3: MP3 (.mp3) 320kbps に変換
```

### 7.1 フォーマットバリアント統合と未割当ファイル除外規則

同一アルバム内に複数フォーマット（例: FLACとMP3、WAVとMP3）が同居している場合、次の条件を満たす候補だけを同一スロットの「従属フォーマットバリアント」として統合する。

1. **異種フォーマットであること**（例: FLAC と MP3）
2. **正規化タイトルが同一曲を示すこと**（トラック番号だけの一致では統合しない）
3. 両方の再生時間が有効な場合、**差が1.0秒未満**であること
4. 複数Steam slotが同じタイトル候補となる場合は、自動統合せずReviewに残すこと

ローカルのdisc番号が欠落またはSteamと異なる場合でも、正規化タイトルが一意なSteam slotと一致し、再生時間条件も満たす異フォーマット候補は、そのSteam slotへ統合してよい。番号だけを根拠にSteam slotへ推定配置してはならない。上記条件を証明できない候補は未割当として隔離し、Reviewを維持する。

スロットに統合された従属ファイルは、最高Tierファイルの採用後に正常に解決されたものとして扱い、後段の未割当ファイル（`unassigned_files`）とはしない。同一フォーマットの別候補や、異なるタイトル・再生時間の候補は自動統合しない。

LLMが1 slotへ複数の論理タイトルを割り当てた場合、同一正規化タイトルかつ有効な再生時間差が1.0秒未満の候補群だけを一つのslot候補群として扱う。Steamタイトルと一致する候補または決定論的根拠のない矛盾候補は割当から除外し、`unassigned_files` と `contradictory_slot_assignments` に記録してReviewとする。矛盾候補を自動で他slotへ振り替えてArchiveにしてはならない。

変換後の出力パスはslotごとに一意でなければならない。同じ出力disc・変換後stem・拡張子が衝突する場合は、slot由来の安定した識別子をステージファイル名へ付ける。metadataのtrack参照が同じ出力パスを共有する場合はReviewとし、上書きを許可しない。

---

## 8. EMBEDスロット横断ピックアップ

EMBEDソースのデータが必要になった場合（APIC, COMM既存コメント等）、  
**同一STEAMスロットに割り当てられた全ファイルからフォーマット優先度順に検索**する。

```
STEAMスロットN に対してフィールドF のEMBEDデータが必要:

  for file in スロットNのファイル群（フォーマット優先度順）:
    if file の埋め込みタグにフィールドF のデータがある:
      → それを採用して終了
    else:
      → 次のファイルを試す

  全ファイルにデータなし → EMBED不在（フォールバックチェーンの次のソースへ）
```

### 例

```
スロット3 "Forest Theme" に APIC が必要:

  Tier 1: "05 - Forest.flac"  → 埋め込みアート: なし ❌
  Tier 3: "ForestTheme.mp3"   → 埋め込みアート: あり ✅ → 採用

  ※ 変換元は FLAC（最高Tier）、カバーアートは MP3 から取得
```

**フィールドごとに異なるフォーマットのファイルから取得できる。**

---

## 9. フィールド定義

各フィールドは以下の4層で定義する：

| 層 | 意味 |
| --- | --- |
| **① 正ソース** | 無条件で採用する情報源 |
| **② 異常検知** | 正ソースの値が「壊れている」と判断する条件 |
| **③ フォールバック** | 異常検知時またはデータ不在時に参照するソースの優先順位 |
| **④ LLM介入** | 機械判断では不十分で、LLMに信頼度評価を求める条件 |

---

### 9.1 TALB — アルバム名

| 層 | 定義 |
| --- | --- |
| ① | **STEAM** のサウンドトラック商品名 |
| ② | なし（商品名は必ず存在する） |
| ③ | なし |
| ④ | なし |

---

### 9.2 TRCK — トラック番号

| 層 | 定義 |
| --- | --- |
| ① | verified時: **MBZ_RELEASE** の `position`。通常: **STEAM** のストアトラックリスト内 `number` |
| ② | 全曲が同一番号 / 50%以上が `0` / トラックリスト自体が不在 |
| ③ | **ACOUSTID** → **MBZ_RELEASE** → **EMBED** → **LOCAL** |
| ④ | STEAMトラック数とローカルファイル数が不一致の場合 |

- **値の形式**: 単一整数（`"7"`）。

---

### 9.3 TIT2 — 曲名

| 層 | 定義 |
| --- | --- |
| ① | verified時: **MBZ_RELEASE** のRecording title。通常: **STEAM** のストアトラックリスト内 `title` |
| ② | トラックリスト不在 / 50%以上のタイトルが同一文字列 |
| ③ | **ACOUSTID** → **MBZ_RELEASE** → **EMBED** → **LOCAL** |
| ④ | 正ソース不在でフォールバック先が複数存在し、異なるタイトルを持つ場合 |

- **タイトルクリーニング**: 正規表現による機械的な除去は行わない（削りすぎのリスクが大きいため）。正ソース（STEAM）の値はそのまま尊重し、正ソースが異常・不在の場合はフォールバック先のタイトルをそのまま採用する。
- **長大タイトルの短縮**: `{Local} / {English}` 形式で60文字超の場合のみ `{Local}` 側を採用。

---

### 9.4 TPE1 — アーティスト

| 層 | 定義 |
| --- | --- |
| ① | verified時: **MBZ_RELEASE** のRecording artist-credit。通常: **ACOUSTID** のRecording Artist Credit |
| ② | AcoustIDヒットなし / Artist Creditが空 / `"Various Artists"`, `"VA"` 等の包括名義 |
| ③ | **MBZ_RELEASE** → **MBZ_SEARCH** → **STEAM** (Store Credits `Artist:`) → **STEAM** (`Developer`) |
| ④ | ACOUSTIDとMBZ_RELEASEでアーティスト名が大きく異なる場合 |

- **値の形式**: 複数名義は `,` 区切り。`feat.` 等のクレジット表記はRecordingのまま保持。
- **アルバム内一貫性**: 不要。トラックごとに異なるアーティストを許容（ゲーム音楽の特性＋DJ用途）。

---

### 9.5 TPE2 — アルバムアーティスト

| 層 | 定義 |
| --- | --- |
| ① | verified時: **MBZ_RELEASE** のalbum artist-credit。通常: **STEAM** の `{Developer}, {Publisher}` |
| ② | いずれかの正ソースが欠落 |
| ③ | 通常: なし。verified時にMBZ値が空ならSTEAMへフォールバック |
| ④ | なし |

- **値の形式**: 通常は`"開発元, パブリッシャー"`固定。verified時はMBZ album artist-creditを保持する。

---

### 9.6 TPOS — ディスク番号

| 層 | 定義 |
| --- | --- |
| ① | verified時: **MBZ_RELEASE** のmedium position。通常: **STEAM** のストアトラックリスト内 `disc` |
| ② | ディスク情報なし |
| ③ | **EMBED** → **LOCAL** (フォルダ構造) → デフォルト `1` |
| ④ | ローカルのフォルダ構造がマルチディスクを示唆するがSTEAMは単一ディスクの場合 |

- **値の形式**: `"n/N"` 形式（例: `"1/2"`）。

---

### 9.7 TYER — 年

| 層 | 定義 |
| --- | --- |
| ① | verified時: **MBZ_RELEASE** の`date`。通常: **STEAM** の `release_date` から西暦年4桁を抽出 |
| ② | リリース日が未定文字列 / パース不能 |
| ③ | **MBZ_RELEASE** → **MBZ_SEARCH** → **EMBED** → `"0000"` |
| ④ | なし |

- **補足**: このフィールドが示すのは「Steam上のサウンドトラック商品のリリース年」。

---

### 9.8 TCON — ジャンル

| 層 | 定義 |
| --- | --- |
| ① | `"STEAM VGM, "` + **STEAM** の全ジャンル（カンマ区切り） |
| ② | ジャンル情報なし |
| ③ | **STEAM** 親ゲームのジャンル → `"Soundtrack"` |
| ④ | なし |

---

### 9.9 TIT1 — グルーピング

| 層 | 定義 |
| --- | --- |
| ① | **STEAM** の `{親ゲーム名}, Steam` |
| ② | 親ゲームが特定できない（極めてまれ） |
| ③ | **STEAM** `{自商品名}, Steam` |
| ④ | なし |

---

### 9.10 COMM — コメント

| 層 | 定義 |
| --- | --- |
| ① | 複合構築（§3.3 参照） |
| ② | なし（常に構築可能） |
| ③ | なし |
| ④ | なし |

- **既存コメントの取得**: EMBEDスロット横断ピックアップ（§8）により、採用ファイルになくても他フォーマットから既存コメントを取得可能。

---

### 9.11 TLAN — 言語

| 層 | 定義 |
| --- | --- |
| ① | `.env` の `USER_LANGUAGE` → ISO 639-2 コード |
| ② | なし |
| ③ | なし |
| ④ | なし |

---

### 9.12 TCOM — 作曲者

| 層 | 定義 |
| --- | --- |
| ① | **STEAM** の Store Credits 内パターンマッチ (`Composer:`, `Music by`, `Music:`, `Sound by`, `Soundtrack by`) |
| ② | Store Credits にマッチするパターンなし / Store Credits 自体が不在 |
| ③ | **ACOUSTID** (Recording Artist Credit を近似使用) → **EMBED** → **STEAM** (`Developer`) |
| ④ | なし |

- **TPE1との役割分担**:
  - **TPE1**: 「この録音に誰がクレジットされているか」（ACOUSTID由来）
  - **TCOM**: 「このゲームの音楽を誰が作曲したか」（STEAM由来）

---

### 9.13 APIC — カバーアート

| 層 | 定義 |
| --- | --- |
| ① | **EMBED**（EMBEDスロット横断ピックアップにより、トラック固有アートを最優先で保護） |
| ② | **MBZ_RELEASE / MBZ_SEARCH** (Cover Art Archive) |
| ③ | **STEAM** (Steam公式ストア画像) |
| ④ | なし |

- **形式**: JPEG, Type 3 (Front Cover) 固定。
- FAST-TRACK では、ローカル埋め込み画像がない場合に限り、アート専用の MBZ_SEARCH を実行する。候補スコアの閾値を適用し、画像を取得できなければ STEAM へフォールバックする。この検索結果をタグ用メタデータ候補としては扱わない。
- **STEAM カバーアートの優先順位と排他ルール（実利・DJ運用最適化）**:
  1. **親ゲーム看板優先（単一サントラ時）**:
     - 当該サウンドトラックに親ゲーム（`parent_app_id`）が存在し、かつ **同一親ゲームに紐づくサウンドトラックがライブラリ内に1つだけの場合**、親ゲームの公式ヘッダー画像（`parent_header_image_url`）を最優先で採用する。ゲーム音楽DJ実運用において、サントラ専用の看板よりも元のゲーム本編の看板の方が一目で作品を識別しやすく実用性が高いためである。
  2. **サントラ固有看板採用（複数サントラ時または親なし）**:
     - 親ゲームが存在しない（スタンドアロンサントラ）、または **同一親ゲームに紐づくサウンドトラックがライブラリ内に2つ以上存在する場合**（例: Vol.1 / Vol.2、Remix盤、DLCサントラ等）、複数のサントラが同一の親看板になってしまう事態を避けるため、サントラ自身の公式ヘッダー画像（`header_image_url`）を採用する。
  3. **取得契約とフォールバック網**:
     - Steam Store API (`https://store.steampowered.com/api/appdetails`) のレスポンスから `header_image`（および親ゲームの `header_image`）を取得・キャッシュする。
     - ヘッダー画像の取得に失敗した場合は、カプセル画像（`capsule_image`）、Steam CDN 固定 URL (`https://cdn.akamai.steamstatic.com/steam/apps/{id}/header.jpg`)、最終手段として親ゲーム画像の順に安全にフォールバックを試みる。全ソースで取得できない場合も例外で処理を中断させず、安全に画像なしで完走する。

---

## 10. 廃止フィールド

### ~~TPUB — レーベル~~

- **タグとしては廃止**。デジタル販売のSteamサウンドトラックにおいてレーベル情報に実用的価値がないため。
- **収集は継続**: MBZ_RELEASE / MBZ_SEARCH のレーベル情報は、LLMのアライメント時の信頼度判断材料（「MBZ_RELEASEのレーベルがSteamパブリッシャーと一致 → 信頼度加点」等）として引き続き取得・提示する。

---

## 11. 信頼度スコアと閾値

### 11.1 3軸評価モデル

| 軸 | 意味 | 算出元 |
| --- | --- | --- |
| **album_confidence** | アルバム同一性の確信度 | LLMアライメント出力 / ファストトラック時はシステム算出 |
| **mapping_confidence** | トラックマッピングの品質 | LLMが出力した各スロットの信頼度の最小値 × 100 |
| **data_quality** | メタデータの充足度 | 必須フィールド（TIT2, TRCK, TPE1）の充足率 |

LLMのalbum identity confidenceは、実際に与えられたSTEAM/MBZ/ACOUSTID signalの一致と矛盾に根拠を置く。`confidence_reason`は最も強い支持根拠を、`concerns`は解消していない重要な矛盾を簡潔に記録する。ローカルファイル名の番号prefixや形式バリアントだけでidentity confidenceを下げず、Steam slot対応が解決してもartist・年・作品同一性・トラックリストの実質的矛盾は無視しない。confidenceの加点やArchive目的の閾値緩和は禁止する。

### 11.2 閾値定義

| 判定パス | album | mapping | data | 条件 |
| ---------- | ------- | --------- | ------ | ------ |
| **MBZ_STEAM_VERIFIED** | — | — | — | §2.2のRelease同定・全Recording一対一照合を満たす。信頼度しきい値は緩和せず、物理・成果物Review条件を適用 |
| **決定論的ARCHIVE** | — | — | — | ファストトラック条件充足（§5） |
| **LLM後ARCHIVE** | ≥ 90 | ≥ 80 | ≥ 70 | LLMアライメント実行後 |
| **STEAM-TRUST** | ≥ 90 | ≥ 75 | ≥ 60 | ACOUSTID不在だがSTEAM構造と一致（バリアント統合後曲数 == Steam曲数） |
| **REVIEW** | 上記いずれも不足 | | | |

- **STEAM-TRUST 構造一致判定のマルチフォーマット対応**:
  - `STEAM_BASED` における構造一致判定（`steam_count == local_count`）は、物理ファイル数ではなく**フォーマットバリアント統合後の一意トラック数（スロット数）** を基準として判定する。
  - FLAC+MP3 が混在している場合でも、バリアント統合後の曲数が Steam 曲数と一致していれば STEAM-TRUST（確信度100%化）が適用される。

### 11.2.1 トラック番号・ディスク番号のゼロ埋め正規化契約 (Zero-padding Normalization)

Steamストアトラックリストとローカルタグのトラック番号照合、重複（Duplicates）検査、および**アーカイブ出力直前の最終事前検証（Archive Artifact Preflight 検査: `_validate_archive_artifacts`）**において、以下の正規化を一貫して適用する：

- **前置ゼロの除去**: トラック番号文字列は前置ゼロを除去した数値表現（`str(track_number).split('/')[0].lstrip('0') or '0'`）に正規化して `(disc, track)` キーを構築する（ディスク番号も同様に `str(disc_number).split('/')[0].lstrip('0') or '1'`）。
- **目的**: Steam側が非ゼロ埋め（`"1"`）、ローカルタグ側がゼロ埋め（`"01"`）であることによる、バリデーション時の偽の `Steam Slots Missing` / `Steam Slots Unexpected` や、事前検証時の偽の `Archive Artifact Steam Slot Mismatch` の発生を防止し、物理構造が完全に一致している健全なアルバム（DJMAX、Evertried 等）を確実に Archive 判定へ導く。
- **安全境界**: この正規化はスロット照合キーおよび事前検証キーの整合判定のみに適用され、音声ファイルに出力されるタグ値（ID3フレーム）や物理ファイル名には一切干渉しない。

### 11.2.2 Archive正本タイトル一致検証

Archive判定前に、各最終トラックのTIT2を同じ`(disc, track)`の正本トラックリストと照合する。通常routeではSteam、`MBZ_STEAM_VERIFIED`では検証済みMBZ tracklistが正本である。照合文字列はHTML entityをunescapeし、Unicode NFKC、前後/連続空白の正規化、casefoldだけを適用する。正本タイトルの単語や句読点を削除して一致扱いにしてはならない。

- slotの正本タイトルがない場合はこの比較だけでArchive可とせず、既存のSteam Tracklist Missing等を維持する。
- 正規化後もTIT2が一致しないtrackがあれば`Official Title Mismatch (N)`をReview理由に加える。confidenceやFast-Track routeで上書きしない。
- Steam/verified MBZから得た正本タイトルは、長さやスラッシュを理由に内容を切り詰めない。
- これはタイトル/slot整合検査であり、音声波形が表示曲名と一致することを単独で証明するものではない。

### 11.2.3 タグfield provenance

各最終trackの`metadata.json.tracks[*].field_provenance`に、タグ値ごとの実採用sourceを記録する。少なくともtitle、artist、album、album_artist、year、track_number、disc_number、genre、grouping、comment、composer、language、steam_appid、APICを対象とする。アルバム単位の`metadata.json.audit.field_provenance`と`AUDIT_REPORT.html`はfield/source別件数を集計する。

- provenanceは値の出所を示すもので、値が外部世界で正しいという保証やconfidenceではない。
- fallbackは実際に選ばれたsourceを記録する。合成placeholderや未確定値は`UNKNOWN_PLACEHOLDER`等と区別する。
- sourceを特定できないfieldは`NOT_RECORDED`または`UNKNOWN`と明示する。ファイル名・host path・raw logから後付け推定しない。
- `field_provenance`はID3 tag mapから分離し、source label自体を音声tagへ書き込まない。

### 11.3 決定論的 album_confidence の算出（ファストトラック時）

| 条件 | 加点 |
| ------ | ------ |
| ACOUSTIDの積集合で単一Release特定 | +40 |
| MBZ_RELEASEにSTEAM/SteamDBリンクあり | +30 |
| STEAMトラック数 == ローカルトラック数 | +15 |
| 全トラック再生時間差 ±3秒以内 | +10 |
| ACOUSTIDヒット率 ≥ 80% | +5 |

合計が100を超えた場合は100で打ち止め。

### 11.4 未割当ファイル（Unassigned Files）の品質保証規則

本システムは「**Archive と判定された成果物はノーチェックでユーザーライブラリに追加できる**」レベルの信頼度を保証する。

- Steamスロットが100%充足（全スロットに音源ファイルが割り当てられ採用完了）している場合であっても、スロットに未割当のローカルファイル（`unassigned_files`）が存在するアルバムは、**REVIEW** 判定とする。
- ただし、同一曲の異フォーマットバリアント（§7.1）としてスロットに帰属・統合されたファイルは、未割当ファイル（`unassigned_files`）とはみなさない。
- 余剰ファイルが「正規のボーナストラック」なのか「マッピング漏れした本編ファイル」なのかを機械判断だけで過信せず、人間の監査機会を確実に残す。
- 未割当ファイル自体は `unassigned/` サブディレクトリへ隔離保存され、監査レポート（`AUDIT_REPORT.html`）において「⚠️ **Steamスロット充足（余剰未割当ファイルあり）**」と目立つバッジおよびファイル一覧を明示する。
- **未割当判定の参照整合契約**: `ResultValidator` が未割当ファイル（`Unassigned Files`）の有無を判定する際は、LLM 推論直後の未整列生データ（`alignment_res["unassigned_files"]`）ではなく、マルチフォーマットバリアント統合（§7.1）および決定論的残差確定を経た **最終的な未割当マニフェスト（`unassigned_manifest`）** を検査基準とする。スロットに採用されたトラックの別フォーマット（従属バリアント）は未割当から完全除外され、Review の判定要因とはならない。

### 11.5 LLMトークンバジェットおよび Truncation 対策・フォールバック規約

思考モデル（DeepSeek-R1 / Qwen 思考版等）やローカル LLM (Ollama) におけるトークン枯渇（`done_reason=length`）による不当な Review 落ち、およびハルシネーションによる長文生成暴走（Runaway Generation）による長時間の滞留を防止するため、以下の安全規約を設ける：

1. **動的出力トークン天井規約（Dynamic Output Budget Ceiling with Safety Margin）**:
   - バックエンド呼び出し時の `max_tokens`（LiteLLM / Gemini / OpenAI互換）および `num_predict`（Ollama）には、静的なコンテキスト最大値（`llm_cloud_max_tokens`）を一律で渡すのではなく、タスク種別（`identity`, `track_mapping`, `steam_tracklist_extraction`）および対象ユニット数（トラック数等）から算出した期待出力トークン予算（`output_budget`）に、安全マージン（既定 25%: `LLM_OUTPUT_BUDGET_SAFETY_RATIO=0.25`）を加算した天井値（`int(output_budget * 1.25)`）を動的に設定する。
   - これにより、モデルが停止トークンを出さずに長文反復出力に陥った場合でも、期待値の1.25倍（約1分強）でバックエンド側が強制打ち切り（`done_reason=length`）を行い、プロキシの長時間ソケットタイムアウト（10分等）を防止する。
2. **縮退プロンプト適応規約（Adaptive Degraded Prompt on Truncation）**:
   - トークン上限到達（`done_reason in {"length", "max_tokens"}`）、タイムアウト、または出力途切れ起因のパースエラーが発生してリトライする際、同一条件での再生成は同じ暴走を招くため、プロンプトを「縮退プロンプト（Degraded Minimal Prompt）」へ自動適応させる。
   - **Prompt Cache プレフィックスの温存**: 並列処理時や推論エンジンの KV キャッシュ効率を損なわないよう、プロンプト本文（Steam、MBZ、音響指紋、ローカル楽曲リスト等のデータプレフィックス）は完全に維持する。
   - **末尾フォーマット指示の縮退**: 末尾の `### OUTPUT FORMAT` 指示部のみを差し替え、`confidence_reason` や各スロットの `reason`、`concerns` 等の詳細解説・理由文の出力を一切禁止し、判定に必要な必須キー（信頼度数値、戦略コード、スロット配列、グローバルタグ）のみを含む最小 JSON の出力を強制する。
   - これにより、モデルは少量のトークン枠で確実に JSON オブジェクトを完結させ、LLM の知能を活かして正常に Archive 判定を救出する。
3. **リトライ設定・ランダムジッター規約**:
   - LLM 呼び出しの最大リトライ回数は環境変数 `LLM_MAX_RETRIES`（既定 3）として設定可能とする。
   - リトライ待機時間（指数バックオフ）にはランダムジッター（±20%）を付与し、並列ワーカー環境におけるリクエスト集中（Retry Storm）を抑制する。
4. **温度（temperature）の不変性**:
   - S.S.T の確証主義（再現性の保証・タグ値の創作禁止・確証不足は Review）を堅持するため、リトライ時であっても温度は常に `0.0` 固定とし、ブレ（偶然の成功）を誘発するサンプリング変更は禁止する。
5. **単一トラック分割時の決定論的フォールバック**: チャンクサイズが 1 の状態で LLM 応答が Truncation となった場合、即座に空指示として破棄せず、決定論的プレマッチ（AcoustID / MBZ_SEARCH / 番号・タイトル完全一致）からの安全なスロット復元を試みる。
6. **Identity 判定時の Steam-Trust フォールバック**: `identity`（Phase 1）判定で Truncation が発生した場合、Steam トラックリストとローカルファイル数が 1:1 完全一致していれば、`STEAM_BASED` を前提として Phase 2 へ進む。構造不一致の場合は安全側に倒して Review を維持する。
7. **LLMスロットキー解決の堅牢化契約**: LLM が `"STEAM_SLOT_0"`, `"STEAM_SLOT_1"`, `"SLOT_1"` 等のプレフィックス付きキーを出力した場合、パーサーは先頭の非数字文字を除去して数値を抽出し、スロット配列（0-indexed / 1-indexed）と安全に照合する。プロンプト出力例示においてもプレースホルダーではなく具体的な数値キー（`"1"`, `"2"`）を用いて例示する。
8. **既知identity JSON delimiter typoの限定修復**: identity応答が`Expecting ':' delimiter`で失敗し、parserのerror位置がobject key直前の`""chosen_mbz_id":`と正確に一致し、その余分なquoteを1個だけ除去した完全JSONがobjectとしてparseできる場合に限り修復してnormalizationへ渡す。修復はidentity requestだけを対象とし、`chosen_mbz_id`以外、複数修復が必要な応答、JSON末尾欠損、その他のsyntax errorを自動修復してはならない。confidence、source選択、slot、tag値は修復しない。成功時は`json_repairs`と`LLM_RESPONSE_JSON_REPAIRED`へrepair code/fieldを記録し、response本文やpromptを重複してログ出力しない。retryは修復後parseが成功した場合のみ回避される。既存Review rowは自動昇格せず、同一AppIDの再処理と通常validator/preflightでのみ結果を確定する。

### 11.6 音声変換警告（audio_warn）と物理破損（audio_fail）の監査分離規約

大音量でのリスニング環境における音質保証と監査可能性のため、音声エラーと警告の取り扱いを以下のように規定する：

1. **物理破損（audio_fail）**: FFmpeg 変換プロセスの異常終了、0バイト出力、音声ストリームの完全欠損などの致命的障害は、無条件で `CRITICAL: Audio Source Error` として **REVIEW** 判定とする（検証強度の維持）。
2. **微細フレーム異常を含む音声警告（audio_warn）**:
   - 元音源の FLAC の Rice 符号化破損（`invalid rice order` / `decode_frame() failed`）等に起因するデコード警告が発生したトラックを含むアルバムは、大音量再生時の微小ノイズ・瞬断リスクに備え、一旦 **REVIEW** 判定を維持する。
   - ただし、単なる一律の `Audio quality warning` ではなく、**「本来Archive相当（構造完全一致）だが微小問題を含むためReview送り」である旨と、該当する具体的なトラック番号（例: `Track 03, 08, 11, 17, 19`）を INFO ログ、Discord 通知、および各アルバム ZIP 内の AUDIT_REPORT.html に明記する**。
3. **仕様適合リサンプリングの非警告化**: 32-bit float から 24-bit PCM への安全なビット深度低減等、本システム仕様（24bit/48kHz 上限）に適合させるための正常なリサンプリング処理は警告（`audio_warn`）とみなさず、正常変換として扱う。

### 11.7 一時copy障害のバッチ後遅延再試行

共有ストレージ等への一時的なアクセス障害で音源copyに失敗した場合、他アルバム・他trackの通常処理を妨げず、Runner管理の居残りキューで一度だけ再試行する。

1. 初回copyは既定の有限回数で再試行する。最終失敗時はFFmpeg変換を呼ばず、trackとcopy試行記録を居残りキューへ保持する。
2. 通常のアルバム処理がすべて完了した後、`SST_DEFERRED_COPY_DELAY_SECONDS` 秒待機し、保留trackを一度だけ再処理する。既定値は600秒（10分）。保留がない場合は待機しない。値が0の場合は待機を省くが、再試行ラウンドは省略しない。
3. 遅延再試行でcopyできたtrackは、通常の変換・タグ付け・Validator・Archive Artifact Preflightへ進む。再試行成功だけでArchiveに昇格させない。
4. 再試行でcopyできないtrackは再キューしない。該当AppIDを`Deferred Copy Recovery Exhausted (N)`でReview確定し、不足slotとcopy試行を監査metadataに残す。他AppIDの処理・結果を巻き戻さず、バッチ全体は継続する。
5. `SST_DEFERRED_COPY_DELAY_SECONDS` は非負整数とし、未指定時は600秒とする。Runner後段で一度だけ消費するため、アルバムごとに待機時間を累積させない。

監査metadataには`deferred_copy_count`、`deferred_copy_success_count`、`deferred_copy_failure_count`を記録する。再試行後も失敗したcopyログは成功ログの件数上限で切り捨てず、`track_id` / `slot_key` と各試行のerror typeを保持する。

---

## 12. LLMの役割定義

| 観点 | 定義 |
| --- | --- |
| **何をするか** | 収集されたシグナルを総合的に判断し、各ファイルをSTEAMスロットに割り当てる |
| **何を判断するか** | シグナル間の矛盾解消 / 同一曲の異フォーマット認識 / 割り当ての信頼度採点 |
| **何をしないか** | 変換元フォーマットの選択 / タイトルの生成・修正 / タグ値の決定 |
| **介入タイミング** | ファストトラック条件を満たさない場合のみ |

---

## 13. 廃止される概念

| 概念 | 理由 | 代替 |
| ------ | ------ | ------ |
| **track_grouper によるフォーマット統合** | トップダウン設計により不要 | LLMアライメントが同一曲を認識 |
| **4種並列仮想アルバム** (STEAM/FINGERPRINT/MBZ_SEARCH/LOCAL) | ソースの6分類に再編 | STEAMアルバムメタデータセット + シグナル |
| **Phase 1 (Global Identity)** | アライメントに統合 | LLMアライメントの `album_confidence` |
| **Phase 2 (Sequential Mapping)** | LLMアライメントに統合 | LLMアライメントの `slots` |
| **Phase 1.5 (Coherence Map-Reduce)** | 入力データが軽量になるため不要 | — |
| **TPUB タグ** | 実用的価値なし | 信頼度判断の参考情報として収集のみ継続 |

---

## 14. 技術的制約（変更なし）

| 項目 | 仕様 |
| ------ | ------ |
| ID3バージョン | **ID3v2.3** 強制（DJ機材互換性） |
| 文字エンコーディング | **UTF-16 with BOM (encoding=1)**（TLAN除く） |
| 出力形式 | Lossless → AIFF (.aif), Lossy → MP3 (.mp3) 320kbps |
| TYER | v2.3準拠で TYER フレーム使用（TDRC不使用） |
| APIC | Type 3 (Front Cover) 固定 |
| コメント制限 | UTF-16で2000バイト超時、末尾タグ要素から `pop()` |
| セパレータ | 一般: `,` / COMM内タグ: `/` |

---

## 15. 残課題

| # | 課題 | 備考 |
| --- | ------ | ------ |
| 1 | LLMアライメントプロンプトの具体的な文面設計 | §6.2 の構造を自然言語プロンプトに変換 |
| 2 | 巨大アルバム（100曲超）でのLLMコンテキスト制限対策 | ファイル1行+STEAMスロット1行で概算300行程度、大半は収まる見込み |
| 3 | LLM出力のバリデーション層 | 同一ファイルの2スロット重複割当、存在しないファイルID参照等の構造エラー検出 |
| 4 | STEAMトラックリスト不在時のフロー詳細 | 全フィールドがフォールバックチェーンに移行、LLMアライメントは代替基準（MBZ_RELEASE等）で実行 |
| 5 | TCOM の Store Credits パターンの多言語対応 | 日本語の「作曲:」等の追加要否 |
| 6 | 音源品質制限の仕様（24bit/48kHz上限） | 現行仕様を継続（TAGGING_RULE.md §1 相当） |
