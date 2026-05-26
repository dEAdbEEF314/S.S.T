# S.S.T (Steam Soundtrack Tagger) Handover Document

## 1. プロジェクト概要
**「一度のアーカイブで、一生の信頼を」**
S.S.Tは、Steamライブラリ内のサウンドトラックに対し、物理的な音の指紋（AcoustID）と公式・外部メタデータ（Steam Store, PICS, MusicBrainz, VGMdb）を掛け合わせ、100%の信頼性で自動タグ付け・アーカイブを行うシステムです。曖昧なデータは「Review」フォルダへ隔離し、人間による最終確認を促す安全設計を貫いています。

## 2. 現在のアーキテクチャ
- **Scout (情報収集)**: 3層API（Store API, PICS Bridge, Web API）に加え、AcoustIDによる物理同定。
- **Judiciary (LLM司法)**: 収集した証拠に基づき、Archive可否の判定と、不整合データのクリーニング指示を生成。
- **Executive (実行)**: FFmpegによる正規化変換（ティア別）と、MutagenによるID3v2.3準拠のタグ書き込み。

## 3. 重要な技術仕様と直近の改善点 (Branch: more-AcoustID-01)
- **VGMdb CDDB連携**: DiscIDベースで日本語・英語の多言語タイトル（Plan B）を取得可能。
- **シングル盤の法則**: 1曲構成のアルバムにおける自動判定救済ロジック。
- **HTMLバッチレポート**: 処理結果を視覚的に一覧できるレポート生成機能。
- **【新規】全曲AcoustID照合モード (`--fingerprint-all`)**:
  - アルバム全曲の指紋を取得し、Release MBIDの完全な積集合（Intersection）を計算。
  - 物理的に完全に一致する「正解の版」を数学的に特定し、Review送りを劇的に削減する。
  - API制限回避のため、1曲ごとに1.5〜2.0秒のディレイを挿入する高精度・低速モード。

## 4. 実行環境
- **OS**: Windows 11 / WSL2 (Ubuntu)
- **Runtime**: Python 3.12 (uv), FFmpeg, SQLite3
- **LLM Backend**: Local Ollama (Qwen2.5/3.5, Phi-4)
- **External API**: AcoustID (fpcalc), MusicBrainz, VGMdb

## 5. 現在のディレクトリ構造 (主要部分)
- `src/scout/`: コアロジック（`processor.py`, `builder.py`, `llm.py` 等）
- `src/scout/ident/`: 外部サービス連携（`acoustid.py`, `mbz.py`, `vgmdb.py`）
- `Maintenance/`: 調査・分析用スクリプト群
- `data/`: 状態DB（初期化済み）
- `output/`: 成果物（クリーンアップ済み）

## 6. 次に着手すべきタスク
- **次回のテスト実行**:
  - **100件のバッチテストを、新設した `--fingerprint-all` オプション付きで実施する。**
  - コマンド: `uv run python -m scout.main --all --limit 100 --fingerprint-all`
  - 実行時に表示される3段階の確認プロンプト（SLOW / CONFIRM 等）に答えて発動させること。
- **期待される検証**:
  - 前回のテストで `[Duplicates]` によりReview送りとなった42件が、全曲照合によってどの程度自動Archiveに昇格するかを確認する。
  - 1曲ごとのディレイ処理が正常に機能し、API制限に抵触せずに完走するかを監視する。

---
このドキュメントを新しいセッションに貼り付けることで、作業を完全に再開できます。
