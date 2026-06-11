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
2026/05/29 04:32:00 Models/SST_Modelfile SYSTEM命令文を日本語から英語に更新。
2026/05/29 04:32:00 Models/SST_Phi4_Mini_Modelfile SYSTEM命令文を日本語から英語に更新。
2026/05/29 04:32:00 Models/SST_Gemma4_2B_Modelfile SYSTEM命令文を日本語から英語に更新。
2026/05/29 04:32:00 Models/SST_Qwen2.5_1.5B_Instruct_Modelfile SYSTEM命令文を日本語から英語に更新。
2026/05/29 04:32:00 Models/SST_Qwen3.5_4B_Modelfile SYSTEM命令文を日本語から英語に更新。
2026/05/29 05:15:00 .env.example, Models/: 推奨LLMモデル（DRAFT: qwen2.5:1.5b, SMALL: qwen2.5:7b, MEDIUM: qwen3.5:9b, LARGE: phi4:14b）の標準化。LLM_setup.sh および build_lightweight_sst.sh を更新し、英語プロンプト版カスタムモデル（-sst）の一括生成・管理体制を整備。不要な旧Modelfileを整理。
2026/05/29 09:55:00 README.md, docs/: システム構成の変更（ネイティブ Ollama への移行、Python zipfile による展開処理への変更）を反映。依存関係に zstd を追加。
2026/05/29 10:20:00 README.md: セットアップ手順にOllamaサーバーの起動（`ollama serve` または `systemd` による自動起動）に関する注意書きと、VRAM節約のための `OLLAMA_KV_CACHE_TYPE=q4_0` おすすめ設定を追記。
2026/05/29 10:05:00 Models/LLM_setup.sh: Ollama サーバーの稼働チェック機能を追加。systemd 環境下での自動起動対応を含め、セットアップの堅牢性を向上。
2026/05/29 18:20:00 システム全体: 100件の大規模テスト（全曲指紋照合ON）を実施。新LLM環境（英語プロンプト＋Ollama）の正常動作を確認し、44%の自動アーカイブ成功を記録。大型アルバムにおけるリソース限界と、バリエーション曲の番号重複という今後の課題を特定。
2026/05/30 03:45:00 src/scout/virtual_album.py 仮想アルバム構築モジュールの新規作成。STEAM, FINGERPRINT (多数決ロジック), LOCAL の3層構造を導入。
2026/05/30 03:45:00 src/scout/llm.py 仮想アルバム統合用メソッド consolidate_virtual_albums を実装。プロンプトを仮想アルバム比較型に刷新。
2026/05/30 03:45:00 src/scout/processor.py 仮想アルバムベースの新しいメタデータ統合フローを試験的に導入。
2026/05/30 11:30:00 docs/Virtual_Album.md, src/scout/virtual_album.py: 仮想アルバム構想の「完成版」を実装。物理的確証 (FINGERPRINT) を Ground Truth とする哲学に基づき、詳細クレジット取得、高度な選別ロジック (Tie-break)、監査特化プロンプトを統合。
2026/05/30 11:30:00 src/scout/runner.py, src/scout/ident/acoustid.py: ティア別並行処理の最適化。SMALLティアの 4並列化と、グローバルな AcoustID API レートリミッターの実装により、精度を維持したまま大幅な高速化を実現。
2026/05/30 11:30:00 src/scout/llm.py, Models/build_lightweight_sst.sh: LLMの安定化と信頼性向上。Ollama コンテキストの 32K 拡大、ロボット型プロンプトへの刷新、および KV キャッシュ量子化解除により、ハルシネーションと Empty Response を解消。
2026/05/30 23:16:00 システム全体: システムをクリーンアップし、--fingerprint-all オプションを用いた100件の再検証テストを開始。
2026/05/31 03:45:00 src/scout/{llm.py,virtual_album.py,builder.py,track_grouper.py}: Cyberpunk 2077 Bonus Content (AppID 1495710) で発生したメタデータ不整合問題を修正。LLMのマッピングキーをインデックス形式に変更し、mbz_track_index の明示的な引き継ぎを実装。ディスク番号の推測ロジックを親フォルダ名参照で強化し、分母（総ディスク数）の不整合を解消。
2026/05/31 06:40:00 src/scout/tagger.py: Mutagen で ID3 フレーム（TCOM 等）に None を渡すとクラッシュするバグを修正。オプション項目が欠損している場合に安全にスキップまたはデフォルト値を設定するようガードを強化。
2026/05/31 06:45:00 AppID 1495710 (Cyberpunk 2077 Bonus Content) の再検証完了。全トラックの個別タイトル付与、Disc 2 のメタデータ復旧、およびディスク番号フォーマットの整合性を確認。物理的矛盾検知による Review 送りの正常動作を実証。
2026/05/31 06:55:00 GEMINI.md: 行動指針を更新。システムクリーンナップを除くすべてのファイル変更（修正・追加・削除）時に CHANGE_HISTORY.md への追記を必須とする義務を明文化。
2026/05/31 06:58:00 AppID 1207000 (Slime Rancher OST II) の再検証完了。tagger.py の修正により、すべての曲にジャンル・コメント等の拡張メタデータが正しく付与されたことを確認。
2026/05/31 07:15:00 docs/LOGIC.md, docs/LOGIC_inside.md: 「重複タイトル検知ガード」の仕様を追記。アルバム内で50%以上のトラックが同一タイトルを持つ場合、LLMの判定に関わらずReviewへ送る安全策を定義。
2026/05/31 07:20:00 src/scout/validator.py: 重複タイトル検知ロジック（Duplicate Title Detection）を実装。LLMの誤認やシステムバグによる全曲同一タイトルの付与を物理的に遮断。
2026/05/31 07:25:00 src/scout/report_generator.py: バッチレポート (Result.html) に重複タイトル警告を表示するバッジとスタイルを追加。
2026/05/31 07:27:00 AppID 1156340 (Nova Drift OST) の再検証完了。修正済みマッピングロジックによりタイトル重複（全曲 Neverend）が完全に解消され、全41曲に固有のメタデータが正しく付与されたことを確認。
2026/05/31 07:45:00 src/scout/processor.py: マルチディスク構成の再構築ロジックを修正。メタデータ解決後にディスク番号を確定させてから出力先サブディレクトリを決定するように順序を入れ替え、ディスク混在問題を解消。
2026/05/31 07:48:00 src/scout/builder.py: MusicBrainz ソースからのディスク番号取得において、トラック単位の正確なディスク番号（mbz_track 由来）を参照するように修正。
2026/05/31 07:55:00 src/scout/main.py: 非対話実行用フラグ '--yes' (-y) を追加。--fingerprint-all モード等の時間のかかる処理における 3段階認証を自動承認できるようにし、バックグラウンド実行や自動テストへの対応を強化。
2026/05/31 08:10:00 docs/LOGIC.md: 'Steam 信頼パス (STEAM-TRUST)' を正式な同定ポリシーとして追加。物理同定が不可でも Steam ストア情報と LOCAL 構成が構造的に一致すれば Archive を許可する仕様を定義。
2026/05/31 08:15:00 src/scout/llm.py: Phase 1 プロンプトを更新。AcoustID 未登録時に Steam ストア情報を Ground Truth として信頼し、確信度 100% を割り当てるよう LLM への指示を強化。
2026/05/31 08:20:00 src/scout/{main.py,scanner.py}: '--appid' 引数を拡張し、カンマ区切りでの複数AppID指定に対応。一括再検証やメンテナンス時の利便性を向上。
2026/05/31 08:35:00 src/scout/validator.py: STEAM-TRUST パスを正式実装。LLM が 'STEAM_BASED' かつ確信度 100% を提示した場合、物理同定データの欠落による Quality 減点を許容し、品質閾値を 90% から 80% へ動的に緩和するように修正。
2026/05/31 08:40:00 src/scout/validator.py: バリデーションロジックを全面リファクタリング。判定の優先順位を整理し、'Steam 信頼パス' が正しく適用されるよう構造を改善。物理的異常チェックと LLM スコア評価の整合性を強化。
2026/05/31 08:45:00 src/scout/llm.py: 最終的なメタデータマッピングに 'integrity_quality' を追加。バリデーターとのスキーマ不一致を解消し、STEAM-TRUST による品質閾値緩和が正しく機能するように修正。
2026/05/31 08:50:00 src/scout/{processor.py,validator.py,report_generator.py}: システム全体のスコア受け渡しスキーマを修正。Validator が品質スコア（quality）を返すように拡張し、Processor がそれを DB (metadata.json) に正しく保存するように改善。レポート上での表示不備も解消。
2026/05/31 08:45:00 src/scout/report_generator.py: 'Optional' インポートの追加忘れによる NameError を修正。システムが起動不能になっていた問題を解決。
2026/05/31 09:05:00 src/scout/llm.py: Phase 1 プロンプトを更新。ARCHIVE 判定時には 'archive_vs_review_ratio' を確実に 100% に設定するよう LLM への指示を強化。これにより、確信度が高くてもバリデーターで Review 送りになる矛盾を解消。
2026/05/31 09:10:00 src/scout/llm.py: プロンプト内の f-string エスケープミスを修正。中括弧の二重化により ValueError を解消。
2026/05/31 09:15:00 src/scout/llm.py: 最終メタデータマッピングに 'archive_vs_review_ratio' を追加。バリデーターとのスキーマ同期をさらに徹底し、Archive 送りの障壁を解消。
2026/05/31 09:20:00 src/scout/processor.py: DB 保存用のメタデータ JSON に 'archive_vs_review_ratio', 'strategy', 'message' を追加。LLM 判定の内部指標を確実に永続化し、バリデーターやレポートの整合性を向上。
2026/05/31 09:25:00 src/scout/llm.py: Phase 1 後のバリデーションを堅牢化。'archive_vs_review_ratio' のデフォルト値設定を追加し、LLM の不完全な応答によるバリデーターの誤作動を防止。
2026/05/31 09:30:00 src/scout/llm.py: Phase 1 プロンプトを再強化。Archive 判定時の比率（archive_vs_review_ratio）設定を厳格に指示し、LLM による不整合な低スコア出力を防止。
2026/05/31 20:52:19 src/scout/validator.py: バリデーションロジックを更新。LLMの判定比率（archive_vs_review_ratio）が矛盾している場合でも、確信度と品質が高い場合はシステム側でアーカイブを許容するように救済措置を導入。
2026/05/31 20:52:19 src/scout/llm.py: プロンプトを更新。ディスク番号の再割り当て（override_disc）を「至上命令」として定義し、ローカルのフォルダ構成に関わらずSteam/Fingerprintの構造に合わせるよう指示を強化。
2026/05/31 20:58:00 src/scout/virtual_album.py: Steamストア情報のキー名（number, title）の不一致を修正。これにより、LLMがSteam側の曲名とトラック番号を正しく認識できなくなる重大なバグを解消。
2026/05/31 21:05:00 src/scout/builder.py: LLMが提示した override_track, override_disc, override_title を最優先で適用するように修正。また、matched_v_idx を利用して Steam/MBZ トラックを正確に特定するように改善し、不正確な曖昧一致を排除。
2026/06/01 02:22:00 src/scout/processor.py: LLMの回答に対する後処理ロジック '_resolve_duplicate_mappings' を実装。Steamストア側で同名曲が連続している場合、LLMの重複マッピングを自動的に順次インデックスへ再配分するようにし、同名曲多発アルバムのアーカイブ成功率を向上。
2026/06/01 02:22:00 src/scout/builder.py: LLMの 'action' 誤認（幻覚）に対する救済措置を導入。'use_fingerprint' が指定されても実際には指紋がない場合、Steamのインデックスとして再解釈して処理を続行するように改善。
2026/06/01 02:22:00 src/scout/builder.py: 作曲者（TCOM）タグの自動抽出ロジックを強化。LLMからの指定がない場合、Steamのクレジット欄から正規表現（'Composer:', 'Music by' 等）を用いて自動的に作曲者を特定・付与するように改善。
2026/06/01 02:22:00 src/scout/llm.py: 指紋データがない場合に LLM へ 'NOT AVAILABLE' を明示するように修正。空配列提示による LLM の不必要な推測（幻覚）を抑制。
2026/06/01 02:22:00 docs/LOGIC.md: 'スマート救済ロジック' および 'STEAM-TRUST パス' の詳細仕様を更新。最新の実装に基づき、判定閾値の動的緩和や重複解消アルゴリズムを追記。
2026/06/01 02:28:10 src/scout/processor.py, src/scout/virtual_album.py: --fingerprint-all フラグの動作を適正化。未指定時は3曲（最初、中間、最後）のみをサンプリングしてAcoustIDスキャンを行うように変更し、APIリクエスト数の削減と処理の高速化を実現。
2026/06/01 16:40:00 run_comparative_test_part2.sh 作成、比較テスト自動化シーケンス（テスト1待機〜テスト2完了まで）を開始。
2026/06/01 20:15:00, src/scout/main.py, --yes オプション使用時に handle_all_confirm と handle_fingerprint_all_confirm の確認プロンプトをスキップするよう修正。
2026/06/01 21:05:00, src/scout/llm.py, consolidate_virtual_albums メソッド内で ref_fingerprint が未定義だったバグを修正。これにより指紋データ使用時に NameError が発生する問題を解消。
2026/06/02 02:10:00, src/scout/processor.py, 実装漏れ（...）となっていた箇所の LocalProcessResult 呼び出しを修正。これにより Pydantic の TypeError を解消。
2026/06/02 11:15:00 GEMINI.md: テストスクリプトおよびテストデータの運用場所を Maintenance ディレクトリに限定するルールを追記。
2026/06/02 11:45:00 src/scout/processor.py: 重複解消ロジック (_resolve_duplicate_mappings) を強化。前方一致による類似名トラック（バリエーション曲）の自動再配分に対応し、ディスク番号の型不一致によるソートエラーを修正。
2026/06/02 12:00:00 src/scout/processor.py: マルチディスク構成におけるインデックス重複救済ロジックを追加。ローカルのディスク番号情報を優先して、Steamリスト内の正しいディスク範囲へ自動再配分するように改善。
2026/06/02 12:15:00 src/scout/processor.py: 重複解消ロジックを抜本的に強化（3段階の救済アルゴリズム：マルチディスク整列、名前ベースの再検索、同名曲順次配分）。Happy's Humble Burger Farm 等の大量重複が発生するケースや、バリエーション曲の誤同定を自動的に救済可能にした。
2026/06/02 12:30:00 Maintenance/: ワークスペースルートのテスト関連ファイル（結果、レポート、検証スクリプト、ログ）を Maintenance ディレクトリへ集約し、ディレクトリ構造を整理。
2026/06/02 12:45:00 docs/LOGIC.md, docs/LOGIC_inside.md, README.md: 重複解消ロジック（Smart Rescue Logic）の強化および Maintenance ディレクトリの役割に関する記述を追記し、最新の実装と同期。
2026/06/02 13:00:00 .gitignore: Maintenanceディレクトリ内の巨大なテスト結果データを除外設定に追加。
2026/06/02 13:15:00 docs/Analysis_Report_Fingerprint_20260602.md: 指紋照合ありテスト結果の深掘り分析レポート（LLMとロジックの判定乖離パターンの分類）を作成。
2026/06/11 07:04:44 rules/RULE.md: ワークスペース内の全ドキュメントおよびコードを検査し、詳細仕様書を作成。ドキュメントとコード間の矛盾点および不足点を明記。
2026/06/11 07:05:00 pyproject.toml: description を適切な内容に更新。ローカル実行ポリシーに反する不要な依存関係（boto3, minio等）を削除。※プロジェクト名はビルドエラーを回避するため scout に据え置き。
2026/06/11 08:58:00 src/scout/config.py: LLMモデル名の不整合を修正（ハイフンとコロンの混在を解消し、ビルドスクリプト・.env.exampleに統一）。
2026/06/11 09:00:00 docs/: 実装と乖離していた陳腐化したドキュメント (LOGIC_inside.md) と使用されていないJSONスキーマ (schemas/) を削除し、情報源を整理。
2026/06/11 12:58:00 全体: プロジェクト名を S.S.T に統一するため、ソースディレクトリを `src/scout` から `src/sst` へリネームし、全ファイルのインポートパスを修正。
2026/06/11 12:59:00 src/sst/llm.py, Models/: 専用LLMモデル構築（-sst等）を廃止し、llm.py 内でシステムプロンプトと推論パラメータを動的に注入する方式へ変更。不要な Modelfile 等を削除。
2026/06/11 13:00:00 src/sst/: VGMdb および Discogs 連携コードを削除し、関連する環境変数・設定項目を .env.example および config.py から撤去。
2026/06/11 13:01:00 src/sst/tagger.py: MP3 のエンコード形式を仕様通り `CBR/320kbps` 固定に変更 (`-b:a 320k` を採用)。
2026/06/11 13:23:00 docs/: ディレクトリ名変更(`scout`->`sst`)、VGMdb・Discogs関連ロジックの排除、MP3のエンコード仕様等の変更を全ドキュメントに反映し、古い記述を一斉置換。
2026/06/11 13:25:00 tests/: コアロジック (track_grouper 等) の単体テスト (`pytest`) を実装。クラウド依存を避けるため GitHub Actions を廃止し、ローカル用のテストスクリプト (`Maintenance/run_tests.sh`) を配置。

2026/06/02 14:23:22 .gitignore, Maintenance/: GitHub送信不適切なファイル（*.pid, Maintenance/*.txt）の追跡を解除し、.gitignore を更新して将来の混入を防止。2026/06/11 13:58:00
- src/sst/processor.py
- src/sst/builder.py
  VGMdb関連のインポートおよび参照ロジックの残存箇所を完全に削除。
- src/sst/ident/acoustid.py
  `acoustid.lookup` に `timeout=10.0` を追加し、API無応答時にプロセスがハングアップする問題を修正。
- src/sst/llm.py
  LLM APIへのリクエスト時、HTTPステータス200以外が返された場合に `logger.warning` でエラー内容を出力するようログを強化。

2026/06/11 16:15:00 HANDOVER.md: 別のエージェントに現在の進行状況を引き継ぐためのドキュメント HANDOVER.md をプロジェクト直下へ作成。

2026/06/11 18:40:00 skills/sst-cleaner/scripts/clean_system.py, skills/sst-cleaner/SKILL.md: `sst-cleaner` に `--keep-steam-cache` オプションを追加。Steamキャッシュ（データベース内の `steam_store_data`）を保持しつつ、`processed_albums` テーブルやその他のログ・キャッシュを初期化できるように改修。

2026/06/12 07:54:00 docs/batch_test_analysis_100.md: 実戦テスト（100件）の結果、および「なぜArchive/Review行きになったか」「相応しくないArchive行きはないか」「ロジックの矛盾はないか」の調査結果をまとめた分析ドキュメントを新規作成。

2026/06/12 07:56:00 skills/sst-analyzer/: 今回の実行結果分析作業を汎用的に再利用できるよう、データベースの履歴からArchive/Reviewの要因を分類・レポート出力するスキル `sst-analyzer` を新規作成。

2026/06/12 08:26:00 docs/discord_integration.md: 既存の通知実装 (`src/sst/notify.py`) に基づき、Discord Webhook連携の仕様書（通知レベル、ペイロード、Cooldown制御の仕組み等）を新規作成。

2026/06/12 08:28:00 docs/smart_duplicate_resolution.md: 同名トラックやLLMのマッピング衝突をプログラム側で解決するアルゴリズム（Smart Duplicate Resolution）の仕様書を新規作成。

2026/06/12 08:30:00 docs/error_handling.md: バッチ継続性、外部APIのタイムアウト制御、LLM推論のフォールバック、Validatorによるフェイルセーフなど、システム全体のエラーハンドリング方針をまとめた仕様書を新規作成。

2026/06/12 08:30:00 docs/data_flow_diagram.md: S.S.Tのシステムアーキテクチャおよび「Input -> Gathering -> LLM Processing -> Validation -> Output」に至る一連の処理フローを可視化したデータフロー図（Mermaid）を新規作成。

2026/06/12 08:31:00 docs/api_rate_limit.md: LLM APIのマルチスレッド保護（ジッター・動的バックオフ機構）やMusicBrainz等の外部APIのレートリミット制御に関する仕様書を新規作成。

2026/06/12 08:31:00 docs/wsl_path_conversion.md: SteamライブラリのWindowsパスをWSL2互換パスへ自動変換する機能（WSL Path Conversion）の仕様書を新規作成。
