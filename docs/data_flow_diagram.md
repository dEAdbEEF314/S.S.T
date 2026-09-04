# S.S.T データフロー図

## 1. 全体データフロー

```mermaid
flowchart TD
    A[AppID とローカル音源] --> B[STEAM アルバムメタデータセット構築]
    A --> C[ローカル全ファイルのシグナル収集]
    B --> D{ファストトラック条件判定<br/>ゼロ埋め正規化照合}
    C --> D
    
    %% Route 1: FAST_TRACK
    D -->|充足| E1[決定論的マッピング確定<br/>Route: FAST_TRACK]
    
    %% LLM Routes
    D -->|未達| F[LLM アライメント実行判定]
    F -->|トラック数小/中| E2[LLM One-Shot アライメント<br/>Route: LLM_ONE_SHOT]
    F -->|トラック数大/VRAM制限| E3[LLM チャンク分割アライメント<br/>Route: LLM_CHUNKED]
    
    %% Early Review
    E2 -->|アライメント完全失敗/空出力| ER[早期Review返却<br/>Route: EARLY_REVIEW]
    E3 -->|アライメント完全失敗/空出力| ER
    
    %% Post Alignment
    E1 --> G[重複解消 & 残余決定論的一意確定]
    E2 --> G
    E3 --> G
    
    G --> H[スロットごとに最高Tier音源を機械的選定]
    H --> I[EMBED 横断ピックアップ & ID3v2.3タグ構築]
    I --> J[並列音声変換 & 音声品質診断<br/>audio_warn vs audio_fail]
    
    %% Validation & STEAM-TRUST
    J --> K{結果バリデーション}
    K -->|構造完全一致かつ高品質| ST[STEAM-TRUST 昇格判定]
    K -->|閾値充足| V_OK[バリデーション合格]
    ST -->|適用| V_OK
    K -->|不合格 / audio_warn / audio_fail / 未割当| REV[Review 隔離判定]
    
    %% Preflight Check
    V_OK --> PF{成果物事前検証<br/>Preflight Check<br/>ゼロ埋め正規化スロット突合}
    PF -->|全曲存在・サイズ・タグ正常| ARCH[archive ZIP 出力]
    PF -->|欠落・破損・スロット不一致| REV
    
    ER --> REV_OUT[review ZIP / マニフェスト / レポート出力]
    REV --> REV_OUT
    ARCH --> REP[監査レポート & DB記録]
    REV_OUT --> REP
```

## 2. 5つの処理経路 (Processing Routes)

| 経路名 | 分岐条件 | 特徴 |
|---|---|---|
| **`FAST_TRACK`** | ローカル曲数とSteam曲数が一致し、全曲がトラック番号または正規化タイトルで1:1決定論的対応 | LLM不要で最高速・最高信頼度 |
| **`LLM_ONE_SHOT`** | ファストトラック未達で、コンテキスト上限に収まる規模のアルバム | 単一プロンプトで全曲の一括アライメントを実施 |
| **`LLM_CHUNKED`** | 楽曲数が多く単一プロンプトでのトークン超過またはTruncationの恐れがあるアルバム | チャンク分割＋並列処理でアライメント |
| **`STEAM_TRUST`** | ACOUSTID不在だが、異フォーマット統合後の一意トラック構造がSteamと完全一致 | 決定論的構造優位性により確信度100%としてArchive昇格 |
| **`REVIEW` / `EARLY_REVIEW`** | 早期中断、スロット未充足、余剰未割当ファイル、音声品質警告（`audio_warn`）、変換失敗、Preflight不一致 | 不確実な成果物を絶対にArchiveせず安全に隔離保存 |

## 3. 情報ソース関係とタグ採用階層

```mermaid
flowchart LR
    S[STEAM] -->|構造骨格・タイトル・トラック番号| Y[最終タグ構築]
    A[ACOUSTID] -->|最優先アーティスト TPE1 / 録音同定| Y
    R[MBZ_RELEASE] -->|補助メタデータ・年・レーベル| Y
    M[MBZ_SEARCH] -->|補助メタデータフォールバック| Y
    E[EMBED] -->|APICカバー画像・既存コメント| Y
    L[LOCAL] -->|ファイル名・構造ヒント| Y
```

## 4. 判定ゲートおよび成果物事前検証 (Preflight Check)

```mermaid
flowchart TD
    M[アライメント & 音声変換結果] --> A{音声破損 audio_fail あり?}
    A -->|Yes| R[Review 隔離]
    A -->|No| B{余剰未割当ファイルあり?}
    B -->|Yes| R
    B -->|No| C{音声警告 audio_warn あり?}
    C -->|Yes| RAW[警告付きReview 隔離<br/>audio_warned_tracks明記]
    C -->|No| D{ファストトラック成立?}
    D -->|Yes| P[Preflight 事前検証へ]
    D -->|No| E{album>=90, mapping>=80, data>=70?}
    E -->|Yes| P
    E -->|No| F{STEAM-TRUST 条件充足<br/>album>=90, mapping>=75, data>=60?}
    F -->|Yes| P
    F -->|No| R
    
    P --> G{Preflight 検査<br/>1. 成果物全ファイル存在<br/>2. ファイルサイズ>0<br/>3. 必須タグ TIT2/TRCK/TPE1 充足<br/>4. ゼロ埋め正規化スロット完全一致}
    G -->|合格| ARC[Archive ZIP 出力]
    G -->|不合格| R
```