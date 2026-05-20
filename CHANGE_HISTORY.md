2026/05/19 09:19:30 skills/sst-cleaner: システム初期化スキルの作成とインストール。データベース、キャッシュ、ログ、中間生成物を一括削除する機能を提供。
2026/05/19 10:20:34 README.md: 「システムの起動準備」セクションを追加。PICS Bridge、llama.cppの起動コマンド、専用モデルの作成方法を追記。
2026/05/19 10:21:26 README.md: 英語版にも「Setup & Startup」セクションを追加。
2026/05/19 10:43:43 scout/src/scout/{llm.py,processor.py}: 監査レポートの強化。LLMが選択したMBZ IDを表示し、UI上で強調表示するよう変更。
2026/05/19 15:58:34 Batch Test: 50件の実戦テストを完了。42件のアーカイブ成功、8件のレビュー判定。システム全体の安定性と並列処理能力を確認。
2026/05/19 19:18:36 scout/src/scout/ident/mbz.py, docs/LOGIC.md: MusicBrainz スコアリングロジックの適正化。多重リンク加点の抑制、トラック数・リリース年不一致ペナルティの強化、減点項目の可視化を実施。
2026/05/19 20:17:59 scout/src/scout/{embedded.py,builder.py,tagger.py}: COMM（コメント）タグのマージ仕様変更。既存コメントがある場合は ", " をセパレータとして接続し、単一のフレームに統合して保存するように修正。
2026/05/20 02:17:53 run_comparative_test.sh: ハードコードされた旧環境の絶対パスを、$(pwd) を使用した動的なパスに修正。環境の移動に対応。
2026/05/20 16:51:41 Repository: ディレクトリ構造のフラット化リファクタリング。scout/src/scout 以下のソースを src/scout に移動し、pyproject.toml 等の設定ファイルをルートに統合。sst ランチャー等のパス参照を全面的に更新。
2026/05/20 16:51:41 src/scout: コードベースの全体リファクタリング。未使用コード（acoustid.py, cross_val.py, audit.py）を削除し、肥大化したコアファイルを config, rate_limit, report_generator, track_grouper, validator に機能分割。10件の実戦テストにより安定性を確認。
2026/05/20 22:42:04 src/scout/{scanner.py,builder.py}: COMM欄のタグ欠落問題を修正。ローカル appinfo.vdf の store_tags と API キャッシュ (data/steam_tags.json) を連携させ、親ゲームの人気タグを自動取得するよう改善。タグセパレータを "; " に変更。
