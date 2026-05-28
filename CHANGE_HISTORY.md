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
2026/05/22 22:47:19 docs/LOGIC_inside.md: 関数単位の挙動、正規表現、例外処理、ID3バイナリレベルの考慮事項などを網羅した「内部実装詳細仕様書」として再構築。
2026/05/22 22:54:15 docs/LOGIC_inside.md: 高レベル仕様書を排し、実際のPythonコード（リファクタリング後の最新版）から関数・アルゴリズム・正規表現・物理検閲ゲート等の「実装の真実」を抽出して全面刷新。
2026/05/22 23:30:10 src/scout/{config.py,ident/mbz.py,processor.py}, .env.example, docs/LOGIC_inside.md: MusicBrainz スコアリングロジックの各配点値を設定ファイル（.env）から調整可能に仕様変更。各項目の役割について日本語の説明コメントを .env.example に追加。
2026/05/23 00:00:31 Workspace: ルートディレクトリに散在していたテスト・デバッグ・確認用スクリプト、および分析結果のJSONファイルを Maintenance/ ディレクトリに移動し整理。
2026/05/23 01:00:00 - All Python files - ruffによる自動修正（インポート整理、フォーマット）の実施。src/scout/tagger.py への missing import (re) の追加。裸の except: を except Exception: に置換。
2026/05/23 01:15:00 - src/scout/builder.py, src/scout/processor.py, src/scout/tagger.py - TYER優先順位のロールバック、Fast-track条件の厳格化（ディスク枚数・名前照合）、タグの完全クリーンアップ、レーベルの無効値フィルタリングの実施。
2026/05/23 01:25:00 - src/scout/llm.py - LLMプロンプトにおける言語制約を強化。中国語（簡体字・繁体字）および中国語特有語彙の禁止を明文化。
2026/05/23 13:37:59 src/scout/track_grouper.py, docs/LOGIC.md: ハイブリッド・トラック統合ロジックの実装。文字列類似度と再生時間を組み合わせることで、フォーマット間でファイル名に微細な差異（タイポ、冠詞、サフィックス）がある場合でも同一トラックとして正しくグループ化できるよう改善。
2026/05/23 15:26:02 .env.example, src/scout/ident/mbz.py, src/scout/track_grouper.py: メタデータ照合能力の強化。AcoustID（音声指紋）および Discogs API 連携のための設定エントリを追加。また、MusicBrainz 候補の評価ロジックに「セット類似度照合（Set Similarity Matching）」を導入し、アルバム名が異なる場合でも全曲の「名前＋再生時間」のパターン一致度に基づいて高精度な特定を可能に改善。
2026/05/23 18:31:16 src/scout/ident/acoustid.py, src/scout/ident/mbz.py, src/scout/processor.py: 音声指紋（AcoustID）連携の正式実装。`fpcalc` を使用して音声から MusicBrainz ID を直接特定する機能を追加。アルバム内の先頭数曲をサンプリング照合し、得られた ID を MusicBrainz 検索時のスコアリングに反映（大幅加点）させることで、テキスト情報が乏しい・あるいは誤っている場合でも確実なアルバム同定が可能に。
2026/05/23 20:48:58 src/scout/track_grouper.py, src/scout/processor.py: 論理トラック統合ロジックのさらなる強化。ファイル名にアルバム名が含まれている場合にそれを自動除去する正規化処理を追加。これにより、Narita Boy のようにフォーマット間でファイル名の構成が劇的に異なるケース（一方は曲名のみ、他方はアルバム名＋番号＋曲名など）でも、正しく同一トラックとして統合できるよう改善。
Review_list.md: sst-check-reviewsスキルを使用してReview項目の分析レポートを生成。
VGMdb CDDB連携の技術検証完了。日本語・英語メタデータの取得に成功。詳細を Maintenance/vgmdb_cddb_report.md に記録。
src/scout/ident/vgmdb.py: VGMdb CDDB連携クライアントের\ 新規実装。
src/scout/config.py, .env.example: メタデータ優先順位に VGMDB を追加。
src/scout/processor.py: MBZ同定後のVGMdb自動照会とLLMスキップフローの実装。
src/scout/builder.py: バイリンガル・タイトル（Plan B）生成ロジックの実装。
docs/LOGIC.md, docs/TAGGING_RULE.md: VGMdb連携およびバイリンガル仕様の反映。
2026/05/24 17:21:18, src/scout/config.py, src/scout/processor.py, src/scout/ident/mbz.py, AcoustIDの一致スコアを1000に強化し、ファストトラック判定ロジックを修正しました。
2026/05/24 17:28:45, src/scout/report_generator.py, src/scout/processor.py, HTMLレポートの高度化（共通CSS、詳細なタグ一覧表の追加）と、DEBUGモード時のファイル保持ロジックを実装しました。
2026/05/24 17:28:45, src/scout/packager.py, Windowsのtar.exe依存を排除し、Python標準のzipfileライブラリを使用した展開処理に切り替えました。
2026/05/24 20:45:00, src/scout/processor.py, docs/TAGGING_RULE.md: 出力ディレクトリ構造の変更（disc_N プレフィックスの追加）および Discord 通知の精査・詳細化を実施。判定理由を「システムロジック」と「LLM推論」に分離して表示するように改善。
2026/05/26 04:25:00, src/scout/ident/{acoustid.py, mbz.py}, src/scout/processor.py, src/scout/llm.py: 「AcoustID Release ID を軸としたボトムアップ同定ロジック」の実装。全トラックの AcoustID 結果から統計的に共通の Release ID を特定し、MusicBrainz 検索の決定論的証拠として活用。あわせて Steam アンカー（AppIDリンク、パブリッシャー＝レーベル照合）を強化し、LLM プロンプトにこれらの物理的証拠と統計情報を注入することで、エディション違いの選別精度を劇的に向上。
2026/05/26 05:30:00 .gemini/skills/sst-cleaner/scripts/clean_system.py: .envのSST_OUTPUT_DIR等の設定値を動的に読み込み、WSLパス変換を介して正しく削除できるように修正。
2026/05/26 06:15:00 src/scout/processor.py, src/scout/track_grouper.py, idea_plan.md: AcoustIDによる曲単位の確定メタデータ（Recording ID由来）をLocal Baselineに注入するロジックを実装。アルバム同定に失敗した場合でも、曲ごとの物理的証拠を保持して検索精度を向上。
2026/05/26 06:45:00 src/scout/llm.py: Steamストア情報を活用したフォールバックロジックを強化。MBZにデータがない場合でも、1曲のみのシングル盤や構成が一致するアルバムにおいて、Steam情報を絶対視してアーカイブ可能とする指示（シングル盤の法則）とシステムヒントをプロンプトに追加。
2026/05/26 07:05:00 src/scout/{validator.py, report_generator.py, main.py, processor.py}: システム判定理由の洗練（キーワード化・LLM理由との重複排除）および Result.html レポートの自動生成機能を実装。バッチ完了時に最終出力先へ結果一覧を自動保存するように改善。
2026/05/27 15:45:00 docs/LOGIC.md: 全曲AcoustID照合モード（--fingerprint-all）の仕様と数学的確定アルゴリズムを追記。
2026/05/27 15:45:10 src/scout/config.py: 実行時フラグ fingerprint_all を Config クラスに追加。
2026/05/27 15:45:20 src/scout/main.py: --fingerprint-all 引数を追加し、API負荷と処理時間に関する3段階のユーザー確認ロジックを実装。
2026/05/27 15:45:30 src/scout/processor.py: 全曲AcoustIDスキャンモードの実装。1曲ごとのディレイ処理と、Release MBIDの積集合による確定ロジックを統合。
2026/05/27 12:15:00 Maintenance/run_batch_test: --fingerprint-all オプションを用いた100件のバッチテストを開始。物理同定の精度向上を確認。
2026/05/28 16:40:00 - 大規模テスト分析: 124アルバムの処理結果を分析。Archive 71件、Review 53件。Review送りの主因が「トラック番号の重複」であり、同定フェーズ自体は極めて高精度であることを確認。
2026/05/28 20:05:00 src/scout/{track_grouper.py, processor.py}: スマート正規化ロジック（SST Smart Normalizer）の実装。単語境界 (\b) を用いた正規表現により、曲名内の重要な単語（Vermilion等）を保護しつつノイズのみを除去。Instrumental, Vocal, Bonus Track, Arrange 等を「別トラック」として正確に識別・グループ化できるように改善。

2026/05/28 22:15:00 src/scout/llm.py: LLMのPhase 2プロンプトを強化。同一ディスク内でのトラック番号（override_track）の重複を明示的に禁止し、公式リストにないバリエーション曲を適切に個別のトラックとして扱うよう指示を追加。
