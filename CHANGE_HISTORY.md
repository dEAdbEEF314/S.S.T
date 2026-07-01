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

2026/05/27 12:15:00 Maintenance/run_batch_test: --fingerprint-all オプションを用いた100件のバッチテストを開始。物理同定の精度向上を確認。

2026/05/27 15:45:00 docs/LOGIC.md: 全曲AcoustID照合モード（--fingerprint-all）の仕様と数学的確定アルゴリズムを追記。

2026/05/27 15:45:10 src/scout/config.py: 実行時フラグ fingerprint_all を Config クラスに追加。

2026/05/27 15:45:20 src/scout/main.py: --fingerprint-all 引数を追加し、API負荷と処理時間に関する3段階のユーザー確認ロジックを実装。

2026/05/27 15:45:30 src/scout/processor.py: 全曲AcoustIDスキャンモードの実装。1曲ごとのディレイ処理と、Release MBIDの積集合による確定ロジックを統合。

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

2026/05/29 10:05:00 Models/LLM_setup.sh: Ollama サーバーの稼働チェック機能を追加。systemd 環境下での自動起動対応を含め、セットアップの堅牢性を向上。

2026/05/29 10:20:00 README.md: セットアップ手順にOllamaサーバーの起動（`ollama serve` または `systemd` による自動起動）に関する注意書きと、VRAM節約のための `OLLAMA_KV_CACHE_TYPE=q4_0` おすすめ設定を追記。

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

2026/05/31 08:45:00 src/scout/report_generator.py: 'Optional' インポートの追加忘れによる NameError を修正。システムが起動不能になっていた問題を解決。

2026/05/31 08:50:00 src/scout/{processor.py,validator.py,report_generator.py}: システム全体のスコア受け渡しスキーマを修正。Validator が品質スコア（quality）を返すように拡張し、Processor がそれを DB (metadata.json) に正しく保存するように改善。レポート上での表示不備も解消。

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

2026/06/02 14:23:22 .gitignore, Maintenance/: GitHub送信不適切なファイル（*.pid, Maintenance/*.txt）の追跡を解除し、.gitignore を更新して将来の混入を防止。2026/06/11 13:58:00

- src/sst/processor.py
- src/sst/builder.py
  VGMdb関連のインポートおよび参照ロジックの残存箇所を完全に削除。
- src/sst/ident/acoustid.py
  `acoustid.lookup` に `timeout=10.0` を追加し、API無応答時にプロセスがハングアップする問題を修正。
- src/sst/llm.py
  LLM APIへのリクエスト時、HTTPステータス200以外が返された場合に `logger.warning` でエラー内容を出力するようログを強化。

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

2026/06/12 09:08:00 src/sst/main.py, src/sst/log_browser.py, src/sst/runner.py, src/sst/notify.py, src/sst/processor.py, src/sst/scanner.py, src/sst/builder.py: S.S.Tシステムからユーザへ送信される文面（コンソール出力、ログメッセージなど）を、固有名詞（S.S.T、Steam、AppIDなど）を残して日本語に翻訳しました。

2026/06/12 12:19:00 docs/Virtual_Album.md, docs/data_flow_diagram.md: 第4の仮想アルバム「MBZ_SEARCH」の概念（Steam URL逆引き、足切り閾値、FINGERPRINTとの統合）を仕様に追加し、データフロー図を更新しました。

2026/06/12 12:30:00 src/sst/validator.py, src/sst/processor.py, src/sst/llm.py: Dirty Tag（トラック番号混入）の足切り判定を緩和し、Steamストア公式やMBZ公式のトラック名と完全一致する場合は正規のタイトルとして許容する（足切りしない）仕様（B案）へ変更しました。

2026/06/12 12:35:00 src/sst/virtual_album.py, src/sst/processor.py, src/sst/llm.py: 4th_Album ブランチにて、第4の仮想アルバム「MBZ_SEARCH (Semantic Truth)」を実装しました。テキスト検索から得られたトップ候補を足切り評価した上で仮想アルバム化し、LLMの推論プロンプトに新たな入力証拠として統合しました。

2026/06/12 13:06:00 src/sst/llm.py, src/sst/processor.py: S.S.Tシステムから送信される文面の日本語化を実施。LLMの出力する推論理由（reason, confidence_reason, mbz_choice_reason）をユーザー設定言語（日本語）で記述するようにプロンプトの指示を変更し、さらにDiscordへの通知文言やシステムが付与する自動修正ログ (`SYSTEM: ...`) も英語から日本語に翻訳しました。

2026/06/13 08:24:00 src/sst/packager.py, docs/SST.md, docs/LOGIC.md, docs/TEST_ENVIRONMENT.md: Windows側でのI/O負荷によるディスク見失いを回避するため、Windowsへの自動ZIP展開・転送機能を無効化。Ubuntu（WSL）上の指定ディレクトリへのZIPアーカイブ出力で処理を完了する暫定仕様に変更。

2026/06/13 08:29:00 .env.example: Windowsへの自動ZIP展開・転送機能無効化の暫定仕様に伴い、SST_OUTPUT_DIRの説明コメントを「WSLパス指定」「ZIPアーカイブのまま出力」とする内容へ修正。

2026/06/13 08:42:00 src/sst/llm.py: STEAM-TRUST（Steam公式情報を正本とする）判定の救済ロジックを修正。FINGERPRINTデータが部分的に存在して一致率が低い場合でも、Steam公式トラックと完全に構造一致していれば、不要な減点を行わず強制的にArchiveへ引き上げるようにプロンプトとプログラムの条件を緩和。

2026/06/13 08:44:00 skills/sst-cleaner/scripts/clean_system.py, skills/sst-cleaner/SKILL.md: テスト環境リセットの利便性を優先し、SST_OUTPUT_DIR 内の出力物（完成済みのZIPアーカイブを含む）はすべてクリーンアップ対象とする仕様に復元。同時に、デフォルトでSteam/PICSのキャッシュを保持するように変更し、キャッシュ削除用オプション `--clear-steam-cache` を新設。

2026/06/14 18:10:00 docs/cache_architecture.md: ツーフェーズ・アーキテクチャおよびAPIキャッシュ層の実装計画書を新規作成。

2026/06/14 18:10:00 docs/data_flow_diagram.md, HANDOVER.md: ツーフェーズ設計 (Phase 1, Phase 2) を反映。

2026/06/14 18:11:00 src/sst/db.py: API通信のキャッシュ用テーブル `api_cache` の作成ロジックと、`get_api_cache`, `set_api_cache` メソッドを追加。

2026/06/14 18:48:00 src/sst/ident/{acoustid.py,mbz.py}, src/sst/processor.py: APIクライアントに `DatabaseManager` を注入し、通信前後で `api_cache` を利用するように改修 (ツーフェーズ・アーキテクチャの Step 2 完了)。

2026/06/14 18:52:00 src/sst/prefetcher.py: CPUの並列性能とAPIのレートリミットを最大限活用するため、AcoustID(波形計算と検索)とMusicBrainz(テキスト検索)の事前フェッチを行う `DataGatherer` クラスを新規実装 (Step 3 完了)。

2026/06/14 21:15:00 sst, src/sst/main.py: CLIに `--prefetch-only` オプションを追加。LLM推論をスキップし、Phase 1 (事前フェッチ) のみを実施して終了するモードを実装。

2026/06/14 21:15:00 skills/sst-cleaner/scripts/clean_system.py, SKILL.md: `sst-cleaner` に `--keep-prefetch` モードを追加（デフォルト挙動）。APIキャッシュとSteamストアデータを維持したまま処理履歴のみを初期化する仕様を明文化し、逆にすべて消去する `--clear-all-cache` を追加。

2026/06/15 05:00:00 README.md: 現在のTwo-Phaseパイプライン仕様、Read-Only原則、第4の仮想アルバムの概念などを反映し、内容を最新化しました。

2026/06/15 18:50:00 README.md, Models/LLM_setup.sh: レポートの記載を BASIS_for_CLASSIFICATION.md から AUDIT_REPORT.html へ修正し、廃止された専用カスタムモデル作成の記述と実行コードを完全に削除。

2026/06/15 19:10:00 全体: アルバムサイズによるLLMモデルの自動切り替え機能 (Adaptive Routing) を完全に廃止し、.env の LLM_MODEL で単一のモデルを指定する仕様に変更。並列処理数の制御は維持し、.env の設定項目として明文化。

2026/06/15 19:25:00 README.md, Models/LLM_setup.sh: Dirty Tag クリーニング機能の説明を、最新の例外処理（公式名完全一致時の許容）に合わせて修正。また、専用カスタムモデルの廃止に伴い不要となった zstd の依存関係を削除し、環境構築手順を整理。

2026/06/15 19:30:00 .gitignore: デバッグ用の Maintenance/ ディレクトリを GitHub 上に公開しないよう、Git の管理対象から除外。

2026/06/15 19:40:00 README.md, rules/RULE.md: Maintenance ディレクトリの非公開化に伴い、ユーザー向けドキュメントから該当ディレクトリに関する記述（Maintenance ツールキット等）を削除。

2026/06/15 20:57:07 src/sst/llm.py, src/sst/main.py, src/sst/config.py, .env.example, README.md, docs/DEPLOYMENT_GUIDE_jp.md, docs/TEST_ENVIRONMENT.md, Models/: LLMサービスをユーザー各自で用意する運用方針に変更。起動時（事前フェッチモード以外）にLLM APIキーとサービス可用性をチェックしてフェイルファストする機能を追加。また、同梱していたOllama等LLMセットアップ用スクリプト(Modelsディレクトリ)を削除し、ドキュメントを.envでの設定を促す内容に更新。

2026/06/16 07:37:00 docs/batch_test_analysis_prefetch_10.md: 10件の全音声指紋照合あり実戦テストおよび事前フェッチ機能の分析レポートを新規作成。

2026/06/16 07:42:00 src/sst/main.py, src/sst/report_generator.py: 出力されるHTMLレポートのファイル名に日時サフィックスを追加 (Result_YYYYMMDD_HHmmSS.html) し、デザインをダークテーマに変更。

2026/06/16 08:52:38 README.md: アーキテクチャの説明を「ハイブリッド・エッジプロセッサ」に更新。LLM推論がクラウドAPIとローカル環境（Ollama）の選択式になった実態に合わせ、dGPU要件およびOllamaがオプションであることを明記。

2026/06/16 08:57:24 Workspace: ルート直下の idea_plan.md および docs/ 内のテスト分析レポート（Analysis_Report_Fingerprint_20260602.md, batch_test_analysis_100.md, batch_test_analysis_prefetch_10.md）を Maintenance/ ディレクトリへ移動して整理。

2026/06/16 09:02:00 Repository: プルリクエスト #1 (docs: READMEの更新とワークスペースのクリーンアップ) をマージし、ローカルの main ブランチに反映。

2026/06/17 17:50:00 docs/TAGGING_RULE.md, docs/LOGIC.md, src/sst/tagger.py: ID3v2.3の仕様（UTF-8非対応）に厳密に準拠するため、非アスキー文字を含む全タグフレームのエンコーディングを `3` (UTF-8) から `1` (UTF-16 with BOM) に修正し、仕様書を更新。また、日本語や韓国語等の多言語ファイル名をFFmpeg処理する際に `subprocess.run(..., text=True)` が `UnicodeDecodeError` でクラッシュするバグを、バイナリキャプチャおよび `errors='ignore'` デコードへの変更によって解消。

2026/06/18 10:25:00 Maintenance/investigate_219152.py: AppID 219152（Hotline Miami Soundtrack）のDBレコード、MBZキャッシュ、およびZIP内ログの解析、生JSONダンプを行う使い捨てスクリプトを追加。

2026/06/18 10:55:00 docs/LOGIC.md, src/sst/{builder.py,processor.py,report_generator.py}: 監査レポート (AUDIT_REPORT.html) の透明性向上。再生時間に基づく自動整列（Duration Alignment）と優先度フォールバックの解説ノートをレポートに追加。また、各トラックが具体的にどのソースからタイトルを採用したかを示す "Title Source" フィールドと列を追加し、仕様書を更新。

2026/06/18 11:25:00 src/sst/{config.py,main.py,scanner.py}, .env.example: 外部の PICS Bridge サーバー（API）から PICS 情報を安全に取得できるよう仕様変更。環境変数 STEAM_PICS_BRIDGE_API_KEY を新設し、APIキーが指定されている場合はリクエスト時に Authorization (Bearer形式の場合) または X-API-Key ヘッダーを自動付与して送信するように実装。

2026/06/18 11:37:00 Maintenance/clear_cache_219152.py: 動作検証のため、AppID 219152（Hotline Miami Soundtrack）のSQLite DBおよびJSONファイル内キャッシュをピンポイントで消去する使い捨てスクリプトを追加。

2026/06/19 23:10:00 Maintenance/investigate_app.py, .agents/skills/sst-app-investigator/SKILL.md: 指定したSteam AppIDのDB判定結果および出力ZIP内のLLM生ログを自動で抽出・比較する検証用スクリプトを新規作成。同時に、この検証プロセスをシステムが呼び出せるようにするためのカスタムスキル（Skill）を定義。

2026/06/19 23:40:00 src/sst/ident/embedded.py, src/sst/virtual_album.py: 複数枚組アルバムが同一ディレクトリに平置きされている場合の曲順不整合問題を解消するため、音源ファイルのタグからdisc_numberの抽出処理を追加。同時に、LOCAL仮想アルバムの組み立てにおいて音源ファイルのメタデータタグ（track_number）を最優先し、不備がある場合にファイル名連番をフォールバックとして採用して、ディスク・トラック番号順に昇順ソートするようロジックを改修。

2026/06/20 08:53:00 src/sst/llm.py: LLMのタイムアウト値を300秒から600秒へ延長し、ローカル31Bモデル等の推論遅延に対応。また、`action: "use_mbz_search"` の場合に `mbz_track_index` の解決キーが `mbz_track_index` になっていたバグ（正しくは `mbz_idx`）を修正し、MusicBrainzテキスト検索を利用したトラックマッピングが正常に適用されるよう改修。

2026/06/20 09:05:00 src/sst/builder.py: LLMの指示アクションが `use_mbz_search` または `use_local` の場合に、Steamストア情報（PICS_API）への不要なあいまい一致（Fuzzy Matching）フォールバックをスキップするようにロジックを修正。これにより、ファイル名前方一致等による誤プレフィックスマッチ（例: "Apartment america" が "Apartment" トラック3へ誤マッチする現象）と、それに伴うトラック番号の重複衝突バグを解消。

2026/06/20 09:17:00 Maintenance/batch_reprocess_verification.py: 今回発見されたバグの影響を受けた可能性のある21件のREVIEW対象アルバムに対し、個別に強制再処理を行い、それでもなお救われなかった（REVIEWステータスのままの）アルバムをデータベースから自動集計・抽出する検証用バッチスクリプトを新規作成。

2026/06/20 12:05:00 NG_List_001.md: 前回のバグ修正バッチ検証で「REVIEW」判定のまま救われなかった18件のアルバム情報とREVIEW要因、および傾向分析のマークダウンリストをワークスペースルートに新規作成。

2026/06/20 14:30:00 .env.example, docs/TAGGING_RULE.md, src/sst/track_grouper.py: 重複排除・グループ化ロジックの抜本的強化（提案1＆提案2 プランA）。ファイル名先頭にトラック番号がない場合でも埋め込みタグの track_number をフォールバックとしてグループ照合（t_num_val）に採用。また、.env の AUDIO_FORMAT_PRIORITY 設定（デフォルト: flac,alac,aiff,wav,mp3,m4a,ogg）を導入し、同一曲グループ内のファイルをその優先順位順に自動ソート。これにより、メタデータが欠落したロスレス（WAV等）に対しても優先度の低いロッシー（MP3等）から自動でタグをマージ・補完しつつ、最高音質ファイルを変換元として優先採用するフローを実現。La-Mulana（AppID: 396690）等のフォーマット混在・重複エラーを解消し、ARCHIVEへの正常救済を確認。

2026/06/20 18:06:00 NG_List_002.md: 重複排除や優先度マージの改修適用後、NG_List_001.md に記載された18件のアルバムを再検証し、依然として REVIEW 判定となった17件のリストと救済された La-Mulana（1件）の結果を記録した NG_List_002.md をワークスペースルートに新規作成。

2026/06/23 07:01:00 report/detailed_analysis_report.md: 全件FINGERPRINTチェックありの処理結果に対する詳細調査報告書（detailed_analysis_report.md）を report ディレクトリ内に新規作成。

2026/06/23 07:02:00 .agents/skills/sst-batch-inspector/: 全件バッチ処理データベースの全体統計および不自然なArchive/Review判定自動検知を再利用可能にするカスタムスキル sst-batch-inspector を新規追加。

2026/06/25 10:55:00 Repository: 未マージブランチ origin/doc-cleanup-20260616 を main にマージし、競合していた CHANGE_HISTORY.md を解消。取り込まれた変更により src/sst/{audio_tagger.py, track_grouper.py, virtual_album.py} を更新。

2026/06/26 21:10:00 src/sst/{processor.py,db.py}, Maintenance/analyze_processing_results.py: Review判定の根因追跡を強化。diagnosticsトレース（review_cause_code/upstream_cause_code/packager_invoked）をDB保存メタデータへ追加し、review message欠落時の警告、および原因別集計・DBとoutput/review整合チェックを分析スクリプトへ実装。

2026/06/26 21:21:00 src/sst/{config.py,llm.py,processor.py}, .env.example: Ollama応答の切断対策を実装。done_reason(length/max_tokens) による response_truncated 検知、切断時のチャンク自動縮小リトライ、LLM_OLLAMA_NUM_CTX/LLM_OLLAMA_NUM_PREDICT と LLM_CHUNK_* 系の環境変数化、およびメタデータ統合チャンクループの進行不具合修正を追加。

2026/06/27 00:22:40 docs/{LOGIC.md,error_handling.md,TAGGING_RULE.md}, src/sst/{validator.py,llm.py,packager.py}: ドキュメントと実装の乖離を是正。LLMタイムアウト/切断検知・可変Chunk設定・Diagnostics追跡の仕様を文書化し、VGMdb記述を削除、ZIP保存運用に説明を統一。あわせて最終判定閾値を通常 100/95、STEAM-TRUST は quality 75 へ更新し、実装と仕様を一致させた。

2026/06/27 00:40:00 src/sst/main.py, CHANGE_HISTORY.md: Option A を適用。未実装方針に合わせて CLI から `--finalize` 引数と `handle_finalize` 経路を完全削除し、ロック制御を通常フローへ一本化。ドキュメント方針（finalize未実装）との整合を確定。

2026/06/27 01:05:00 docs/{VIRTUAL_ALBUM_RULES.md,cache_architecture.md,data_flow_diagram.md,AGENT_GUIDE.md,Inference_Optimization.md}, CHANGE_HISTORY.md: ドキュメント整合性の5点修正を実施。仮想アルバム数を4系統（MBZ_SEARCH含む）へ統一、判定閾値を通常100/95・STEAM-TRUST品質75へ統一、キャッシュ層表記を `api_cache`（service/query_key）へ統一、AGENT_GUIDEにSTEAM-TRUST例外を明記、Inference_Optimization.mdを歴史資料として注記して現行仕様との混同を防止。

2026/06/27 05:49:44 report/doc_consistency_check_20260627.md, CHANGE_HISTORY.md: 主要ドキュメントを対象に最終整合チェック表を作成。コマンド名（--reset-db）、finalize未実装方針、Review ZIP運用、4仮想アルバム構成、判定閾値（通常100/95・STEAM-TRUST 75）、api_cache表記の一致を確認し、スコープ内を PASS と判定。

2026/06/27 05:53:35 README.md, CHANGE_HISTORY.md: README（日本語/英語）のIntroduction直下に、最終整合チェック表 `report/doc_consistency_check_20260627.md` への導線を追加。

2026/06/27 05:59:24 sst, README.md, docs/Parallel_Optimization.md, CHANGE_HISTORY.md: 不要候補の整理を実施。ランチャー `sst` から未実装の `--finalize` と旧互換 `--delete-db` を削除し、`--reset-db` 表記に統一。README（日英）へドキュメント導線（コア/運用/補助/エージェント/歴史資料）を追加。`docs/Parallel_Optimization.md` を歴史資料として注記し、現行仕様との混同を防止。

2026/06/27 06:00:50 docs/archive/{Inference_Optimization.md,Parallel_Optimization.md}, README.md, CHANGE_HISTORY.md: 提案メモ（歴史資料）を `docs/archive/` へ集約。README の歴史資料リンクを新パスへ更新し、通常仕様ドキュメントと履歴資料の境界を明確化。

2026/06/27 06:02:11 docs/SST.md, CHANGE_HISTORY.md: `docs/` ディレクトリ構造の説明に `docs/archive/` の1行注記を追加。提案メモ・検証時点資料は歴史資料であり、現行仕様の正本ではないことを明記。

2026/06/27 06:11:31 src/sst/{processor.py,processor_support.py}, CHANGE_HISTORY.md: 第1弾リファクタを実施。`processor.py` から補助責務（アルバムアート取得、通知送信、重複マッピング救済）を `processor_support.py` へ分離し、`LocalProcessor` 側は委譲ラッパーへ簡素化。既存の呼び出しインターフェースを維持して挙動互換を確保。

2026/06/27 07:27:42 src/sst/{processor.py,processor_tracks.py}, CHANGE_HISTORY.md: 第2弾リファクタを実施。`process_album` 内のトラック処理クロージャを `processor_tracks.py` の `process_single_track` へ分離。並列実行後に `had_warning/failed` フラグを集計する方式へ変更し、`processor.py` をオーケストレーション中心へ整理。

2026/06/30 18:35:00 sst
- `sst` ランチャースクリプトに実行権限 (chmod +x) を付与し、正常に起動できるよう修正しました。

2026/06/30 18:37:00 sst
- ドキュメント (GEMINI.md, LOGIC.md, error_handling.md, SKILL.md) および仕様について、テスト関連のスクリプトやログ出力先を `Maintenance` から `tests` ディレクトリへと変更しました。
- .gitignore から Maintenance/ ディレクトリの除外設定を解除（コメントアウト）しました。

2026/06/30 19:29:00 sst-system-monitor
- 今後のデバッグとフリーズ診断のため、S.S.T本体とOllamaのログを同時に監視・分析する手順を `.agents/skills/sst-system-monitor/SKILL.md` として新たに定義・追加しました。

2026/06/30 19:37:00 README.md
- FFmpegが必須であることを「セットアップと起動」および「Software」の項目（日本語・英語両方）に追記しました。

2026/06/30 20:08:00 docs/token_stingy.md
- LLMのコンテキストサイズ（num_ctx）を動的に算出し、VRAM消費を最適化するアーキテクチャ（Token Stingy戦略）のドキュメントを新規作成しました。

2026/06/30 20:41:00 src/sst/llm.py
- プロンプトに `USER_LANGUAGE` (`ja`) を強制し、Qwen等のモデルが中国語で回答してしまうのを防ぐための明示的なルール（ネイティブな日本語を使用し、中国語の語彙を避ける）を追記。

2026/07/01 01:15:00 src/sst/report_generator.py, GEMINI.md
- Option A の残件として `src/sst/report_generator.py` 内のHTMLレポートに出力される `--finalize` 実行の案内テキストを完全に削除。
- GEMINI.md に「コマンドが見つかりません」エラー時にユーザーへインストールをリクエストするルールを追記。

2026/07/01 02:15:00 docs/token_stingy.md
- 動的なVRAMスケジューリング（プレフライト・チェック、総VRAM自動検出、動的セマフォ）とAPI利用時のロジック分離に関する新しい並行処理アーキテクチャの仕様を反映し、全面書き換えを実施。

2026/07/01 02:18:00 docs/token_stingy.md
- 入力トークン予測ロジックをtiktokenからOllamaの /api/tokenize を利用した完全精度の算出ロジックへ変更。
- 80%の安全マージンが「トークン数」ではなく「システムの空きVRAM物理容量に対する上限閾値」であることを明文化。

2026/07/01 02:24:00 README.md, docs/LOGIC.md
- token_stingy.md における新仕様（動的VRAMセマフォと外部APIスレッドプールの分岐）を反映し、固定スレッド数ベースの並列処理（Tier-based Concurrency）の記述を完全に刷新。

2026/07/01 02:32:00 src/sst/track_grouper.py, tests/test_track_grouper.py, tests/run_tests.sh
- Maintenance ディレクトリから有用なテスト資産を抽出し移行。track_grouper.py 内のスマート正規化ロジックをテスト可能なメソッドへリファクタリングし、pytest形式の単体テストとして統合。
- ローカルテストランナー (run_tests.sh) を tests/ ディレクトリへ移動・再構築。

2026/07/01 02:37:00 src/sst/runner.py, src/sst/vram_manager.py
- Token Stingyアーキテクチャの根幹となる動的VRAMセマフォディスパッチャーを実装（vram_manager.py 新設）。
- runner.py の固定スレッドプールを廃止し、Ollama利用時にはVRAM空き容量に基づく自律的スケジューリングへ、外部API利用時にはレートリミットベースの制御へ動的分岐するよう改修。

2026/07/01 08:33:00 src/sst/llm.py, docs/token_stingy.md, docs/LOGIC.md
- VRAM保護目的の固定チャンク分割（10曲など）をOllama環境において撤廃し、モデルの出力限界まで動的にチャンクサイズを最大化（One-shot化）するよう `_adaptive_chunk_size` を改修。
- Ollama APIへのリクエストパラメータに `num_predict: -1` を付与し、モデルがコンテキスト長の限界まで途切れずに出力できるようリミッターを解除。

2026/07/01 08:50:00 .env.example, src/sst/config.py, src/sst/llm.py
- クラウドAPI利用時の適応型チャンクアルゴリズムを刷新。設定ファイルに `LLM_LIMIT_TPM` および `LLM_CLOUD_MAX_TOKENS` を新設し、「TPM限界（毎分トークン枯渇による429エラー回避）」と「出力トークン限界」の双方を考慮して、外部APIでも安全に限界までOne-shot処理できるよう改修。
- OpenAI互換およびGemini APIリクエスト時に `max_tokens` (出力限界) を明示的に付与するよう実装。

2026/07/01 11:10:00 docs/token_stingy.md, docs/LOGIC.md, README.md
- 外部API向けに適応型チャンク・アルゴリズムが実装されたことに伴い、公式ドキュメントを更新。
- `README.md` にシステムカスタマイズ項目を新設し、`LLM_LIMIT_*` 関連のパラメータが429エラー回避およびコンテキスト最大化に果たす役割と、`MAX_ENCODING_TASKS` 等の並列制御パラメータの詳細を追記。

2026/07/01 11:17:00 .env.example, README.md, docs/token_stingy.md, docs/LOGIC.md
- Ollama使用時の `LLM_OLLAMA_NUM_PREDICT` が、実際のAPI制限（-1）ではなく「モデルが幻覚を起こさずに出力できる信頼度の天井（チャンク計算の数学的上限）」として機能する仕様について、各ドキュメントおよび設定ファイルのコメントを正確に更新。

2026/07/01 11:20:00 .env.example, README.md
- Ollama使用時の `LLM_OLLAMA_NUM_CTX` について、「単純なモデル上限指定」だけでなく、「VRAMのKVキャッシュ消費量を意図的に制限し、全体の並列実行数を引き上げるためのチューニングパラメータ」として機能する点をドキュメントに明記。

2026/07/01 11:34:00 .env.example, src/sst/config.py, README.md
- VRAM動的セマフォ制御への移行により完全にデッドコードとなっていたティア制の並行パラメータ（`MAX_PARALLEL_SMALL/MEDIUM/LARGE`）をシステムおよび設定ファイルから完全に削除。
- `MAX_PARALLEL_ALBUMS` の機能が「絶対最大数」ではなく「クラウドAPI利用時の強制底上げ用下限値」であるという現在の正しいロジックをドキュメントに反映。
- 2026/07/01 14:23:00, src/sst/vram_manager.py, VRAM要求サイズがシステムの最大空き容量を超過した場合にデッドロックする問題を修正。要求サイズを最大予算にクリップし、CPUオフロードを許容して単独実行させる安全装置を追加。
- 2026/07/01 14:52:00, src/sst/llm.py, src/sst/processor.py, src/sst/config.py, .env.example, 超巨大アルバム処理時のコンテキスト溢れを防止するためのPhase 1.5: Coherence Map-Reduce（階層型分割ルーティング）を実装。設定LLM_COHERENCE_THRESHOLD(デフォルト75曲)を追加し、超過時は自動でサブアルバムへ分割処理する。
2026/07/01 22:15:00 report/NG_Duplicates.md および report/NG_Dirty_Tags.md を新規作成し、テスト実行ログから Duplicates および Dirty Tags が原因で Review 判定となった AppID とその理由を抽出・一覧化しました。
2026/07/01 22:52:00 src/sst/llm.py, docs/exception_handling.md - LLMの推論結果がnullの場合のフォールバック処理を実装し、複数のサウンドトラックが同一ディレクトリにインストールされるケースへの例外処理仕様を新規作成しました。

2026/07/01 23:13:00 src/sst/vram_manager.py
- Ollamaの `/api/tokenize` が利用できず404エラーとなる問題に対処するため、`tiktoken` を導入し、エラー時はローカルで高精度にトークン数を推論できるフォールバック処理を実装しました。これにより、VRAM割り当てディスパッチ精度の低下を防ぎます。

2026/07/01 23:17:00 docs/token_stingy.md, README.md
- VRAMスケジュール最適化のための `tiktoken` フォールバック機構がシステムに組み込まれたことを仕様としてドキュメント化し、READMEの機能一覧にも追記しました。

2026/07/02 05:30:07 src/sst/{llm.py,processor.py,builder.py}, docs/{SST.md,TAGGING_RULE.md}, CHANGE_HISTORY.md
- ドキュメント点検で見つかった実装乖離の是正を実施。`LLMOrganizer` のクラウドAPI向け適応チャンク計算から壊れていた `self.config` 参照を排除し、`LLM_CLOUD_MAX_TOKENS` / `LLM_LIMIT_TPM` をインスタンス属性として保持する形へ修正。Gemini/OpenAI互換リクエストへ `max_tokens` を常時反映するよう整理しました。
- あわせて `llm.py` と `builder.py` に残っていたタグ優先順位の既定値を `Config` の正本に揃え、既定値の分裂を解消しました。
- 仕様書側では、`docs/SST.md` の3層API説明を実装どおり「Steam Web APIの公式タグ取得」中心に更新し、`appinfo.vdf` は補助ソースである旨を明記。`docs/TAGGING_RULE.md` では未実装だったバイリンガルタイトル自動生成の記述を撤回し、実際の `COMM` マージ仕様・`TIT1` 表記・`APIC` 選択仕様へ修正しました。

2026/07/02 05:43:40 src/sst/{config.py,llm.py,builder.py}, .env.example, README.md, docs/{LOGIC.md,TAGGING_RULE.md,VIRTUAL_ALBUM_RULES.md}, CHANGE_HISTORY.md
- メタデータ優先順位のフォールバック文字列を `src/sst/config.py` に集約し、`llm.py` と `builder.py` に残っていた直書き既定値を同ファイルの定数参照へ置き換えました。これにより、`.env` 未設定時のソース優先順位が単一の正本から供給される構成へ整理されました。
- あわせて `.env.example`、README、および仕様書群へ「ユーザー設定は `.env`、未設定時のフォールバックは `src/sst/config.py`」という現在の実装方針を明記し、`VIRTUAL_ALBUM_RULES.md` のフィールド優先順位説明も現行既定値へ更新しました。

2026/07/02 05:46:26 docs/{api_rate_limit.md,Virtual_Album.md,TEST_ENVIRONMENT.md}, CHANGE_HISTORY.md
- 補助仕様書の残件を是正。`api_rate_limit.md` の MusicBrainz 待機時間を実装どおり `time.sleep(1.1)` ベースへ更新しました。
- `Virtual_Album.md` では、`qwen2.5:7b` を現行標準モデルと断定していた記述を、プロトタイプ時の評価対象であった旨へ修正し、現行は `.env` / `Config` で切り替える方式であると明記しました。
- `TEST_ENVIRONMENT.md` では、代表 AppID 群をハードコード必須ケースではなく推奨例として位置づけ直し、`COMM` 検証項目も既存コメント保持を含む現行のマージ仕様に合わせて更新しました。

2026/07/02 06:00:11 src/sst/{config.py,llm.py,builder.py,processor.py,processor_tracks.py}, docs/LOGIC.md, CHANGE_HISTORY.md
- `llm.py` に残っていた未使用の旧統合経路 `consolidate_metadata()` を削除し、現行の仮想アルバム統合入口を `consolidate_virtual_albums()` に一本化しました。
- メタデータ優先順位を `PriorityConfig` 型として `config.py` に追加し、`processor_tracks.py` から `MetadataBuilder` への受け渡しを辞書直組みではなく型経由に整理しました。
- あわせて `Config.build_mbz_scoring_config()` と `Config.build_llm_organizer_kwargs()` を追加し、`processor.py` のコンストラクタから MusicBrainz スコア辞書および LLM 初期化引数の手組みロジックを追い出しました。`docs/LOGIC.md` にもこの構成整理を反映しました。
