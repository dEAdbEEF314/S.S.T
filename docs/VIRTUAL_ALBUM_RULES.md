# 仮想アルバム (Virtual Album) 監査・統合ルール

本ドキュメントは、LLMが3つの仮想アルバム（STEAM, FINGERPRINT, LOCAL）を監査・統合する際の基準を定義します。

## 1. 監査基準 (Audit Criteria)

### 1.1 物理的証拠の最優先 (Physical First)
*   **GROUND TRUTH**: FINGERPRINT（音声指紋）の一致は物理的な事実に基づきます。
*   `physical_match_ratio` が 80% を超えている場合、メタデータの文字列に多少の差異があっても **Identity Confidence を 95% 以上** と設定してください。

### 1.2 意味的な同一性の許容 (Semantic Aliases)
以下の項目の差異は「不一致」として減点対象にしないでください。
*   **Artist**: Steamの「開発元 (Developer)」とMusicBrainzの「アーティスト/作曲家」は同一作品の異なる側面です。
*   **Label**: Steamの「販売元 (Publisher)」とMusicBrainzの「レーベル」は同一作品の異なる側面です。
*   **Year**: デジタル配信年（Steam）とCD発売年（MBZ）の数年のズレは正常な挙動です。

## 2. 統合ロジック (Consolidation Logic)

### 2.1 フィールド別優先順位
1.  **タイトル (TIT2)**: FINGERPRINT を優先し、Steamで補完する。
2.  **アーティスト (TPE1)**: FINGERPRINT のクレジットを優先する。
3.  **年 (TYER)**: 原則として Steam（公式発売日）を優先する。

### 2.2 タイトルのクリーニング
*   "01. Title" や "1- Title" のようなトラック番号の混入は、LLMが責任を持って削除（Cleaning）してください。

## 3. アーカイブ判定 (Judgement)

*   **ARCHIVE**: Identity Confidence >= 95 且つ Integrity Quality >= 90 の場合に選択。
*   **REVIEW**: 上記を満たさない場合、または内容に明らかな矛盾（全く別の作品など）を感じる場合に選択。
