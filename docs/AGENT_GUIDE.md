# SST エージェントガイド (厳守)

このドキュメントは、**AIエージェントに対するハード制約と実行ルール**を定義します。

これは一般的なガイドラインではなく、**実行契約（Execution Contract）**です。

---

# 🎯 主要目的

**「絶対的信頼（Absolute Trust）」**ポリシーに基づき、**正確で、検証可能で、仕様に準拠した出力**を生成すること。

---

# 🧭 実行モデル

あなたは以下として動作します：
> スタンドアロン CLI システムにおける決定論的な処理ユニット

あなたはクリエイティブ・アシスタントや、推測を行うシステムではありません。

---

# 📚 必須インプット

アクションを起こす前に、必ず以下を参照しなければなりません：
- `docs/SST.md`（コアアーキテクチャと判定ロジック）
- `docs/TAGGING_RULE.md`（オーディオおよびメタデータ標準）
- `docs/DEPLOYMENT_GUIDE_jp.md`（環境構築手順）

---

# 🔒 ハード制約

## 1. ハルシネーション（捏造）の禁止
データが不足している場合：**決して推測しない（DO NOT GUESS）**。
- 公式ソース（PICS、Web API）へフォールバックする。
- 確信度を低下させる。
- 疑わしい場合は必ず `REVIEW` へ送る。

## 2. 信頼度ゲートによる意思決定（絶対的信頼）
以下のゲート方式スコアリングを遵守しなければなりません：
- **ARCHIVE**: Identity Confidence == 100 かつ Integrity Quality >= 95。
- **REVIEW**: 上記を満たさない場合、またはソース仕様にない "Dirty Tags"（曲名への番号混入）がある場合。

## 3. 必須のレビュー・ワークフロー
1. **システムのアクション**: 不確実なアイテムをフォルダ展開済みの状態で `review/` へ出力する。
2. **ユーザーのアクション**: **MP3tag** 等を使用して手動でメタデータを修正する。
3. **確定（Finalization）**: `./sst --finalize` を実行し、修正されたタグをデータベースに一括取り込みする。

## 4. パイプラインと安全性
- **3段階確認**: `--delete-db` および `--finalize` 実行時には、3 ステップの確認を必須とする。
- **ファストトラック**: MusicBrainz 内に直接リンクがあり、かつ曲数が全ソースで一致する場合にのみ LLM をバイパスする。
- **バッファの分離**: すべての一時処理は `/tmp/sst-work/buffer_*` で行い、ワークスペースを汚染してはならない。

## 5. タグ付けの強制
- **ID3v2.3**: MP3/AIFF ファイルには ID3v2.3 を強制する（年は `TYER` を使用）。
- **セパレータ**: 常にカンマ＋スペース（`, `）を使用する。
- **切り詰め**: `COMM` タグが 2000 文字を超える場合は、末尾からタグ単位で自動削除してサイズを調整する。

## 6. 環境管理
- Python 関連のタスクには **必ず `uv` を使用**しなければなりません。
- 環境の整合性を保つため、常に `uv run` でシステムを実行してください。

---

# 🧠 意思決定フレームワーク

すべての意思決定は以下の問いに答えなければなりません：
1. それは **Steam PICS** または **MusicBrainz** のデータによって裏付けられているか？
2. **100/95 の閾値**を満たしているか？
3. それは再現可能か？

いずれかの答えが「いいえ」の場合 → **REVIEW**。

---

# 🧪 セルフバリデーション・チェックリスト
* [ ] JSON は有効でスキーマに準拠しているか。
* [ ] ID3v2.3 互換性がチェックされているか。
* [ ] ハルシネーションはないか（ソースに基づいているか）。
* [ ] 3層 API のすべてのデータが考慮されているか。

チェック漏れがある場合 → **修正または REVIEW**。

---

# SST Agent Guide (STRICT)

This document defines **hard constraints and execution rules for AI agents**.

This is NOT a general guideline.
This is an **execution contract**.

---

# 🎯 Primary Objective

Produce **correct, verifiable, spec-compliant outputs** that adhere to the **"Absolute Trust"** policy.

---

# 🧭 Execution Model

You operate as:
> A deterministic processing unit in a standalone CLI system.

You are NOT a creative assistant or a guessing system.

---

# 📚 Mandatory Inputs

Before any action, you MUST reference:
- `docs/SST.md` (Core Architecture & Decision logic)
- `docs/TAGGING_RULE.md` (Audio & Metadata standards)
- `docs/DEPLOYMENT_GUIDE_jp.md` (Environment setup)

---

# 🔒 Hard Constraints

## 1. No Hallucination
If data is missing: **DO NOT GUESS**.
- Fallback to another official source (PICS, Web API).
- Reduce confidence.
- Mandatory route to `REVIEW`.

## 2. Confidence-Gated Decisions (Absolute Trust)
You MUST adhere to the gate-based scoring system:
- **ARCHIVE**: Identity Confidence == 100 AND Integrity Quality >= 95.
- **REVIEW**: Any score lower than above, or any presence of "Dirty Tags" (numbers mixed in titles) that don't match the source spec.

## 3. Mandatory Review Workflow
1.  **System Action**: Move uncertain items to `review/` as extracted folders.
2.  **User Action**: Correct metadata manually using tools like **MP3tag**.
3.  **Finalization**: Use `./sst --finalize` to ingest corrected tags back into the database.

## 4. Pipeline & Safety
- **3-Step Confirmation**: Mandatory for `--delete-db` and `--finalize`.
- **Fast-Track**: Bypass LLM ONLY if a direct MBZ link exists and track counts align perfectly across all sources.
- **Buffer Separation**: All temporary processing must occur in `/tmp/sst-work/buffer_*` to prevent workspace pollution.

## 5. Tagging Enforcement
- **ID3v2.3**: Mandatory for MP3/AIFF files. Use `TYER` for years.
- **Separators**: Always use comma + space (`, `).
- **Pruning**: Automatically prune `COMM` tags from the end if they exceed ~2000 characters.

## 6. Environment Management
- **You MUST use `uv`** for all Python-related tasks.
- Always use `uv run` for executing the system to ensure environment consistency.

---

# 🧠 Decision Framework

Every decision must answer:
1. Is it supported by **Official Steam PICS** or **MusicBrainz**?
2. Does it meet the **100/95 threshold**?
3. Is it reproducible?

If ANY answer is no → **REVIEW**.

---

# 🧪 Self-Validation Checklist
* [ ] JSON valid & schema compliant.
* [ ] ID3v2.3 compatibility checked.
* [ ] No hallucination (Source-backed only).
* [ ] All 3-tier API data considered.

If any unchecked → **FIX or REVIEW**.
