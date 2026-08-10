# S.S.T タグ仕様

## 1. 出力形式

- Lossless 入力: AIFF (.aif)
- Lossy 入力: MP3 (.mp3) 320kbps
- ID3 バージョン: v2.3 固定
- 文字エンコーディング: UTF-16 with BOM (encoding=1)、ただし TLAN を除く
- 年フレーム: TYER を使用し、TDRC は使わない
- APIC: Front Cover (Type 3) 固定
- Review成果物では、確定できない文字列フィールドに `S.S.T Unconfirmed` を設定する。
- Review成果物で未確定の `TRCK` / `TPOS` / `TYER` は推測値を設定せず、該当フレームを省略する。
- 未確定フィールド名と理由は COMM または監査用JSONに記録する。

## 2. アルバムレベルの構築

| フィールド | 正ソース | 規則 |
|---|---|---|
| TALB | STEAM | サウンドトラック商品名 |
| TPE2 | STEAM | Developer, Publisher を重複排除せず連結 |
| TYER | STEAM | release_date から西暦 4 桁 |
| TCON | STEAM | STEAM VGM, に全ジャンルを連結 |
| TIT1 | STEAM | 親ゲーム名, Steam |
| TLAN | Config | USER_LANGUAGE を ISO 639-2 化 |

## 3. トラックレベルの骨格

| フィールド | 正ソース | 規則 |
|---|---|---|
| TRCK | STEAM | ストアトラック number |
| TIT2 | STEAM | ストアトラック title |
| TPOS | STEAM | disc、不在時は 1 |

## 4. フィールド別ルール

### 4.1 TRCK

- 正ソース: STEAM
- 異常検知: 全曲同一番号、50%以上が 0、またはトラックリスト不在
- 通常時の補助候補: ACOUSTID -> MBZ_RELEASE -> EMBED -> LOCAL
- Review時にSteam構造を確定できない場合は、補助候補を公式TRCKとして扱わない。
- LLM 介入: STEAM 曲数とローカル曲数が不一致な場合
- 出力形式: 単一整数文字列
- Reviewで確定できない場合: 空欄またはフレーム省略。`0`は未確定値の代替に使わない。

### 4.2 TIT2

- 正ソース: STEAM
- 異常検知: トラックリスト不在、または 50%以上が同一タイトル
- 通常時の補助候補: ACOUSTID -> MBZ_RELEASE -> EMBED -> LOCAL
- Review時にSteamタイトルを確定できない場合は `S.S.T Unconfirmed` を付与する。
- LLM 介入: フォールバック候補間でタイトル競合がある場合
- タイトルクリーニング: しない
- 60 文字超の Local / English 形式のみ、Local 側を採用して短縮可

### 4.3 TPE1

- 正ソース: ACOUSTID の Recording Artist Credit
- 異常検知: ヒットなし、空、Various Artists / VA のような包括名義
- フォールバック: MBZ_RELEASE -> MBZ_SEARCH -> STEAM Store Credits Artist -> STEAM Developer
- LLM 介入: ACOUSTID と MBZ_RELEASE で大きく乖離する場合
- 複数名義は , 区切りで保持する

### 4.4 TPE2

- 正ソース: STEAM の Developer, Publisher
- フォールバックなし
- Developer と Publisher が同一でも重複排除しない

### 4.5 TPOS

- 正ソース: STEAM disc
- 異常検知: ディスク情報なし
- 通常時の補助候補: EMBED -> LOCAL フォルダ構造
- Review時にDiscを確定できない場合は `TPOS` を出力しない。
- LLM 介入: ローカル構造が複数ディスクを示すのに STEAM が単一ディスクの場合
- 出力形式: n/N
- Reviewで確定できない場合: 空欄またはフレーム省略。`1/1`は未確定値の代替に使わない。

### 4.6 TYER

- 正ソース: STEAM release_date
- 異常検知: 年抽出不能
- 通常時の補助候補: MBZ_RELEASE -> MBZ_SEARCH -> EMBED
- Review時に年を確定できない場合は `TYER` を出力しない。
- Reviewで確定できない場合: 空欄またはフレーム省略。`0000`は未確定値の代替に使わない。

### 4.7 TCON

- 正ソース: STEAM のジャンル
- 異常検知: ジャンル不在
- フォールバック: 親ゲームの STEAM ジャンル -> Soundtrack

### 4.8 TIT1

- 正ソース: 親ゲーム名, Steam
- 異常検知: 親ゲーム特定不能
- フォールバック: 自商品名, Steam

### 4.9 COMM

構築式:

```text
{EMBED 既存コメント}, {STEAM 親ゲームタイトル}, {STEAM 親ゲームストアURL}, [{STEAM 親ゲームのユーザー定義タグ}]
```

- EMBED コメントは同一スロット内の全フォーマットから横断検索する
- タグ区切りは / を使う
- UTF-16 で 2000 バイト超過時は、末尾タグから順に削る

### 4.10 TLAN

- 正ソース: USER_LANGUAGE
- フォールバックなし

### 4.11 TCOM

- 正ソース: STEAM Store Credits の Composer / Music by / Soundtrack by 等
- 異常検知: Store Credits 不在またはパターン不一致
- フォールバック: ACOUSTID Artist Credit -> EMBED -> STEAM Developer

### 4.12 APIC

- 正ソース: EMBED
- 異常検知: 同一スロット内の全フォーマットに画像なし
- フォールバック: MBZ_RELEASE Cover Art Archive -> STEAM ヘッダー画像
- トラック固有アート保護のため、EMBED スロット横断ピックアップを優先する

## 5. 廃止フィールド

### 5.1 TPUB

最終タグとしては使いません。

ただし MBZ_RELEASE / MBZ_SEARCH のレーベル情報は、LLM の信頼度判断材料として保持して構いません。

## 6. 変換元と EMBED 取得元の分離

変換元ファイルと、APIC / COMM の取得元ファイルは一致しなくて構いません。

例:

- 変換元: FLAC
- APIC 取得元: MP3

この分離は仕様として許可されます。