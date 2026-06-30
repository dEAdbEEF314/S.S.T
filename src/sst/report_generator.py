import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from .models import SteamMetadata

logger = logging.getLogger("sst.report_generator")

class ReportGenerator:
    @staticmethod
    def _get_common_css() -> str:
        return """
:root {
    --bg-color: #0d1117;
    --card-bg: #161b22;
    --text-color: #c9d1d9;
    --accent-green: #238636;
    --accent-yellow: #d29922;
    --accent-blue: #58a6ff;
    --border-color: #30363d;
    --table-header: #0d1117;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background-color: var(--bg-color);
    color: var(--text-color);
    line-height: 1.6;
    margin: 0;
    padding: 20px;
}
.container { max-width: 1000px; margin: 0 auto; }
.header { border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-bottom: 20px; }
.status-badge {
    display: inline-block;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: bold;
    margin-bottom: 10px;
    text-transform: uppercase;
}
.status-archive { background-color: var(--accent-green); color: white; }
.status-review { background-color: var(--accent-yellow); color: black; }
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 20px;
    margin-bottom: 20px;
}
.card {
    background-color: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 15px;
}
.card h3 { margin-top: 0; font-size: 0.9rem; color: #8b949e; text-transform: uppercase; }
.reason-box {
    background-color: #090c10;
    border-left: 4px solid var(--border-color);
    padding: 15px;
    margin: 20px 0;
    font-style: italic;
    white-space: pre-wrap;
}
.mbz-card {
    border-bottom: 1px solid var(--border-color);
    padding: 10px 0;
}
.mbz-card:last-child { border-bottom: none; }
.badge { font-size: 0.8rem; background: #21262d; padding: 2px 6px; border-radius: 10px; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85rem; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-color); }
th { background-color: var(--table-header); color: #8b949e; font-weight: 600; }
.tag-table tr:hover { background-color: #1c2128; }
a { color: var(--accent-blue); text-decoration: none; }
a:hover { text-decoration: underline; }
footer { margin-top: 40px; font-size: 0.8rem; color: #8b949e; text-align: center; border-top: 1px solid var(--border-color); padding-top: 20px; }
"""

    @staticmethod
    def generate_html_report(app_id: int, steam_meta: SteamMetadata, status: str, message: str, score: int, reason: str, processed_tracks: List[Dict[str, Any]], llm_log: Dict[str, Any], mbz_candidates: List[Dict[str, Any]], localized_now_str: str, priority_str: str, quality: Optional[int] = None) -> str:
        is_fast = llm_log.get("fast_track", False)
        status_class = "status-archive" if status == "archive" else "status-review"
        status_label = "🛡️ ARCHIVE SUCCESS" if status == "archive" else "🔍 REVIEW REQUIRED"
        count = len(processed_tracks)
        
        display_reason = reason
        if is_fast:
            display_reason = "<strong>🛡️ DETERMINISTIC FAST-TRACK ENABLED</strong><br><br>This album was automatically verified by matching perfect evidence from MusicBrainz or PICS. LLM inference was bypassed to maintain 100% data integrity."

        p1_res = llm_log.get("phase1_res", {})
        if quality is None:
            quality = int(p1_res.get("integrity_quality", 0))
        global_tags = p1_res.get("global_tags", {})
        chosen_idx = global_tags.get("chosen_mbz_index")
        chosen_id = global_tags.get("chosen_mbz_id")
        mbz_choice_reason = global_tags.get("mbz_choice_reason")

        mbz_html = ""
        if mbz_candidates:
            for i, c in enumerate(mbz_candidates[:5]):
                is_chosen = (i == chosen_idx) or (c.get('mbid') == chosen_id)
                chosen_badge = ' <span class="badge" style="background:#238636;">⭐ CHOSEN</span>' if is_chosen else ''
                card_style = ' style="border: 2px solid var(--accent-green); background: #1a2332; padding: 10px; border-radius: 6px; margin-bottom: 5px;"' if is_chosen else ''
                mbz_html += f"""<div class="mbz-card"{card_style}><strong>{c.get('album')}</strong> <span class="badge">Score: {c.get('score')}</span>{chosen_badge}<br><code style="font-size: 0.85rem; color: var(--accent-yellow);">{c.get('mbid')}</code><br><a href="https://musicbrainz.org/release/{c.get('mbid')}" target="_blank">View on MusicBrainz ↗</a></div>"""
            if mbz_choice_reason: mbz_html += f'<div class="reason-box" style="margin-top:10px;"><strong>LLM MBZ Choice Reason:</strong><br>{mbz_choice_reason}</div>'
        else: mbz_html = "<p>No matching MusicBrainz candidates found.</p>"

        matrix_rows = ""
        priority_list = [p.strip().upper() for p in priority_str.split(',')]
        for source in priority_list:
            if source == "STEAM_PICS": matrix_rows += f"<tr><td>{source}</td><td>{steam_meta.name}</td><td>{steam_meta.developer or 'N/A'}</td><td>N/A</td><td>N/A</td></tr>"
            elif source == "STEAM_STORE":
                store_track_count = len(steam_meta.store_tracklist) if steam_meta.store_tracklist else 0
                matrix_rows += f"<tr><td>{source}</td><td>{steam_meta.name}</td><td>{steam_meta.developer or 'N/A'}</td><td>{store_track_count}</td><td>{steam_meta.release_date or 'N/A'}</td></tr>"
            elif source == "MBZ":
                if not mbz_candidates: matrix_rows += f"<tr><td>{source}</td><td>N/A</td><td>N/A</td><td>N/A</td><td>N/A</td></tr>"
                else:
                    for i, c in enumerate(mbz_candidates[:5]):
                        is_chosen = (i == chosen_idx) or (c.get('mbid') == chosen_id)
                        row_style = ' style="background-color: #1a2332; font-weight: bold; border-left: 4px solid var(--accent-green);"' if is_chosen else ''
                        matrix_rows += f"<tr{row_style}><td>{source} (Candidate {i} - Score: {c.get('score')})</td><td>{c.get('album')}</td><td>{c.get('artist')}</td><td>{c.get('track_count')}</td><td>{c.get('year')}</td></tr>"
            elif source in ["STEAM_TAGS", "EMBEDDED"]: matrix_rows += f"<tr><td>{source}</td><td>(Per-track data)</td><td>N/A</td><td>N/A</td><td>N/A</td></tr>"
            
        # --- Detailed Tag Table ---
        def safe_sort_key(t):
            tags = t.get("tags", {})
            try:
                d = int(tags.get("disc_number") or 1)
                n = int(tags.get("track_number") or 0)
                return (d, n)
            except: return (99, 99)

        sorted_tracks = sorted(processed_tracks, key=safe_sort_key)
        tag_rows = ""
        for t in sorted_tracks:
            tg = t.get("tags", {})
            tag_rows += f"""<tr>
                <td>{tg.get('disc_number', '1')}</td>
                <td>{tg.get('track_number', '')}</td>
                <td><strong>{tg.get('title', 'Unknown')}</strong></td>
                <td>{tg.get('artist', '')}</td>
                <td>{tg.get('album_artist', '')}</td>
                <td>{tg.get('genre', '')}</td>
                <td>{tg.get('year', '')}</td>
                <td style="font-weight: 500; color: var(--accent-blue);">{t.get('title_source', 'UNKNOWN')}</td>
                <td style="font-size: 0.75rem; color: #8b949e;">{t.get('source', '')}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SST Audit Report - {steam_meta.name}</title>
    <style>{ReportGenerator._get_common_css()}</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>SST Audit Report</h1>
        <p>AppID: <a href="https://store.steampowered.com/app/{app_id}" target="_blank">{app_id}</a> | Album: <strong>{steam_meta.name}</strong></p>
    </div>

    <div class="status-badge {status_class}">{status_label}</div>

    <div class="grid">
        <div class="card">
            <h3>Decision Summary</h3>
            <p><strong>Status:</strong> {status.upper()}<br>
            <strong>Score:</strong> {score}/100<br>
            <strong>Message:</strong> {message}<br>
            <strong>Tracks:</strong> {count}</p>
        </div>
        <div class="card">
            <h3>LLM Metrics</h3>
            <p><strong>Identity Confidence:</strong> {p1_res.get('identity_confidence', 'N/A')}%<br>
            <strong>Integrity Quality:</strong> {quality}%<br>
            <strong>Decision Ratio:</strong> Arch {p1_res.get('archive_vs_review_ratio', {}).get('archive', 0)}% : Rev {p1_res.get('archive_vs_review_ratio', {}).get('review', 0)}%</p>
        </div>
    </div>

    <div class="card">
        <h3>Judgment Reasoning & Strategy</h3>
        <div class="reason-box">{display_reason}</div>
        
        <div style="margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 15px; font-size: 0.85rem; color: #8b949e;">
            <strong style="color: var(--accent-yellow);">⚙️ System Merge Note:</strong><br>
            本システムは、LLMが選択した MusicBrainz (MBZ) のリリースデータをベースに動作しますが、元のリリース曲順がローカルファイルと異なる場合は、**再生時間（Duration）に基づき物理的に自動整列（Duration Alignment）**した上でマッピングを行っています。<br>
            また、最終的なタグの値は `.env` の優先度（`METADATA_SOURCE_PRIORITY`）に基づいて、項目ごとに最適なソース（MBZやSteamなど）から動的にブレンドおよびフォールバックされます。そのため、MBZが選ばれた場合でも、データ不存在や優先度に応じてSteam等の情報が一部適用されることがあります。
        </div>
    </div>

    <div class="grid" style="margin-top: 20px;">
        <div class="card">
            <h3>Source Alignment Matrix</h3>
            <table>
                <thead><tr><th>Source</th><th>Title</th><th>Artist/Dev</th><th>Tracks</th><th>Year</th></tr></thead>
                <tbody>{matrix_rows}</tbody>
            </table>
        </div>
        <div class="card">
            <h3>MusicBrainz Candidates</h3>
            {mbz_html}
        </div>
    </div>

    <div class="card" style="margin-top: 20px;">
        <h3>Final Applied Tags (Tracklist)</h3>
        <table class="tag-table">
            <thead>
                <tr>
                    <th>Disc</th>
                    <th>#</th>
                    <th>Title</th>
                    <th>Artist</th>
                    <th>Album Artist</th>
                    <th>Genre</th>
                    <th>Year</th>
                    <th>Title Source</th>
                    <th>Source</th>
                </tr>
            </thead>
            <tbody>{tag_rows}</tbody>
        </table>
    </div>

    <footer>
        <p>Generated by S.S.T (Steam Soundtrack Tagger) at {localized_now_str}</p>
    </footer>
</div>
</body>
</html>"""

    @staticmethod
    def generate_classification_basis(app_id: int, steam_meta: SteamMetadata, status: str, message: str, score: int, reason: str, count: int, llm_log: Dict[str, Any], mbz_candidates: List[Dict[str, Any]], localized_now_str: str) -> str:
        p1_res = llm_log.get("phase1_res", {})
        id_conf = p1_res.get("identity_confidence", 0)
        quality = p1_res.get("integrity_quality", 0)
        ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
        is_fast = llm_log.get("fast_track", False)
        
        def md_escape(text):
            if text is None: return "-"
            return str(text).replace("|", "\\|").replace("\n", "<br>")

        def md_blockquote(text):
            if not text: return "> -"
            lines = str(text).strip().split("\n")
            return "\n".join([f"> {line}" for line in lines])

        status_emoji = "🛡️ ARCHIVE" if status == "archive" else "🔍 REVIEW REQUIRED"
        candidate_md = ""
        if mbz_candidates:
            for c in mbz_candidates[:5]: candidate_md += f"- **{md_escape(c.get('album'))}** (Score: {c.get('score')})\n  - {c.get('mbid_url')}\n"
        else: candidate_md = "- No matching MusicBrainz candidates found."

        action_required = ""
        if status == "review":
            action_required = f"## 🛠️ Action Required\n- [ ] Open the output ZIP file and inspect the tags.\n- [ ] Use MP3tag to verify track titles and artists against the [Steam Store](https://store.steampowered.com/app/{app_id}).\n"

        display_reason = reason
        if is_fast:
            display_reason = "🛡️ **DETERMINISTIC FAST-TRACK ENABLED**\n\nThis album was automatically verified by matching perfect evidence (e.g., Direct Steam links, exact track count, and title alignment) from MusicBrainz or PICS. \n\n**LLM inference was bypassed** to maintain 100% data integrity and save tokens."

        return f"# {status_emoji} Archive Audit Report: {steam_meta.name}\n\n## 📊 Quick Summary\n- **AppID**: {app_id}\n- **Status**: **{status.upper()}**\n- **Confidence Gates**:\n  - Identity Confidence: `{id_conf}/100` (Req: 100 for Archive)\n  - Integrity Quality: `{quality}/100` (Req: 95 for Archive)\n- **Judgment Ratio**: Archive `{ratio.get('archive', 0)}%` / Review `{ratio.get('review', 0)}%`\n- **System Decision Reason**: {md_escape(message)}\n- **Tracks Processed**: {count}\n{action_required}\n## 🔍 LLM Reasoning & Strategy\n{md_blockquote(display_reason)}\n\n## 🔗 External References\n- **Steam Store**: https://store.steampowered.com/app/{app_id}\n- **Parent Game**: {md_escape(steam_meta.parent_name) or 'N/A'} (AppID: {steam_meta.parent_app_id or 'N/A'})\n\n## 🎼 MusicBrainz Candidates (Top 5)\n{candidate_md}\n\n---\n*Report generated by S.S.T (Steam Soundtrack Tagger) at {localized_now_str}*\n"

    @staticmethod
    def generate_batch_report(results: List[Any], output_path: Path):
        """Generates a summary HTML report (Result.html) for a batch of results."""
        archive_count = sum(1 for r in results if r.status == "archive")
        review_count = sum(1 for r in results if r.status == "review")
        error_count = sum(1 for r in results if r.status == "error")
        skip_count = sum(1 for r in results if r.status == "skip")

        html = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <title>S.S.T Batch Processing Report</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #cdd6f4; max-width: 1400px; margin: 0 auto; padding: 20px; background-color: #1e1e2e; }}
                h1 {{ color: #cdd6f4; border-bottom: 2px solid #cdd6f4; padding-bottom: 10px; }}
                .summary {{ background: #313244; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.5); }}
                .summary-item {{ font-size: 1.2em; font-weight: bold; }}
                .archive {{ color: #a6e3a1; }}
                .review {{ color: #f9e2af; }}
                .error {{ color: #f38ba8; }}
                table {{ width: 100%; border-collapse: collapse; background: #313244; box-shadow: 0 2px 4px rgba(0,0,0,0.5); border-radius: 8px; overflow: hidden; }}
                th {{ background-color: #45475a; color: #cdd6f4; text-align: left; padding: 12px; font-size: 0.9em; }}
                td {{ padding: 12px; border-bottom: 1px solid #45475a; vertical-align: top; font-size: 0.85em; }}
                tr:hover {{ background-color: #585b70; }}
                .status-archive {{ color: #a6e3a1; font-weight: bold; }}
                .status-review {{ color: #f9e2af; font-weight: bold; }}
                .status-error {{ color: #f38ba8; font-weight: bold; }}
                .reason-box {{ white-space: pre-wrap; word-break: break-all; }}
                .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-right: 5px; color: #fff; margin-bottom: 5px; }}
                .badge-acoustid {{ background-color: #3498db; }}
                .badge-fallback {{ background-color: #9b59b6; }}
                .badge-mbz {{ background-color: #2ecc71; }}
                .badge-trust {{ background-color: #f1c40f; color: #333; }}
                .badge-duplicate {{ background-color: #e74c3c; }}
            </style>
        </head>
        <body>
            <h1>🚀 S.S.T Batch Processing Report</h1>
            <div class="summary">
                <div class="summary-item">Total: {len(results)}</div>
                <div class="summary-item archive">Archive: {archive_count}</div>
                <div class="summary-item review">Review: {review_count}</div>
                <div class="summary-item">Skip: {skip_count}</div>
                <div class="summary-item error">Error: {error_count}</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th style="width: 80px;">AppID</th>
                        <th style="width: 250px;">Album Name</th>
                        <th style="width: 80px;">Status</th>
                        <th style="width: 50px;">Score</th>
                        <th style="width: 350px;">System Reason</th>
                        <th>LLM Confidence Reason</th>
                    </tr>
                </thead>
                <tbody>
        """

        for r in results:
            status_class = f"status-{r.status}"
            score = r.confidence_score if r.confidence_score is not None else "-"
            
            # Badge generation from message keywords
            badges = []
            m_lower = r.message.lower()
            if "acoustid" in m_lower: badges.append('<span class="badge badge-acoustid">AcoustID</span>')
            if "fallback" in m_lower: badges.append('<span class="badge badge-fallback">Fallback</span>')
            if "mbz" in m_lower: badges.append('<span class="badge badge-mbz">MBZ Match</span>')
            if "trust" in m_lower: badges.append('<span class="badge badge-trust">Trust Tier</span>')
            if "duplicate titles" in m_lower: badges.append('<span class="badge badge-duplicate">Duplicate Titles</span>')
            
            badge_str = "".join(badges)
            
            html += f"""
                    <tr>
                        <td>{r.app_id}</td>
                        <td>{r.album_name}</td>
                        <td class="{status_class}">{r.status.upper()}</td>
                        <td>{score}</td>
                        <td class="reason-box">{badge_str}<br>{r.message}</td>
                        <td class="reason-box">{r.confidence_reason}</td>
                    </tr>
            """

        html += """
                </tbody>
            </table>
            <footer style="margin-top: 20px; font-size: 0.8em; color: #888; text-align: center;">
                Generated by S.S.T (Steam Soundtrack Tagger)
            </footer>
        </body>
        </html>
        """
        
        output_path.write_text(html, encoding="utf-8")
