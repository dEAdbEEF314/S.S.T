# LLM推論基準の最適化による精度向上案

> 注記: 本書は検証時点の提案メモ（歴史資料）です。現行の正式仕様は `docs/LOGIC.md` と `docs/Virtual_Album.md` を参照してください。

## 1. 現状の課題分析
プロトタイプ実行の結果、LLM（7Bモデル）が以下のケースでスコアを低く見積もり（75〜85点）、自動アーカイブを断念する傾向が見られました。

1.  **意味的な同一性の誤認**:
    *   STEAMの「開発者名」とFINGERPRINTの「作曲家名」が異なる場合に「不一致」と判定される。
    *   STEAMの「発売年」とFINGERPRINTの「CD再販年」が数年ずれている場合に減点される。
2.  **不完全なデータの過剰な重み付け**:
    *   STEAMのトラックリストが空（`tracks: []`）の場合、FINGERPRINTに正解があっても「確証がない」としてスコアを下げてしまう。
3.  **トークンの無駄と推論の迷い**:
    *   プロンプトに構造化 JSON をそのまま流し込んでいるため、LLMが「データの比較」という事務作業にリソースを割き、最終的な「監査判断」が甘くなっている。

## 2. 精度向上のための3つの施策

### ① Python側での「決定論的ヒント」の事前付与
LLMに丸投げするのではなく、Python側で計算可能な「物理的な確証」をプロンプトの最上部に明示します。
*   **物理的証拠 (Physical Evidence)**: 「ローカルファイルの総再生時間がMusicBrainzのデータと99%一致している」などの事実を、`SYSTEM_HINT` として注入。
*   **信頼の継承**: FINGERPRINTが物理的に一致している場合、「Metadata differences between sources are secondary to the physical waveform match.」と明示的に指示。

### ② セマンティック・アンカー（意味的紐付け）の教育
Steam VGM特有の慣習をプロンプト内で「公式ルール」として再定義します。
*   **Artist == Developer**: 「If STEAM[Artist] is a game developer and FINGERPRINT[Artist] is a person, treat them as the same identity.」
*   **Label == Publisher**: 「If FINGERPRINT[Label] is null, adopt STEAM[Publisher] with 100% confidence.」

### ③ プロンプトの極限スリム化（効率化）
LLMが処理すべき情報を「差異（Diff）」に集中させます。
*   **重複情報の削除**: （当時）3つの仮想アルバムで共通している項目（例：アルバム名が完全一致）は、「一致項目」として要約し、生JSONからは除外してトークンを節約。
*   **サンプリングの知能化**: トラックリストが空のソースがある場合、そのソースを「比較対象」から外すよう指示。

## 3. 具体的な実装変更案

### `llm.py` のプロンプトテンプレート変更
```python
### [MASTER AUDIT GUIDELINE]
1. GROUND TRUTH: FINGERPRINT (AcoustID) matches are based on physical waveforms. 
   If FINGERPRINT exists, prioritize its track titles and credits.
2. IDENTITY ALIASES: Developer (Steam) == Artist (MBZ), Publisher (Steam) == Label (MBZ).
3. YEAR FLEXIBILITY: A +/- 5 year difference between Store and Physical release is NORMAL.
```

### `processor.py` でのヒント注入
```python
# FINGERPRINT構築時に計算した「確からしさ」をLLMに伝える
v_fingerprint["match_confidence"] = "HIGH (Duration-based Perfect Match)"
```

## 4. 期待される効果
*   **自動アーカイブ率の向上**: 現在の 0%（検証時）から、安定して **60%〜80%** 程度まで引き上げられると予想されます。
*   **レビューコストの削減**: LLMの `confidence_reason` がより具体的になり、人間がチェックする際も判断しやすくなります。
*   **処理の高速化**: プロンプトの軽量化（10〜20%削減）により、推論のレイテンシが低下します。
