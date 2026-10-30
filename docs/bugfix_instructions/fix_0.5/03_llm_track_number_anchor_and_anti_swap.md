# 修正指示書 03: LLM マッピングプロンプトにおけるトラック番号アンカー保護とスワップ抑止

## 1. 背景と課題

AppID `466530`（Koihime Enbu Original Sound Track）において、LLM が `13_Sonken.flac` と `14_Kannei.flac` の割り当てにおいて、ファイル名先頭のトラック番号（13, 14）およびローマ字タイトル（Sonken=孫権, Kannei=甘寧）の明らかな対応関係が存在するにもかかわらず、わずかな再生時間差（214秒 vs 211秒等）のみに引っ張られてスロットをスワップ（逆転）して割り当ててしまった。
（なお、本アルバムはスロット20の欠落により正常に Review 送りとなっており、誤Archiveは防がれているが、LLM推論の安定性向上が課題となっている。）

## 2. 解決方針

LLM Phase 2 のプロンプト構築関数（`build_differential_mapping_prompt` および `build_mapping_prompt`）の RULES セクションにおいて、以下の指示を明文化する：
- ファイル名にトラック番号が含まれており、それが Steam スロットのトラック番号と一致している場合、微小な再生時間差（数秒程度の差はマスタリングや無音領域の差異による正常な範囲）よりもトラック番号の一致を優先すること。
- 微小な再生時間差のみを根拠に、トラック番号が一致している隣接曲同士をスワップ（入れ替え）して割り当ててはならない。

## 3. 実装詳細

### `src/sst/llm/prompts.py`

`build_differential_mapping_prompt` および `build_mapping_prompt` の RULES に以下を追加：

```text
7. When file names contain track numbers (e.g. "13_Sonken", "14_Kannei") that correspond to slot track numbers ("1_13", "1_14"), prioritize matching by track number over slight differences in duration (differences of a few seconds are normal due to mastering/silence). NEVER swap adjacent numbered tracks simply because of minor duration differences.
```

## 4. 安全境界

- 本修正はプロンプトのルール制約の追加であり、既存のバリデーションや信頼度閾値には一切影響を与えない。
- LLM が再生時間の近さに惑わされて誤ったスワップを行うのを抑制し、推論の再現性と精度を向上させる。
