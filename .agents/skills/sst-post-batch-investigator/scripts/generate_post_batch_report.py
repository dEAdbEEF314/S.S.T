import sqlite3
import json
import html
import re
import glob
from pathlib import Path

def _track_key(track):
    tags = track.get('tags', {})
    disc = str(tags.get('disc_number', '1')).split('/')[0]
    number = str(tags.get('track_number', '0')).split('/')[0]
    return disc, number


def _integrity_snapshot(meta, tracks):
    expected_slots = []
    steam_info = meta.get('steam_info') or {}
    for slot in steam_info.get('store_tracklist') or []:
        expected_slots.append((str(slot.get('disc', 1)), str(slot.get('number', '0'))))

    track_keys = [_track_key(track) for track in tracks]
    slot_keys = [str(track.get('slot_key', '')) for track in tracks]
    format_counts = {}
    for track in tracks:
        suffix = Path(str(track.get('file_path', ''))).suffix.lower() or 'unknown'
        format_counts[suffix] = format_counts.get(suffix, 0) + 1

    return {
        'expected_slot_count': len(expected_slots),
        'track_keys': track_keys,
        'duplicate_key_count': len(track_keys) - len(set(track_keys)),
        'missing_slots': sorted(set(expected_slots) - set(track_keys)),
        'unexpected_slots': sorted(set(track_keys) - set(expected_slots)) if expected_slots else [],
        'slot_key_count': len(set(slot_keys)),
        'duplicate_slot_key_count': len(slot_keys) - len(set(slot_keys)),
        'format_counts': format_counts,
        'fallback_count': sum(track.get('source') == 'Fallback' for track in tracks),
        'local_title_count': sum(track.get('title_source') == 'LOCAL' for track in tracks),
        'track_zero_count': sum(str(track.get('tags', {}).get('track_number')) == '0' for track in tracks),
        'unknown_title_count': sum((track.get('tags', {}).get('title') or 'Unknown') == 'Unknown' for track in tracks),
    }


def analyze_and_generate_report(db_path='data/sst_local_state.db', output_dir='report'):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT app_id, album_name, status, metadata_json
        FROM processed_albums
        WHERE rowid IN (SELECT MAX(rowid) FROM processed_albums GROUP BY app_id)
        ORDER BY CAST(app_id AS INTEGER)
    ''')
    rows = cursor.fetchall()

    archives = []
    reviews = []
    all_items = []

    unnatural_archives = []
    reviews_unassigned = []
    reviews_audio = []
    reviews_slot_mismatch = []
    reviews_low_conf = []
    reviews_early = []
    reviews_io = []

    fast_track_count = 0
    steam_trust_count = 0

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
        integrity = _integrity_snapshot(meta, tracks)
        conf = meta.get('confidence_score', 0)
        qual = meta.get('integrity_quality', 0)
        msg = meta.get('message') or 'N/A (Early Review)'
        reason = meta.get('confidence_reason') or 'No reason captured'
        strategy = meta.get('strategy') or 'N/A'

        if strategy == 'FAST_TRACK' or 'Deterministic Fast-Track' in str(msg) or 'Deterministic fast-track' in str(reason):
            fast_track_count += 1
        elif 'STEAM-TRUST' in str(msg) or 'STEAM-TRUST' in str(reason):
            steam_trust_count += 1

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
            'unassigned_count': len(meta.get('unassigned_files', [])),
            'integrity': integrity,
            'meta': meta
        }
        all_items.append(item)

        if status == 'archive':
            archives.append(item)
            # Scan for unnatural archive issues
            issues = []
            html_entities = []

            for t in tracks:
                tags = t.get('tags', {})
                title = str(tags.get('title', ''))

                if any(e in title for e in ['&amp;', '&quot;', '&#39;', '&lt;', '&gt;']):
                    html_entities.append(title)

            if html_entities:
                issues.append(f"HTMLエンティティ未デコード ({len(html_entities)}トラック): 例 \"{html_entities[0]}\"")
            if integrity['duplicate_key_count']:
                issues.append(f"最終Disc/Track重複 ({integrity['duplicate_key_count']})")
            if integrity['duplicate_slot_key_count']:
                issues.append(f"最終slot_key重複 ({integrity['duplicate_slot_key_count']})")
            if integrity['expected_slot_count'] and len(tracks) != integrity['expected_slot_count']:
                issues.append(f"Steam slot数不一致 ({len(tracks)}/{integrity['expected_slot_count']})")
            if integrity['fallback_count'] or integrity['local_title_count']:
                issues.append(f"Fallback/LOCAL残留 ({integrity['fallback_count']}/{integrity['local_title_count']})")

            if issues:
                unnatural_archives.append({
                    'app_id': app_id,
                    'name': name,
                    'issues': issues
                })

        else:
            reviews.append(item)
            app_id_int = int(app_id) if str(app_id).isdigit() else app_id

            if app_id_int in io_error_app_ids or 'CRITICAL: Audio Source Error' in msg:
                reviews_io.append(item)
            elif 'Audio quality warning' in msg or 'conversion_warning' in str(meta):
                reviews_audio.append(item)
            elif item['unassigned_count'] > 0:
                reviews_unassigned.append(item)
            elif any(token in msg for token in ['Slots Missing', 'Slots Unexpected', 'Track Count Mismatch', 'Duplicates']):
                reviews_slot_mismatch.append(item)
            elif msg == 'N/A (Early Review)' or 'No LLM response' in reason or 'EARLY_REVIEW' in str(meta.get('diagnostics', {})):
                reviews_early.append(item)
            else:
                reviews_low_conf.append(item)

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
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
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
        .kpi-value {{ font-size: 2rem; font-weight: 700; }}
        .kpi-value.archive {{ color: var(--color-archive); }}
        .kpi-value.review {{ color: var(--color-review); }}
        .kpi-value.target {{ color: var(--accent-light); }}
        .kpi-value.info {{ color: var(--color-info); }}
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
        .highlight-box.info {{ border-left: 4px solid var(--color-info); }}
        .table-container {{ overflow-x: auto; margin-top: 1rem; border-radius: 0.5rem; border: 1px solid var(--border-color); }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left; }}
        th {{ background-color: #0f172a; color: var(--text-secondary); font-weight: 600; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); }}
        td {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); }}
        tr:hover {{ background-color: var(--bg-card-hover); }}
        .badge {{ display: inline-block; padding: 0.2rem 0.55rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
        .badge.archive {{ background-color: var(--color-archive-bg); color: var(--color-archive); border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge.review {{ background-color: var(--color-review-bg); color: var(--color-review); border: 1px solid rgba(245, 158, 11, 0.3); }}
        .filter-bar {{ display: flex; gap: 1rem; margin-bottom: 1rem; align-items: center; flex-wrap: wrap; }}
        .search-input {{ background-color: #0f172a; border: 1px solid var(--border-color); color: var(--text-primary); padding: 0.5rem 1rem; border-radius: 0.375rem; flex: 1; min-width: 200px; }}
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
            <div class="kpi-label">Fast-Track 発動数</div>
            <div class="kpi-value info">{fast_track_count} <span style="font-size: 0.9rem; color: var(--text-secondary);">({fast_track_count/max(len(all_items),1)*100:.1f}%)</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Archive 判定</div>
            <div class="kpi-value archive">{len(archives)} <span style="font-size: 0.9rem; color: var(--text-secondary);">({len(archives)/max(len(all_items),1)*100:.1f}%)</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Review 判定</div>
            <div class="kpi-value review">{len(reviews)} <span style="font-size: 0.9rem; color: var(--text-secondary);">({len(reviews)/max(len(all_items),1)*100:.1f}%)</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">不自然なArchive</div>
            <div class="kpi-value {'archive' if len(unnatural_archives)==0 else 'review'}">{len(unnatural_archives)}件</div>
        </div>
    </div>

    <!-- Section 1 -->
    <section>
        <h2 class="section-title archive-title">1. 総合的に不自然な Archive 送りのケースと判断理由</h2>
        <p>自動判定で <code>Archive</code> とされたものの、メタデータ品質・美観の観点からクリーンアップ不足や不自然さが残るケースを自動検出しました。</p>

        <h3 class="card-subhead">検出された不自然な Archive 事例 ({len(unnatural_archives)}件)</h3>
        <div class="highlight-box {'success' if len(unnatural_archives)==0 else 'warning'}">
            {'<p style="color: var(--color-archive); margin:0;">✓ 不自然な Archive 事例は検出されませんでした（全件 Steam スロット 1:1 準拠）。</p>' if not unnatural_archives else '<ul>' + ''.join(f"<li><code>AppID {ua['app_id']}</code> ({html.escape(ua['name'])}): {', '.join(ua['issues'])}</li>" for ua in unnatural_archives[:10]) + '</ul>'}
        </div>
        <p><strong>判断基準:</strong> <code>&amp;amp;</code> などのHTML特殊文字の残留、Steam slotと最終トラックの不一致、最終キーの重複など、出力の整合性を低下させる事象を対象にしています。DeveloperとPublisherが同一社名の場合の <code>AlbumArtist</code> 重複は仕様通り保持します。</p>
    </section>

    <!-- Section 2 -->
    <section>
        <h2 class="section-title review-title">2. Review 送りの要因別分類と精査</h2>
        <p>Validatorのメッセージ、最終タグ、Steam slot、物理出力、LLM割当、ログを突合し、Reviewの原因を要因別に分類しました。</p>

        <h3 class="card-subhead">要因1: 未割当ファイル（Steamスロット外の余剰ファイル）の存在 ({len(reviews_unassigned)}件)</h3>
        <div class="highlight-box info">
            <p>Steamトラックリストに存在しないボーナストラック・未収録ファイルがローカルに存在するため、安全弁（Review隔離）が正常に働いたケースです。</p>
            <ul>
                {''.join(f"<li><code>AppID {r['app_id']}</code>: {html.escape(r['name'])} (未割当: {r['unassigned_count']}ファイル)</li>" for r in reviews_unassigned[:5])}
            </ul>
        </div>

        <h3 class="card-subhead">要因2: 音声物理破損 / デコード警告 ({len(reviews_audio)}件)</h3>
        <div class="highlight-box danger">
            <p>ローカルの音声ファイルが物理的に破損（FLACデコードエラー等）しており、FFmpeg変換警告を検知して正しく Review 隔離されたケースです。</p>
            <ul>
                {''.join(f"<li><code>AppID {r['app_id']}</code>: {html.escape(r['name'])} (Msg: {html.escape(str(r['msg']))})</li>" for r in reviews_audio)}
            </ul>
        </div>

        <h3 class="card-subhead">要因3: Steam構造・スロット不整合 ({len(reviews_slot_mismatch)}件)</h3>
        <div class="highlight-box warning">
            <p>Steamスロットとローカルファイルの間でトラック番号の食い違いや欠落が発生したケースです（単曲アルバム判定誤りによる不当Reviewを含む）。</p>
            <ul>
                {''.join(f"<li><code>AppID {r['app_id']}</code>: {html.escape(r['name'])} (Msg: {html.escape(str(r['msg']))})</li>" for r in reviews_slot_mismatch[:5])}
            </ul>
        </div>

        <h3 class="card-subhead">要因4: 早期レビュー / トラックリスト不在 ({len(reviews_early)}件)</h3>
        <div class="highlight-box warning">
            <p>Steam上にトラックリストが存在しないボーナスコンテンツや、事前判定ゲートにより早期Reviewとなったケースです。</p>
            <ul>
                {''.join(f"<li><code>AppID {r['app_id']}</code>: {html.escape(r['name'])} (Msg: {html.escape(str(r['msg']))})</li>" for r in reviews_early)}
            </ul>
        </div>

        <h3 class="card-subhead">要因5: 信頼度不足・LLM判断不確実 ({len(reviews_low_conf)}件)</h3>
        <div class="highlight-box warning">
            <p>LLM確信度が基準値（90%）を下回るか、ローカル重複によりマッピングに不確実性が残ったケースです。</p>
            <ul>
                {''.join(f"<li><code>AppID {r['app_id']}</code>: {html.escape(r['name'])} (Conf: {r['conf']}%, Msg: {html.escape(str(r['msg']))})</li>" for r in reviews_low_conf)}
            </ul>
        </div>
    </section>

    <!-- Section 3 -->
    <section>
        <h2 class="section-title action-title">3. 証拠に基づく改善候補</h2>
        <div class="highlight-box success">
            <strong>具体的な改修ロードマップ:</strong>
            <ol style="margin-left: 1.25rem; color: var(--text-secondary);">
                <li><strong>slot identityの回帰テスト</strong>: 物理候補、<code>track_groups</code>、<code>slot_variant_index</code>、<code>adopted_files</code>、最終metadataの件数を固定する。</li>
                <li><strong>LLM割当の矛盾検出</strong>: 未割当、1ファイルの多重割当、無関係な曲の同一slot割当を自動的にReviewへ分類する。</li>
                <li><strong>物理I/Oの再試行</strong>: 実ログで確認できたコピー・変換失敗に限定してリトライと構造化診断を追加する。</li>
                <li><strong>HTML/テキストソースの監査</strong>: 実際に残留したエンティティやLLM抽出ソースだけを対象に正規化を検討する。</li>
                <li><strong>結果の再検証</strong>: 修正後は同一AppIDまたは合成fixtureを再実行し、Steam slot数、重複0、Fallback0を確認する。</li>
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
