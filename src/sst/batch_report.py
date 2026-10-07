from pathlib import Path
from typing import Any, Callable, List


def render_batch_row(result: Any, escape: Callable[[Any], str]) -> str:
    status_raw = str(result.status if result.status else "")
    status_class = f"status-{escape(status_raw)}"
    score = escape(result.confidence_score if result.confidence_score is not None else "-")
    metadata = getattr(result, "metadata", {}) or {}
    diagnostics = metadata.get("diagnostics", {}) if isinstance(metadata, dict) else {}
    audit = metadata.get("audit", {}) if isinstance(metadata, dict) else {}
    primary_cause = escape(diagnostics.get("primary_review_cause") or "-")
    raw_secondaries = diagnostics.get("secondary_review_causes", [])
    secondary_causes = escape(", ".join(str(cause) for cause in raw_secondaries) if raw_secondaries else "-")

    badges = []
    message_lower = str(result.message or "").lower()
    if "acoustid" in message_lower:
        badges.append('<span class="badge badge-acoustid">AcoustID</span>')
    if "fallback" in message_lower:
        badges.append('<span class="badge badge-fallback">Fallback</span>')
    if "mbz" in message_lower:
        badges.append('<span class="badge badge-mbz">MBZ Match</span>')
    if "trust" in message_lower:
        badges.append('<span class="badge badge-trust">Trust Tier</span>')
    if "duplicate titles" in message_lower:
        badges.append('<span class="badge badge-duplicate">Duplicate Titles</span>')

    badge_str = "".join(badges)
    app_id = escape(result.app_id)
    album_name = escape(result.album_name)
    status_text = escape(status_raw.upper())
    message = escape(result.message)
    confidence_reason = escape(result.confidence_reason)
    steam_expected = escape(audit.get("steam_expected_slots", "-"))
    final_adopted = escape(audit.get("final_adopted_slots", "-"))
    legitimate_unknown = escape(audit.get("steam_legitimate_unknown", "-"))
    anomalous_unknown = escape(audit.get("anomalous_unknown", "-"))
    input_count = escape(audit.get("input_file_count", "-"))
    adopted_count = escape(audit.get("adopted_file_count", "-"))
    unassigned_count = escape(audit.get("unassigned_file_count", "-"))

    audit_text = (
        f"Steam: {steam_expected} → {final_adopted}<br>"
        f"Unknown: {legitimate_unknown} legitimate / {anomalous_unknown} anomalous<br>"
        f"Input: {input_count} / Adopted: {adopted_count} / Unassigned: {unassigned_count}"
    )

    return f"""
                    <tr>
                        <td>{app_id}</td>
                        <td>{album_name}</td>
                        <td class="{status_class}">{status_text}</td>
                        <td>{score}</td>
                        <td class="reason-box">{badge_str}<br>{message}</td>
                        <td class="reason-box"><strong>{primary_cause}</strong><br>{secondary_causes}</td>
                        <td class="reason-box">{audit_text}</td>
                        <td class="reason-box">{confidence_reason}</td>
                    </tr>
        """


def generate_batch_report(
    results: List[Any],
    output_path: Path,
    render_row: Callable[[Any], str],
) -> None:
    """Write the batch-level HTML report without owning per-album report rendering."""
    archive_count = sum(1 for result in results if result.status == "archive")
    review_count = sum(1 for result in results if result.status == "review")
    error_count = sum(1 for result in results if result.status == "error")
    skip_count = sum(1 for result in results if result.status == "skip")

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
                        <th>Primary / Secondary Cause</th>
                        <th>Audit Counters</th>
                        <th>LLM Confidence Reason</th>
                    </tr>
                </thead>
                <tbody>
        """

    for result in results:
        html += render_row(result)

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