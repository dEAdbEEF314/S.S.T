import sqlite3
import json
import html
import re
import glob
from pathlib import Path

def analyze_and_generate_report(db_path='data/sst_local_state.db', output_dir='report'):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT app_id, album_name, status, metadata_json FROM processed_albums ORDER BY CAST(app_id AS INTEGER)')
    rows = cursor.fetchall()

    archives = []
    reviews = []
    all_items = []

    unnatural_archives = []
    unnatural_reviews_conf = []
    unnatural_reviews_io = []
    unnatural_reviews_minor = []

    # Check debug logs for I/O errors
    log_files = glob.glob('logs/*.log')
    io_error_app_ids = set()
    for lf in log_files:
        try:
            with open(lf, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'トラック処理の失敗' in line and ('Host is down' in line or 'Errno' in line or 'Permission denied' in line):
                        m = re.search(r'\[(\d+)\]', line)
                        if m:
                            io_error_app_ids.add(int(m.group(1)))
        except Exception:
            pass

    for app_id, name, status, meta_str in rows:
        meta = json.loads(meta_str) if meta_str else {}
        tracks = meta.get('tracks', [])
        conf = meta.get('confidence_score', 0)
        qual = meta.get('integrity_quality', 0)
        msg = meta.get('message') or 'N/A (Early Review)'
        reason = meta.get('confidence_reason') or 'No reason captured'
        strategy = meta.get('strategy') or 'N/A'

        item = {
            'app_id': app_id,
            'name': name,
            'status': status,
            'conf': conf,
            'qual': qual,
            'msg': msg,
            'reason': reason,
            'strategy': strategy,
            'track_count': len(tracks),
            'meta': meta
        }
        all_items.append(item)

        if status == 'archive':
            archives.append(item)
            # Scan for unnatural archive issues
            issues = []
            html_entities = []
            dirty_artist = False

            for t in tracks:
                tags = t.get('tags', {})
                title = str(tags.get('title', ''))
                a_art = str(tags.get('artist', ''))
                alb_art = str(tags.get('album_artist', ''))

                if any(e in title for e in ['&amp;', '&quot;', '&#39;', '&lt;', '&gt;']):
                    html_entities.append(title)
                if ',' in alb_art and alb_art.split(',')[0].strip() == alb_art.split(',')[1].strip():
                    dirty_artist = True

            if html_entities:
                issues.append(f"HTMLエンティティ未デコード ({len(html_entities)}トラック): 例 \"{html_entities[0]}\"")
            if dirty_artist:
                issues.append("AlbumArtist名に社名の二重重複が発生")

            if issues:
                unnatural_archives.append({
                    'app_id': app_id,
                    'name': name,
                    'issues': issues
                })

        else:
            reviews.append(item)
            app_id_int = int(app_id) if str(app_id).isdigit() else app_id

            if msg == 'N/A (Early Review)' or 'No LLM response' in reason or conf < 100:
                unnatural_reviews_conf.append(item)
            elif app_id_int in io_error_app_ids or 'CRITICAL: Audio Source Error' in msg:
                unnatural_reviews_io.append(item)
            else:
                unnatural_reviews_minor.append(item)

    # HTML Generation
    report_file = output_path / 'batch_analysis_report.html'

    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>S.S.T 処理後総合調査・改善報告書</title>
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
            --color-archive: #10b981;
            --color-archive-bg: rgba(16, 185, 129, 0.12);
            --color-review: #f59e0b;
            --color-review-bg: rgba(245, 158, 11, 0.12);
            --color-danger: #ef4444;
            --color-info: #06b6d4;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
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
        .header-subtitle {{ color: var(--text-secondary); font-size: 0.95rem; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2.5rem;
        }}
        .kpi-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 1.25rem;
            transition: transform 0.2s ease;
        }}
        .kpi-card:hover {{ transform: translateY(-2px); }}
        .kpi-label {{ font-size: 0.85rem; color: var(--text-secondary); font-weight: 500; text-transform: uppercase; margin-bottom: 0.5rem; }}
        .kpi-value {{ font-size: 2.25rem; font-weight: 700; }}
        .kpi-value.archive {{ color: var(--color-archive); }}
        .kpi-value.review {{ color: var(--color-review); }}
        .kpi-value.target {{ color: var(--accent-light); }}
        section {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.875rem;
            padding: 1.75rem;
            margin-bottom: 2rem;
        }}
        .section-title {{
            font-size: 1.35rem; font-weight: 600; margin-bottom: 1.25rem;
            border-left: 4px solid var(--accent-primary); padding-left: 0.75rem;
        }}
        .section-title.archive-title {{ border-color: var(--color-archive); }}
        .section-title.review-title {{ border-color: var(--color-review); }}
        .section-title.action-title {{ border-color: var(--color-info); }}
        .card-subhead {{ font-size: 1.05rem; font-weight: 600; color: var(--accent-light); margin: 1.25rem 0 0.75rem 0; }}
        p {{ color: var(--text-secondary); margin-bottom: 1rem; font-size: 0.95rem; }}
        ul {{ margin-left: 1.25rem; margin-bottom: 1rem; color: var(--text-secondary); }}
        li {{ margin-bottom: 0.5rem; font-size: 0.93rem; }}
        code {{ font-family: 'JetBrains Mono', monospace; background: rgba(15, 23, 42, 0.6); padding: 0.15rem 0.4rem; border-radius: 0.25rem; font-size: 0.88rem; }}
        .highlight-box {{ background: #0f172a; border: 1px solid var(--border-color); border-radius: 0.5rem; padding: 1rem; margin: 1rem 0; }}
        .highlight-box.warning {{ border-left: 4px solid var(--color-review); }}
        .highlight-box.danger {{ border-left: 4px solid var(--color-danger); }}
        .highlight-box.success {{ border-left: 4px solid var(--color-archive); }}
        .table-container {{ overflow-x: auto; margin-top: 1rem; border-radius: 0.5rem; border: 1px solid var(--border-color); }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left; }}
        th {{ background-color: #0f172a; color: var(--text-secondary); font-weight: 600; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); }}
        td {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); }}
        tr:hover {{ background-color: var(--bg-card-hover); }}
        .badge {{ display: inline-block; padding: 0.2rem 0.55rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
        .badge.archive {{ background-color: var(--color-archive-bg); color: var(--color-archive); border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge.review {{ background-color: var(--color-review-bg); color: var(--color-review); border: 1px solid rgba(245, 158, 11, 0.3); }}
        .filter-bar {{ display: flex; gap: 1rem; margin-bottom: 1rem; align-items: center; }}
        .search-input {{ background-color: #0f172a; border: 1px solid var(--border-color); color: var(--text-primary); padding: 0.5rem 1rem; border-radius: 0.375rem; flex: 1; }}
        .filter-btn {{ background: #0f172a; border: 1px solid var(--border-color); color: var(--text-secondary); padding: 0.5rem 1rem; border-radius: 0.375rem; cursor: pointer; }}
        .filter-btn.active {{ background: var(--accent-primary); color: white; border-color: var(--accent-primary); }}
    </style>
</head>
<body>
    <header>
        <h1 class="header-title">S.S.T 処理後総合調査・改善報告書</h1>
        <div class="header-subtitle">対象件数: {len(all_items)}件 | 自動分析・調査モジュール出力</div>
    </header>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">総処理アルバム数</div>
            <div class="kpi-value">{len(all_items)}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Archive 判定</div>
            <div class="kpi-value archive">{len(archives)} <span style="font-size: 1rem; color: var(--text-secondary);">({len(archives)/max(len(all_items),1)*100:.1f}%)</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Review 判定</div>
            <div class="kpi-value review">{len(reviews)} <span style="font-size: 1rem; color: var(--text-secondary);">({len(reviews)/max(len(all_items),1)*100:.1f}%)</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">次回 Archive 予測目標</div>
            <div class="kpi-value target">85%+</div>
        </div>
    </div>

    <!-- Section 1 -->
    <section>
        <h2 class="section-title archive-title">1. 総合的に不自然な Archive 送りのケースと判断理由</h2>
        <p>自動判定で <code>Archive</code> とされたものの、メタデータ品質・美観の観点からクリーンアップ不足や不自然さが残るケースを自動検出しました。</p>

        <h3 class="card-subhead">検出された不自然な Archive 事例 ({len(unnatural_archives)}件)</h3>
        <div class="highlight-box warning">
            <ul>
"""
    for ua in unnatural_archives[:10]:
        html_content += f"<li><code>AppID {ua['app_id']}</code> ({html.escape(ua['name'])}): {', '.join(ua['issues'])}</li>\n"

    html_content += f"""
            </ul>
        </div>
        <p><strong>判断理由:</strong> <code>&amp;amp;</code> などのHTML特殊文字の残留や、Developer/Publisher名の安易な重複結合（例: <code>CAPCOM CO., LTD., CAPCOM CO., LTD.</code>）が含まれており、メタデータの正しさ・視認性を低下させています。</p>
    </section>

    <!-- Section 2 -->
    <section>
        <h2 class="section-title review-title">2. 総合的に不自然な Review 送りのケースと判断理由</h2>
        <p>過剰に保守的なハードコード閾値やストレージI/Oエラー等により、本来 Archive 判定されるべきデータが Review 送りになっている構造的問題の分類です。</p>

        <h3 class="card-subhead">原因1: ハードコード閾値 <code>if conf &lt; 100: return {{}}</code> による早期 Review 送り ({len(unnatural_reviews_conf)}件)</h3>
        <div class="highlight-box danger">
            <p>LLMが Confidence 90%〜98% と高い確信度を返しても、100%未満を理由に Phase 2 を実行せず即座に早期離脱 (<code>early_review</code>) するロジックが原因です。メッセージが空 (<code>None</code>) になるため `Unknown Review Reason` としてカウントされます。</p>
        </div>

        <h3 class="card-subhead">原因2: SMB/CIFS ネットワークマウント I/Oエラーによる <code>Audio Source Error</code> 誤判定 ({len(unnatural_reviews_io)}件)</h3>
        <div class="highlight-box danger">
            <p>LLMの判定は100%完全一致であったにも関わらず、ファイルコピー (<code>shutil.copy2</code>) 実行時に <code>[Errno 112] Host is down</code> 等のI/Oエラーが発生し、バリデータが <code>CRITICAL: Audio Source Error</code> として誤降格させたケースです。</p>
        </div>

        <h3 class="card-subhead">原因3: 軽微な構造問題（Track#0 / ディスク重複）による過剰降格 ({len(unnatural_reviews_minor)}件)</h3>
        <p>タグの Track#0 や複数ディスク間の重複検出などの軽微な表記揺れにより降格したケースです。</p>
    </section>

    <!-- Section 3 -->
    <section>
        <h2 class="section-title action-title">3. 整備されたメタデータの正しさを高めながら、次回のArchive送りを増加させる方法</h2>
        <div class="highlight-box success">
            <strong>具体的な改修ロードマップ:</strong>
            <ol style="margin-left: 1.25rem; color: var(--text-secondary);">
                <li><strong><code>conf &lt; 100</code> 早期離脱の撤廃と動的閾値化 (Archive +25〜30件見込み)</strong>: <code>conf &gt;= 85</code> で Phase 2 への遷移を許可し、<code>Confidence &gt;= 90%</code> かつ <code>Quality &gt;= 85%</code> で Archive 送りを許可する。</li>
                <li><strong>I/Oエラーに対する自動リトライ（指数バックオフ）の実装 (Archive +15〜19件見込み)</strong>: ネットワークドライブ一時切断時に最大3回のリトライ処理を挿入。</li>
                <li><strong><code>html.unescape()</code> の全自動適用</strong>: タイトル・アルバム・アーティスト名のタグ書き込み前に特殊文字をデコード。</li>
                <li><strong>AlbumArtist / Genre のインテリジェント正規化</strong>: Developer/Publisher の二重重複の自動排除と、ゲームカテゴリタグの音楽ジャンル化。</li>
                <li><strong>Track#0 および 二重プレフィックスの自動クリーンアップ</strong>: 1ベースへの自動補正とタイトル冒頭トラック番号の除去。</li>
            </ol>
        </div>
    </section>

    <!-- Section 4: Table -->
    <section>
        <h2 class="section-title">全件処理結果一覧</h2>
        <div class="filter-bar">
            <input type="text" id="searchInput" class="search-input" placeholder="検索...">
            <button class="filter-btn active" onclick="filterTable('all')">すべて ({len(all_items)})</button>
            <button class="filter-btn" onclick="filterTable('archive')">Archive ({len(archives)})</button>
            <button class="filter-btn" onclick="filterTable('review')">Review ({len(reviews)})</button>
        </div>

        <div class="table-container" style="max-height: 500px; overflow-y: auto;">
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
        s_class = item['status']
        b_html = f'<span class="badge {s_class}">{item["status"].upper()}</span>'
        html_content += f"""
                    <tr class="item-row" data-status="{s_class}">
                        <td><code>{item['app_id']}</code></td>
                        <td>{html.escape(item['name'])}</td>
                        <td>{b_html}</td>
                        <td>{item['conf']}%</td>
                        <td>{item['qual']}%</td>
                        <td><code>{item['strategy']}</code></td>
                        <td style="font-size: 0.82rem; color: var(--text-secondary);">
                            <strong>{html.escape(str(item['msg']))}</strong><br>
                            <span>{html.escape(str(item['reason']))[:100]}</span>
                        </td>
                    </tr>
"""

    html_content += """
                </tbody>
            </table>
        </div>
    </section>

    <script>
        function filterTable(status) {
            const rows = document.querySelectorAll('.item-row');
            const btns = document.querySelectorAll('.filter-btn');
            btns.forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            rows.forEach(r => {
                r.style.display = (status === 'all' || r.getAttribute('data-status') === status) ? '' : 'none';
            });
        }
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const term = e.target.value.toLowerCase();
            document.querySelectorAll('.item-row').forEach(r => {
                r.style.display = r.innerText.toLowerCase().includes(term) ? '' : 'none';
            });
        });
    </script>
</body>
</html>
"""

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"[OK] 調査レポートを生成しました: {report_file.resolve()}")

if __name__ == '__main__':
    analyze_and_generate_report()
