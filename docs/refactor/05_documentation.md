# 作業者5: 仕様書・ドキュメント整合

## 目的

実装・テスト・実測結果を突き合わせ、仕様の正本と補助文書の役割を整理する。文書を先に書き換えて実装上の誤りを隠さない。

## 対象

- `docs/METADATA_SOURCE_SPEC.md`
- `docs/TAGGING_RULE.md`
- `docs/LOGIC.md`
- `docs/configuration.md`
- `docs/data_flow_diagram.md`
- `README.md`
- `docs/DEPLOYMENT_GUIDE_jp.md`
- `docs/archive/`
- 作業者1〜4の報告と差分台帳

## 依存関係

作業者1〜4の結果を受けて実施する。途中で判定不能な仕様差分が出た場合は、コードを勝手に変更せず判断保留として返す。

## 正本の役割

- `METADATA_SOURCE_SPEC.md`: データソース、優先順位、Review安全ゲート
- `TAGGING_RULE.md`: ID3タグと成果物
- `LOGIC.md`: 処理フロー、判定、LLMの責務
- `configuration.md`: 設定キー、型、既定値、単位
- `DEPLOYMENT_GUIDE_jp.md`: 外部サービスと運用手順
- `README.md`: 導入と概要。詳細な閾値・設定表は重複させない
- `docs/archive/`: 歴史資料。現行仕様と明示的に区別する

## 作業内容

1. 差分台帳を作る。最低限、正本、実装箇所、現行記載、判定、検証方法を記録する。
2. 次の既知候補を実装・テスト・文書で再照合する。
   - LLM worker既定値 `4` と `.env.example` の明示値 `2`（設定書で区別済み）
   - MusicBrainz track count penalty（Configの既定値を `20` / `300` に統一済み）
   - READMEのテスト件数 `166`（固定件数の記述を削除済み）
   - `LLM_NUM_CTX` / `LLM_OLLAMA_NUM_CTX`
   - metadata priorityの旧名・新名
   - `main.py` のtimeout、パス、lock、cache
   - 処理経路名、Fast-Track、STEAM-TRUST、Review条件
3. 重複文書の記述を正本へのリンクへ置き換える。ただし履歴資料は削除せず、アーカイブ表示を明確にする。
4. Mermaid図と実装の経路名・分岐条件を一致させる。
5. READMEのテスト件数・性能値には測定日と条件を付け、変動する値は固定値として断定しない。
6. 設定文書の自動検証で未記載キー、コードにないキー、既定値・単位不一致を検出できることを確認する。

## 禁止事項

- 実装・テスト未確認の閾値を仕様として確定すること
- 現行仕様と異なる `docs/archive/` を削除すること
- 実データの処理結果や秘密情報を文書へ転載すること
- READMEだけを修正して正本を更新しないこと

## 成果物

- 差分台帳
- 正本文書の修正
- READMEとデータフロー図の修正
- アーカイブ文書への明示ラベルまたはリンク整理
- 文書・設定の自動検証結果
- 未解決の仕様判断リスト

## 完了条件

- 設定キー、既定値、単位がコード・`.env.example`・設定書で一致する。
- Archive/Review、タグ優先順位、未割当・物理成果物ゲートの記載が正本間で一致する。
- READMEが詳細仕様の第二の正本になっていない。
- 文書診断、差分チェック、関連テストが通る。
