2026/05/19 09:19:30 skills/sst-cleaner: システム初期化スキルの作成とインストール。データベース、キャッシュ、ログ、中間生成物を一括削除する機能を提供。
2026/05/19 10:20:34 README.md: 「システムの起動準備」セクションを追加。PICS Bridge、llama.cppの起動コマンド、専用モデルの作成方法を追記。
2026/05/19 10:21:26 README.md: 英語版にも「Setup & Startup」セクションを追加。
2026/05/19 10:43:43 scout/src/scout/{llm.py,processor.py}: 監査レポートの強化。LLMが選択したMBZ IDを表示し、UI上で強調表示するよう変更。
2026/05/19 15:58:34 Batch Test: 50件の実戦テストを完了。42件のアーカイブ成功、8件のレビュー判定。システム全体の安定性と並列処理能力を確認。
2026/05/19 19:18:36 scout/src/scout/ident/mbz.py, docs/LOGIC.md: MusicBrainz スコアリングロジックの適正化。多重リンク加点の抑制、トラック数・リリース年不一致ペナルティの強化、減点項目の可視化を実施。
2026/05/19 20:17:59 scout/src/scout/{embedded.py,builder.py,tagger.py}: COMM（コメント）タグのマージ仕様変更。既存コメントがある場合は ", " をセパレータとして接続し、単一のフレームに統合して保存するように修正。
2026/05/20 02:17:53 run_comparative_test.sh: ハードコードされた旧環境の絶対パスを、$(pwd) を使用した動的なパスに修正。環境の移動に対応。
2026/05/22 22:47:19 docs/LOGIC_inside.md: 関数単位の挙動、正規表現、例外処理、ID3バイナリレベルの考慮事項などを網羅した「内部実装詳細仕様書」として再構築。
2026/05/22 22:54:15 docs/LOGIC_inside.md: 高レベル仕様書を排し、実際のPythonコード（リファクタリング後の最新版）から関数・アルゴリズム・正規表現・物理検閲ゲート等の「実装の真実」を抽出して全面刷新。
2026/05/20 16:51:41 Repository: ディレクトリ構造のフラット化リファクタリング。scout/src/scout 以下のソースを src/scout に移動し、pyproject.toml 等の設定ファイルをルートに統合。sst ランチャー等のパス参照を全面的に更新。
2026/05/20 16:51:41 src/scout: コードベースの全体リファクタリング。未使用コード（acoustid.py, cross_val.py, audit.py）を削除し、肥大化したコアファイルを config, rate_limit, report_generator, track_grouper, validator に機能分割。10件の実戦テストにより安定性を確認。
2026/05/20 22:42:04 src/scout/{scanner.py,builder.py}: COMM欄のタグ欠落問題を修正。ローカル appinfo.vdf の store_tags と API キャッシュ (data/steam_tags.json) を連携させ、親ゲームの人気タグを自動取得するよう改善。タグセパレータを "; " に変更。
2026/05/21 01:11:31 src/scout/{builder.py,tagger.py}: COMM欄のタグ表記法を仕様変更。タグ項目を "[ ]" で囲み、セパレータを "/ " に変更。また、ID3v2.3 の制限に収まるよう、長すぎる場合にタグ単位で後方から自動削除する機能を実装。
2026/05/21 12:28:11 100-item Test & Fixes: 100件の実戦テストを実施し、Windowsマウントポイントでの移動エラー、Track#0問題を修正。LLMにSTABLE_IDロジックを導入。中間ZIPファイルの自動削除機能を正式実装し、docs/LOGIC.md に仕様を追記。
2026/05/21 12:51:35 docs: ドキュメント全体のリファクタリング。SST.md, LOGIC.md, TAGGING_RULE.md 等の役割を明確化し、最新のフラット構造、新タグルール、自動削除仕様との整合性を確保。不要なファイルを削除しメンテナンススクリプトを移動。
2026/05/21 13:23:00 Report_about_INFO-Source.md: メタデータ情報ソースの調査結果レポート（各API、VDF、埋め込みタグ情報の役割と利用箇所）を作成し保存。
2026/05/22 05:31:00 .env.example, src/scout/{config.py,llm.py,builder.py,processor.py}: 各ID3フレーム（TIT2, TPE1, TRCK, TPOS, TYER, TPUB, APIC）ごとに、.envで個別にメタデータ優先順位を指定できる機能を追加。優先順位はLLMプロンプトの調停の重み付けに反映され、システムロジック（builder.py）において上位ソースが欠損している場合に次の優先度のソースへ動的にフォールバックするロジックを実装。
2026/05/22 05:58:30 skills/sst-cleaner/scripts/clean_system.py: sst-cleaner で動的に設定値 (SST_OUTPUT_DIR, SST_WORKING_DIR, SST_DB_PATH) を Config から読み込み、WSL物理パスへ変換してそれらの出力物・一時ファイルを安全にクリーンアップできるように修正。
2026/05/22 09:38:16 src/scout/builder.py, .env, .env.example: トラック番号（TRCK）の解決優先順位に `FILE`（ファイル名からの抽出）をサポート。汚染された内部タグへの対策として、.envの `PRIORITY_TRCK` に `FILE` を指定可能に変更。
2026/05/22 13:01:00 src/scout/llm.py: Happy's Humble Burger Farm シリーズ等で見られる、すべてのトラックの内部タグ番号が `1` に固定されている等の異常なメタデータ汚染対策として、LLMプロンプトを修正。異常検知時に `override_track` を `null` として出力させ、システム（`FILE` 優先設定）による自動推論へ安全にフォールバックさせるように改善。
2026/05/22 13:58:00 src/scout/{llm.py,builder.py,validator.py,track_grouper.py}, docs/LOGIC.md: FlatOut 4等でファイル名にアーティスト名が付加されているためPICSデータとの照合に失敗し、すべての曲がDisc 1にフォールバックしてしまう問題に対応。ファイル名正規化処理で先頭番号後のアンダースコア `_` が除去されないバグを修正し、PICS曲名の一致判定を前方一致（Fuzzy Matching）に緩和。LLM出力項目に `override_disc` を追加し、重複トラック（Disc/Trackの組み合わせが同じ）が発生した場合は強制的にReviewへ送る安全網を追加。
2026/05/22 15:16:44 src/scout/builder.py, .env, .env.example: トラック番号（TRCK）の解決優先順位に `FILE`（ファイル名からの抽出）をサポート。汚染された内部タグへの対策として、.envの `PRIORITY_TRCK` に `FILE` を指定可能に変更。
2026/05/22 15:47:25 src/scout/builder.py, .env, .env.example: トラック番号（TRCK）の解決優先順位に `FILE`（ファイル名からの抽出）をサポート。汚染された内部タグへの対策として、.envの `PRIORITY_TRCK` に `FILE` を指定可能に変更。
2026/05/22 20:51:10 src/scout/scanner.py: サウンドトラックのパス解決ロジックにおいて、music/ フォルダを common/ フォルダより優先して検索するように修正。ゲーム本体とサウンドトラックが両方存在する場合に、正しくサウンドトラック用（音声ファイルのある）ディレクトリが優先して選択されるように改善。
