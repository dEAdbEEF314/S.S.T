import logging
from typing import Dict, Any, List
from .models import SteamMetadata

logger = logging.getLogger("scout.report_generator")

class ReportGenerator:
    @staticmethod
    def generate_html_report(app_id: int, steam_meta: SteamMetadata, status: str, message: str, score: int, reason: str, count: int, llm_log: Dict[str, Any], mbz_candidates: List[Dict[str, Any]], localized_now_str: str, priority_str: str) -> str:
        is_fast = llm_log.get("fast_track", False)
        status_class = "status-archive" if status == "archive" else "status-review"
        status_label = "🛡️ ARCHIVE SUCCESS" if status == "archive" else "🔍 REVIEW REQUIRED"
        
        display_reason = reason
        if is_fast:
            display_reason = "<strong>🛡️ DETERMINISTIC FAST-TRACK ENABLED</strong><br><br>This album was automatically verified by matching perfect evidence from MusicBrainz or PICS. LLM inference was bypassed to maintain 100% data integrity."

        p1_res = llm_log.get("phase1_res", {})
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
            
        return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>SST Audit Report - {steam_meta.name}</title><style>:root {{--bg-color: #0d1117; --card-bg: #161b22; --text-color: #c9d1d9; --accent-green: #238636; --accent-yellow: #d29922; --border-color: #30363d;}}body {{font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; background-color: var(--bg-color); color: var(--text-color); line-height: 1.6; margin: 0; padding: 20px;}}.container {{max-width: 900px; margin: 0 auto;}}.header {{border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-bottom: 20px;}}.status-badge {{display: inline-block; padding: 8px 16px; border-radius: 6px; font-weight: bold; margin-bottom: 10px;}}.status-archive {{ background-color: var(--accent-green); color: white; }}.status-review {{ background-color: var(--accent-yellow); color: black; }}.grid {{display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px;}}.card {{background-color: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 15px;}}.card h3 {{ margin-top: 0; font-size: 0.9rem; color: #8b949e; text-transform: uppercase; }}.reason-box {{background-color: #090c10; border-left: 4px solid var(--border-color); padding: 15px; margin: 20px 0; font-style: italic;}}.mbz-card {{border-bottom: 1px solid var(--border-color); padding: 10px 0;}}.mbz-card:last-child {{ border-bottom: none; }}.badge {{font-size: 0.8rem; background: #21262d; padding: 2px 6px; border-radius: 10px;}}table {{width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.9rem;}}th, td {{padding: 8px; text-align: left; border-bottom: 1px solid var(--border-color);}}th {{ background-color: #0d1117; color: #8b949e; }}a {{ color: #58a6ff; text-decoration: none; }}a:hover {{ text-decoration: underline; }}footer {{margin-top: 40px; font-size: 0.8rem; color: #8b949e; text-align: center;}}</style></head><body><div class="container"><div class="header"><div class="status-badge {status_class}">{status_label}</div><h1>{steam_meta.name}</h1></div><div class="grid"><div class="card"><h3>Confidence Gates</h3><p>Identity: <strong>{p1_res.get('identity_confidence', 0)}%</strong><br>Integrity: <strong>{p1_res.get('integrity_quality', 0)}%</strong></p></div><div class="card"><h3>Decision Logic</h3><p>System: {message}<br>Tracks: {count}</p></div><div class="card"><h3>Steam Links</h3><p><a href="https://store.steampowered.com/app/{app_id}" target="_blank">Store Page</a><br>AppID: {app_id}</p></div></div><h2>🔍 Analysis & Reasoning</h2><div class="reason-box">{display_reason}</div><div class="card" style="margin-bottom: 20px;"><h3>Metadata Information Matrix</h3><table><tr><th>Source</th><th>Album Title</th><th>Artist</th><th>Tracks</th><th>Year</th></tr>{matrix_rows}</table></div><div class="grid"><div class="card" style="grid-column: span 2;"><h3>MusicBrainz Candidates (Provided to LLM)</h3>{mbz_html}</div><div class="card"><h3>Final Global Tags</h3><p>Artist: {global_tags.get('canonical_album_artist', 'N/A')}<br>Year: {global_tags.get('canonical_year', 'N/A')}<br>Label: {global_tags.get('canonical_label', 'N/A')}</p></div></div><footer>Report generated by S.S.T (Steam Soundtrack Tagger) at {localized_now_str}</footer></div></body></html>"""

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
            action_required = f"## 🛠️ Action Required\n- [ ] Open the output ZIP file and inspect the tags.\n- [ ] Use MP3tag to verify track titles and artists against the [Steam Store](https://store.steampowered.com/app/{app_id}).\n- [ ] If tags are incorrect, fix them and run `./sst --finalize` to update the database.\n"

        display_reason = reason
        if is_fast:
            display_reason = "🛡️ **DETERMINISTIC FAST-TRACK ENABLED**\n\nThis album was automatically verified by matching perfect evidence (e.g., Direct Steam links, exact track count, and title alignment) from MusicBrainz or PICS. \n\n**LLM inference was bypassed** to maintain 100% data integrity and save tokens."

        return f"# {status_emoji} Archive Audit Report: {steam_meta.name}\n\n## 📊 Quick Summary\n- **AppID**: {app_id}\n- **Status**: **{status.upper()}**\n- **Confidence Gates**:\n  - Identity Confidence: `{id_conf}/100` (Req: 100 for Archive)\n  - Integrity Quality: `{quality}/100` (Req: 95 for Archive)\n- **Judgment Ratio**: Archive `{ratio.get('archive', 0)}%` / Review `{ratio.get('review', 0)}%`\n- **System Decision Reason**: {md_escape(message)}\n- **Tracks Processed**: {count}\n{action_required}\n## 🔍 LLM Reasoning & Strategy\n{md_blockquote(display_reason)}\n\n## 🔗 External References\n- **Steam Store**: https://store.steampowered.com/app/{app_id}\n- **Parent Game**: {md_escape(steam_meta.parent_name) or 'N/A'} (AppID: {steam_meta.parent_app_id or 'N/A'})\n\n## 🎼 MusicBrainz Candidates (Top 5)\n{candidate_md}\n\n---\n*Report generated by S.S.T (Steam Soundtrack Tagger) at {localized_now_str}*\n"
