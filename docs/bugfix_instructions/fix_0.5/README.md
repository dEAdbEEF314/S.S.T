# S.S.T 修正作業指示書 fix_0.5

## 概要

音源ライブラリ全352件のバッチ処理完了後のフォレンジック監査に基づき、システムのロジック欠陥・処理不備に起因する誤Review是正（指示書 01〜03）、およびその後の全数監査で承認された運用性・網羅性向上（指示書 04〜05）を実施するための総合改修仕様書。

本改修を適用することにより、**Archive 率は 340件 (96.59%) から 346件 (98.30%) 以上** へ向上し、残る Review 案件についてもサブステータスによって監査コストが極小化される。

---

## 修正指示書一覧

| 番号 | ファイル名 | 対象モジュール | 主対象 AppID | 優先度 | 概要 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **01** | `01_ffmpeg_video_stream_suppression.md` | `src/sst/tagger.py` | `2410560` (デイヴ・ザ・ダイバー) | 🔴 P0 | FFmpeg 変換コマンドへの `-vn` 常時付与による高解像度埋め込み画像クラッシュ防止 |
| **02** | `02_multidisc_continuous_numbering_variant_consolidation.md` | `src/sst/processing/slot_variants.py` | `1879310` (TCSTRIKERS4) | 🔴 P0 | 通し連番マルチディスクにおける兄弟バリアント統合の元トラック番号照合と他ディスク直接照合バイパス |
| **03** | `03_llm_track_number_anchor_and_anti_swap.md` | `src/sst/llm/prompts.py` | `466530` (恋姫†演武) | 🟡 P1 | LLM マッピングプロンプトにおけるトラック番号アンカー保護と微小再生時間差による安易なスワップ抑止 |
| **04** | `04_bonus_or_se_isolated_review_sub_status.md` | `validator.py`, `package_metadata.py`, `batch_report.py`, `notifications.py` | `1299740`, `1553350`, `1806720`, `584382` | 🟢 P1 | 本編100%充足・余剰ファイル隔離アルバムへの `BONUS_OR_SE_ISOLATED` サブステータス自動付与 |
| **05** | `05_local_appinfo_pics_tracklist_fallback.md` | `scanner.py`, `steam_web_api.py` | `870530`, `1270860`, `1611170`, `1796120`, `2392620`, `2966860` | 🔴 P0 | ローカル `appinfo.vdf` (PICS) からのトラックリスト・クレジット抽出フォールバック強化 |

---

## 安全境界と検証強度維持原則

1. **検証強度の維持**: `ResultValidator` の信頼度・品質閾値（`confidence` / `data_quality`）、重複検知、クロススロット整合性検査は一切緩和しない。
2. **STEAM 正本の絶対性**: Steam ストア・PICS トラックリストの構造を唯一の正本とし、ローカル推論による Steam スロットの創作・上書きは行わない。
3. **物理エラーの正当性**: FLAC デコードエラー等の真の物理破損（457840, 459851）は Review を維持する。
4. **サブステータスの透明性**: `BONUS_OR_SE_ISOLATED` は Review の中立的分類であり、本編が完全に保護されていることを監査者に明示しつつ、未割当ファイルの勝手なアーカイブ化は行わない。
