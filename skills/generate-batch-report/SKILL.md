---
name: generate-batch-report
description: バッチ処理の完了後に、処理結果（Archive/Review/Error等）の網羅的な詳細分析レポートをHTML形式で生成するスキル。
---

# Generate Batch Report Skill

このスキルは、バッチ処理（例: `--fingerprint-all` オプション等を用いた一括処理）の完了後に、データベースとログを解析して包括的なHTMLレポートを生成するためのものです。

## 📊 レポートに含まれる分析内容

1. **「Archive送り」の件数および理由と処理フロー詳細**
2. **「不自然なArchive送り」の件数と不自然と判断した根拠およびシステム内での処理フロー詳細**
   - SteamタイトルとMusicBrainzの乖離、Track数乖離などを検出します。
3. **「Review送り」の件数および理由と処理フロー詳細**
4. **「理不尽なReview送り」の件数と理不尽と判断した根拠およびシステム内での処理フロー詳細**
   - 高品質・高確信度スコアにもかかわらず、物理的欠損等によりValidatorがArchiveを拒否したケース。
5. **LLMの決定とシステム処理の矛盾の有無と原因**
   - LLMがArchiveを推奨したのにシステムがReview送りとした（またはその逆の）ケース。
6. **処理途中でのエラー、失敗の件数と原因**
   - DB記録エラーや `logs/` ディレクトリ配下の最新ログから致命的エラーを抽出。

## 🚀 実行方法

ワークスペースのルートディレクトリで以下のコマンドを実行するだけで、`report/` 配下に `total_analysis_report.html` という名前でレポートが生成されます。

```bash
uv run python report/generate_total_report.py
```

実行後、生成されたHTMLファイルをブラウザ等で開くことで結果を確認できます。
