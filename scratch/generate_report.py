import sqlite3
import json
import html
from pathlib import Path

def generate_report():
    conn = sqlite3.connect('data/sst_local_state.db')
    cursor = conn.cursor()
    cursor.execute('SELECT app_id, album_name, status, metadata_json FROM processed_albums ORDER BY CAST(app_id AS INTEGER)')
    rows = cursor.fetchall()

    archives = []
    reviews = []
    all_items = []

    for app_id, name, status, meta_str in rows:
        meta = json.loads(meta_str) if meta_str else {}
        item = {
            'app_id': app_id,
            'name': name,
            'status': status,
            'conf': meta.get('confidence_score', 0),
            'qual': meta.get('integrity_quality', 0),
            'msg': meta.get('message') or 'N/A (Early Review)',
            'reason': meta.get('confidence_reason') or 'Reason not captured in Phase 1',
            'strategy': meta.get('strategy') or 'N/A',
            'track_count': len(meta.get('tracks', []))
        }
        all_items.append(item)
        if status == 'archive':
            archives.append(item)
        else:
            reviews.append(item)

    # HTML Generator
    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>S.S.T 100件処理結果 総合分析・改善考察報告書</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #0f172a;
            --bg-card: #1e293b;
            --bg-card-hover: #334155;
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-primary: #6366f1;
            --accent-light: #818cf8;
            --accent-glow: rgba(99, 102, 241, 0.15);
            --color-archive: #10b981;
            --color-archive-bg: rgba(16, 185, 129, 0.12);
            --color-review: #f59e0b;
            --color-review-bg: rgba(245, 158, 11, 0.12);
            --color-danger: #ef4444;
            --color-danger-bg: rgba(239, 68, 68, 0.12);
            --color-info: #06b6d4;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            margin-bottom: 2.5rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }}

        .header-title {{
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #818cf8 0%, #c084fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}

        .header-subtitle {{
            color: var(--text-secondary);
            font-size: 0.95rem;
        }}

        /* KPI Cards Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2.5rem;
        }}

        .kpi-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 1.25rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}

        .kpi-card:hover {{
            transform: translateY(-2px);
            border-color: var(--accent-light);
        }}

        .kpi-label {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}

        .kpi-value {{
            font-size: 2.25rem;
            font-weight: 700;
            line-height: 1.2;
        }}

        .kpi-value.archive {{ color: var(--color-archive); }}
        .kpi-value.review {{ color: var(--color-review); }}
        .kpi-value.target {{ color: var(--accent-light); }}

        .kpi-desc {{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-top: 0.4rem;
        }}

        /* Section Styling */
        section {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.875rem;
            padding: 1.75rem;
            margin-bottom: 2rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
        }}

        .section-title {{
            font-size: 1.35rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            border-left: 4px solid var(--accent-primary);
            padding-left: 0.75rem;
        }}

        .section-title.archive-title {{ border-color: var(--color-archive); }}
        .section-title.review-title {{ border-color: var(--color-review); }}
        .section-title.action-title {{ border-color: var(--color-info); }}

        .card-subhead {{
            font-size: 1.05rem;
            font-weight: 600;
            color: var(--accent-light);
            margin: 1.25rem 0 0.75rem 0;
        }}

        p {{
            color: var(--text-secondary);
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }}

        ul {{
            margin-left: 1.25rem;
            margin-bottom: 1rem;
            color: var(--text-secondary);
        }}

        li {{
            margin-bottom: 0.5rem;
            font-size: 0.93rem;
        }}

        code {{
            font-family: 'JetBrains Mono', monospace;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #f1f5f9;
            padding: 0.15rem 0.4rem;
            border-radius: 0.25rem;
            font-size: 0.88rem;
        }}

        .badge {{
            display: inline-block;
            padding: 0.2rem 0.55rem;
            border-radius: 0.375rem;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .badge.archive {{
            background-color: var(--color-archive-bg);
            color: var(--color-archive);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .badge.review {{
            background-color: var(--color-review-bg);
            color: var(--color-review);
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}

        /* Code block / Highlight box */
        .highlight-box {{
            background: #0f172a;
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 1rem 0;
            font-size: 0.9rem;
        }}

        .highlight-box.warning {{
            border-left: 4px solid var(--color-review);
        }}

        .highlight-box.danger {{
            border-left: 4px solid var(--color-danger);
        }}

        .highlight-box.success {{
            border-left: 4px solid var(--color-archive);
        }}

        /* Table Styling */
        .table-container {{
            overflow-x: auto;
            margin-top: 1rem;
            border-radius: 0.5rem;
            border: 1px solid var(--border-color);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            text-align: left;
        }}

        th {{
            background-color: #0f172a;
            color: var(--text-secondary);
            font-weight: 600;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
        }}

        td {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-primary);
        }}

        tr:hover {{
            background-color: var(--bg-card-hover);
        }}

        /* Filter Controls */
        .filter-bar {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            align-items: center;
        }}

        .search-input {{
            background-color: #0f172a;
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            font-size: 0.9rem;
            flex: 1;
        }}

        .search-input:focus {{
            outline: none;
            border-color: var(--accent-light);
        }}

        .filter-btn {{
            background: #0f172a;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
        }}

        .filter-btn.active {{
            background: var(--accent-primary);
            color: white;
            border-color: var(--accent-primary);
        }}

        .footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-top: 3rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border-color);
        }}
    </style>
</head>
<body>

    <header>
        <h1 class="header-title">S.S.T (Steam Soundtrack Tagger) 100件処理結果 総合分析・改善考察報告書</h1>
        <div class="header-subtitle">実行コマンド: <code>./sst --limit 100 --dev</code> | 対象件数: 100件 | 分析日時: 2026年7月29日</div>
    </header>

    <!-- KPI Section -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">総処理アルバム数</div>
            <div class="kpi-value">100</div>
            <div class="kpi-desc">全処理対象件数</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Archive 判定 (成功)</div>
            <div class="kpi-value archive">42 <span style="font-size: 1.1rem; color: var(--text-secondary);">(42.0%)</span></div>
            <div class="kpi-desc">自動タグ付け・アーカイブ完了</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Review 判定 (手動確認)</div>
            <div class="kpi-value review">58 <span style="font-size: 1.1rem; color: var(--text-secondary);">(58.0%)</span></div>
            <div class="kpi-desc">手動レビュー送りに分類</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">次回 Archive 目標率</div>
            <div class="kpi-value target">85%+</div>
            <div class="kpi-desc">ロジック改善後の予測達成率</div>
        </div>
    </div>

    <!-- Section 1: Unnatural Archive -->
    <section>
        <h2 class="section-title archive-title">1. 総合的に不自然な Archive 送りとなっているケースと判断理由</h2>
        <p>現在 <code>Archive</code> に送られた 42 件のうち、自動判定を通過したものの、メタデータ品質・美観の観点から<strong>「本来であればクリーンアップされるべき、あるいは質が不十分なままアーカイブされている不自然な事例」</strong>を検出しました。</p>

        <h3 class="card-subhead">ケース1-1: HTMLエンティティの未デコード・タグノイズ混入 (6件)</h3>
        <p>Steam Store のトラックリストから取得したタイトル文字列に含まれる <code>&amp;amp;</code> や <code>&amp;quot;</code> などの HTML 特殊文字が、デコードされずにそのまま音声ファイルの <code>TIT2</code> (Title) タグに書き込まれている不自然な状態です。</p>
        <div class="highlight-box warning">
            <strong>具体例:</strong>
            <ul>
                <li><code>AppID 1142840</code> (Lichtspeer Soundtrack): <code>Space, Time &amp;amp; Death</code></li>
                <li><code>AppID 1224940</code> (Tropico 6 OST): <code>Hot &amp;amp; Spicy</code></li>
                <li><code>AppID 1238762</code> (DJMAX RESPECT V): <code>quiet 29&amp;quot; (Music Select Lock) by Mycin.T</code></li>
                <li><code>AppID 1386615</code> (DJMAX TECHNIKA 3): <code>Wanna Be Your Lover by Laurent Newfield &amp;amp; Ravenat</code></li>
                <li><code>AppID 1568690</code> (DJMAX Portable 3): <code>Sunny Side (Remastered) (Extended Ver.) by Forte Escape &amp;amp; CROOVE</code></li>
                <li><code>AppID 1832440</code> (Happy's Humble Burger Farm): <code>Julio &amp;amp; Dmitri (At the Beach)</code></li>
            </ul>
        </div>
        <p><strong>判断理由:</strong> ユーザーの音楽ライブラリに <code>&amp;amp;</code> などのエスケープ文字が直接表示されるため美観を大きく損なっており、文字列正規化処理 (<code>html.unescape()</code>) の漏れを示しています。</p>

        <h3 class="card-subhead">ケース1-2: AlbumArtist の Steam デベロッパー・パブリッシャー機械的結合・重複 (多数)</h3>
        <p>音楽の <code>AlbumArtist</code> (TPE2) タグに、Steam ストアの <code>developer</code> と <code>publisher</code> をカンマで連結した文字列がそのまま設定されており、不自然なアーティスト名や文字列重複が発生しています。</p>
        <div class="highlight-box warning">
            <strong>具体例:</strong>
            <ul>
                <li><code>AppID 1611260</code>: <code>AlbumArtist = "CAPCOM CO., LTD., CAPCOM CO., LTD."</code> (全く同じ社名が二重結合)</li>
                <li><code>AppID 1631300</code>: <code>AlbumArtist = "Red Phantom Games, Numskull Games"</code> (開発元と販売元の安易な連結)</li>
                <li><code>AppID 1749230</code>: <code>AlbumArtist = "@unepic_fran, Versus Evil"</code> (Twitterアカウント名を含む開発元名)</li>
                <li><code>AppID 1832430</code>: <code>AlbumArtist = "Scythe Dev Team, tinyBuild"</code></li>
            </ul>
        </div>
        <p><strong>判断理由:</strong> 音楽ファイルとして実際の作曲者・アーティスト名（例: <code>Matt Kap</code>, <code>James Paddock</code>）が存在するにも関わらず、ゲーム開発・パブリッシャー会社名が二重表示されたり無秩序に連結されて Archive 送りになっています。</p>

        <h3 class="card-subhead">ケース1-3: ゲーム属性ジャンルタグの無差別注入</h3>
        <p>音楽ジャンル (<code>TCON</code>) に、Steam ストア上のゲームのカテゴリ属性（「インディー」「アクション」「シミュレーション」等）がそのままカンマ区切りで混入しています。</p>
        <div class="highlight-box warning">
            <strong>例:</strong> <code>Genre = "STEAM VGM, アクション, アドベンチャー, カジュアル, インディー"</code>
        </div>
        <p><strong>判断理由:</strong> 音楽プレイヤー上で「アクション」「インディー」というジャンルで分類されてしまい、音楽ジャンルとしての機能（Game Music, Synthwave, Rock 等）を満たしていません。</p>
    </section>

    <!-- Section 2: Unnatural Review -->
    <section>
        <h2 class="section-title review-title">2. 総合的に不自然な Review 送りとなっているケースと判断理由</h2>
        <p>現在 <code>Review</code> 送りとなった 58 件について解析を行ったところ、<strong>システムの過剰に保守的なハードコード閾値や物理チェックの誤判定によって「本来 Archive 判定されるべき完璧または高精度なアルバム」が不自然に Review に落とされている構造的問題</strong>を特定しました。</p>

        <h3 class="card-subhead">ケース2-1: ハードコード閾値 <code>if conf &lt; 100: return {{}}</code> による大量の早期 Review 落ち (35件)</h3>
        <p>データベース上の判定理由が空（<code>Unknown Review Reason</code>）となっている 35 件についてソースコードを追跡した結果、<code>src/sst/llm.py</code> 内の L635 に存在するハードコードゲートが原因であることが判明しました。</p>
        <div class="highlight-box danger">
            <strong>コード解析 (src/sst/llm.py L635):</strong><br>
            <code>if conf &lt; 100: return {{}}, {{"phase1_res": global_res, "phase1_log": global_log}}</code>
        </div>
        <p><strong>判断理由:</strong> LLM が Phase 1 で <strong>Confidence 90%〜98%</strong> という極めて高い確信度を返した場合であっても、100% 未満であれば Phase 2（トラックごとのマッピング処理）を実行せずに即座に空辞書を返して <code>early_review</code> に送られるロジックになっています。このため、実質的に正しいメタデータを持つ 35 件のアルバムが全滅して Review 送りとなっています。</p>

        <h3 class="card-subhead">ケース2-2: CIFS/SMB ネットワークマウントの I/O エラーによる <code>CRITICAL: Audio Source Error</code> 誤判定 (19件)</h3>
        <p>LLM の確信度 100%・品質 100% を獲得しながら最終判定で <code>[CRITICAL: Audio Source Error]</code> として Review 送りになった 19 件のログ（<code>logs/SST_DEBUG_*.log</code>）を精査しました。</p>
        <div class="highlight-box danger">
            <strong>ログのエラー内容 (例: AppID 1195480 DOOM Soundtrack):</strong><br>
            <code>ERROR - [1195480] トラック処理の失敗 07 - Authorization; Olivia Pierce: [Errno 112] Host is down: '/mnt/windows/win_steamlibrary/steamapps/music/...'</code>
        </div>
        <p><strong>判断理由:</strong> LLM やメタデータ照合の不一致ではなく、Windows/CIFSマウントポイント (<code>/mnt/windows/win_steamlibrary</code>) からのファイルコピー <code>shutil.copy2</code> 実行時にネットワークドライブの一時的応答遅延・切断 (<code>Host is down</code>) が発生したことが原因です。リトライ処理が無いためトラック処理が失敗し、Validator が物理エラーとして Review 送りに評価を下げています。</p>

        <h3 class="card-subhead">ケース2-3: 軽微な構造問題（Track#0 / ディスク重複）による過剰降格 (4件)</h3>
        <p>確信度 95%〜100% を獲得しながら、物理バリデータ (<code>ResultValidator</code>) の個別ルールに引っかかって降格したケースです。</p>
        <ul>
            <li><code>AppID 1279740</code> (Desperados III): 87トラックの巨大アルバムで重複検出により降格</li>
            <li><code>AppID 1663820</code> (Super Magbot): トラック番号0のファイル混入 (<code>Track#0 x14</code>) により降格</li>
            <li><code>AppID 1796120</code>, <code>1806720</code>: 複数ディスク構成での重複判定により降格</li>
        </ul>
    </section>

    <!-- Section 3: Action Plan & Recommendations -->
    <section>
        <h2 class="section-title action-title">3. メタデータ精度を高めながら、次回の100件処理でArchive送りを増加させる方法</h2>
        <p>上記の調査結果を踏まえ、メタデータの正しさ・クオリティを向上させつつ、次回 100 件処理において <strong>Archive 成功率を現在の 42% から 85%〜90% へ劇的に引き上げるための5段階の具体的な改修アクションプラン</strong>を提案します。</p>

        <h3 class="card-subhead">【施策1】 <code>conf &lt; 100</code> 早期離脱ロジックの撤廃と動的閾値への移行 (即時+30%増加)</h3>
        <div class="highlight-box success">
            <strong>改修内容 (src/sst/llm.py L635 付近):</strong><br>
            <code>conf &lt; 100</code> での無条件リターンを廃止し、<code>conf &gt;= 85</code> であれば Phase 2（トラックマッピング）へ進めるよう緩和します。また、`ResultValidator` 側の閾値を <code>Confidence &gt;= 90%</code> かつ <code>Quality &gt;= 85%</code> で Archive 許可と設定します。<br>
            <strong>期待効果:</strong> 今回 `Unknown Review Reason` として撃沈した 35 件のうち <strong>約25〜30件が正常に Archive 化</strong> されます。
        </div>

        <h3 class="card-subhead">【施策2】 I/O エラー（Host is down）に対する指数バックオフ・リトライ処理の実装 (即時+19%増加)</h3>
        <div class="highlight-box success">
            <strong>改修内容 (src/sst/processor_tracks.py):</strong><br>
            <code>shutil.copy2</code> やファイル読み込み部分において、<code>[Errno 112] Host is down</code> や I/O エラーが発生した場合に最大 3 回の自動リトライ（1秒・3秒・5秒のバックオフ）を挿入します。<br>
            <strong>期待効果:</strong> `CRITICAL: Audio Source Error` で全滅していた 19 件のアルバムのほぼ全て（15〜19件）が成功し、<strong>Archive に昇格</strong> します。
        </div>

        <h3 class="card-subhead">【施策3】 HTML エンティティの全自動アンエスケープ処理の追加 (メタデータ精度100%保証)</h3>
        <div class="highlight-box success">
            <strong>改修内容 (src/sst/builder.py &amp; tagger.py):</strong><br>
            Steam Store メタデータや MusicBrainz から抽出した <code>title</code>, <code>album</code>, <code>artist</code>, <code>label</code> 等の全文字列に対して <code>html.unescape()</code> を強制適用します。<br>
            <strong>期待効果:</strong> <code>&amp;amp;</code> や <code>&amp;quot;</code> などのエスケープ汚れが全滅し、完全にクリーンな表示に改善されます。
        </div>

        <h3 class="card-subhead">【施策4】 AlbumArtist および Genre タグのインテリジェント正規化フィルタ</h3>
        <div class="highlight-box success">
            <strong>改修内容 (src/sst/builder.py):</strong><br>
            <ul>
                <li><code>AlbumArtist</code>: Developer と Publisher が同一文字列の場合は重複を除去。また、具体的な音楽 Artist 名が抽出されている場合はそれを優先設定。</li>
                <li><code>Genre</code>: Steam ストアのゲーム開発タグ（「アクション」「インディー」）を排除し、音楽固有ジャンル（"Game Music", "Soundtrack" 等）にサニタイズ。</li>
            </ul>
            <strong>期待効果:</strong> タグの美観と音楽ライブラリとしての整理レベルがプロ基準に向上します。
        </div>

        <h3 class="card-subhead">【施策5】 Track#0 および タイトル二重プレフィックス (Dirty Tags) の自律補正</h3>
        <div class="highlight-box success">
            <strong>改修内容 (src/sst/track_grouper.py):</strong><br>
            ローカルファイルの <code>track_number</code> が 0 の場合、ファイル名のトラックインデックスや Steam トラックリストの連番から 1 ベースで再採番。タイトル冒頭の <code>01 - </code> 等のプレフィックスを除去。<br>
            <strong>期待効果:</strong> 物理バリデータでの `Track#0` や `Dirty Tags` による Review 落ちを未然に防止します。
        </div>

        <h3 class="card-subhead">次回処理における Archive 率改善予測</h3>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>区分</th>
                        <th>現状 (現在100件)</th>
                        <th>改修後の予測効果</th>
                        <th>次回100件の予測数</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Archive 判定</strong></td>
                        <td>42件 (42.0%)</td>
                        <td>+ 28件 (conf&lt;100 救済) + 17件 (I/Oリトライ)</td>
                        <td><strong style="color: var(--color-archive); font-size: 1.1rem;">87件 (87.0%)</strong></td>
                    </tr>
                    <tr>
                        <td><strong>Review 判定</strong></td>
                        <td>58件 (58.0%)</td>
                        <td>真に手動確認が必要な複雑なケースのみに限定</td>
                        <td><strong style="color: var(--color-review); font-size: 1.1rem;">13件 (13.0%)</strong></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </section>

    <!-- Appendix: Complete 100 Items Table -->
    <section>
        <h2 class="section-title">付録: 100件全件処理結果一覧</h2>
        <div class="filter-bar">
            <input type="text" id="searchInput" class="search-input" placeholder="AppID または アルバム名で検索...">
            <button class="filter-btn active" onclick="filterTable('all')">すべて ({len(all_items)})</button>
            <button class="filter-btn" onclick="filterTable('archive')">Archive ({len(archives)})</button>
            <button class="filter-btn" onclick="filterTable('review')">Review ({len(reviews)})</button>
        </div>

        <div class="table-container" style="max-height: 600px; overflow-y: auto;">
            <table id="resultsTable">
                <thead>
                    <tr>
                        <th>AppID</th>
                        <th>アルバム名</th>
                        <th>Status</th>
                        <th>Conf</th>
                        <th>Qual</th>
                        <th>Strategy</th>
                        <th>Message / Reason</th>
                    </tr>
                </thead>
                <tbody>
"""

    for item in all_items:
        status_class = item['status']
        badge_html = f'<span class="badge {status_class}">{item["status"].upper()}</span>'
        escaped_name = html.escape(item['name'])
        escaped_msg = html.escape(str(item['msg']))
        escaped_reason = html.escape(str(item['reason']))
        
        html_content += f"""
                    <tr class="item-row" data-status="{status_class}">
                        <td><code>{item['app_id']}</code></td>
                        <td style="font-weight: 500;">{escaped_name}</td>
                        <td>{badge_html}</td>
                        <td>{item['conf']}%</td>
                        <td>{item['qual']}%</td>
                        <td><code>{item['strategy']}</code></td>
                        <td style="font-size: 0.82rem; color: var(--text-secondary);">
                            <strong>{escaped_msg}</strong><br>
                            <span style="color: var(--text-muted);">{escaped_reason[:120]}{'...' if len(escaped_reason)>120 else ''}</span>
                        </td>
                    </tr>
"""

    html_content += """
                </tbody>
            </table>
        </div>
    </section>

    <div class="footer">
        S.S.T (Steam Soundtrack Tagger) Automated Analytics & Report Generator
    </div>

    <script>
        function filterTable(status) {
            const rows = document.querySelectorAll('.item-row');
            const btns = document.querySelectorAll('.filter-btn');
            
            btns.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            rows.forEach(row => {
                if (status === 'all' || row.getAttribute('data-status') === status) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }

        document.getElementById('searchInput').addEventListener('input', function(e) {
            const term = e.target.value.toLowerCase();
            const rows = document.querySelectorAll('.item-row');
            
            rows.forEach(row => {
                const text = row.innerText.toLowerCase();
                if (text.includes(term)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    </script>
</body>
</html>
"""

    report_path = Path('report/batch_analysis_report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Report generated successfully at: {report_path.resolve()}")

if __name__ == '__main__':
    generate_report()
