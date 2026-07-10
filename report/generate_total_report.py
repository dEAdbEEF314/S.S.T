import sqlite3
import json
import re
import html
import glob
from pathlib import Path
from collections import Counter
from datetime import datetime

# --- Utilities ---
def levenshtein_distance(s1, s2):
    if len(s1) < len(s2): return levenshtein_distance(s2, s1)
    if len(s2) == 0: return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            del_ = curr[j] + 1
            sub = prev[j] + (c1 != c2)
            curr.append(min(ins, del_, sub))
        prev = curr
    return prev[-1]

def string_similarity(s1, s2):
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    s1 = re.sub(r'[\s\-_:\.\,\(\)\[\]\'\"]', '', s1)
    s2 = re.sub(r'[\s\-_:\.\,\(\)\[\]\'\"]', '', s2)
    if not s1 and not s2: return 1.0
    if not s1 or not s2: return 0.0
    return 1.0 - (levenshtein_distance(s1, s2) / max(len(s1), len(s2)))

def escape(t):
    return html.escape(str(t))

def app_link(app_id):
    return f'<a href="https://store.steampowered.com/app/{app_id}" target="_blank">{app_id}</a>'

# --- HTML CSS ---
CSS = """
:root { --bg-color: #0d1117; --card-bg: #161b22; --text-color: #c9d1d9; --accent-green: #238636; --accent-yellow: #d29922; --accent-red: #da3633; --border-color: #30363d; --table-header: #0d1117; }
body { font-family: -apple-system, sans-serif; background: var(--bg-color); color: var(--text-color); line-height: 1.6; padding: 20px; }
.container { max-width: 1400px; margin: 0 auto; }
h1, h2, h3 { border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }
.card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 10px; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-color); vertical-align: top; }
th { background: var(--table-header); color: #8b949e; }
tr:hover { background: #1c2128; }
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; background: #30363d; }
ul { margin: 0; padding-left: 20px; }
"""

def main():
    db_path = Path("data/sst_local_state.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT app_id, status, album_name, metadata_json FROM processed_albums")
    rows = cur.fetchall()

    results = []
    for row in rows:
        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        results.append({
            "app_id": row["app_id"],
            "status": row["status"],
            "album_name": row["album_name"],
            "meta": meta
        })
    conn.close()

    # Log Parsing
    log_files = sorted(glob.glob("logs/SST_DEBUG_*.log"))
    log_errors = []
    if log_files:
        latest_log = log_files[-1]
        try:
            with open(latest_log, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if "致命的な失敗" in line or "Audio encoding failed" in line or "response_truncated" in line or ("done_reason" in line and "length" in line):
                        log_errors.append(f"L{i+1}: {line.strip()}")
        except Exception:
            pass

    # --- Section 1: Archive ---
    archives = [r for r in results if r["status"] == "archive"]
    archive_reasons = Counter()
    archive_rows = []
    for r in archives:
        meta = r["meta"]
        msg = meta.get("message", "Unknown")
        archive_reasons[msg] += 1
        archive_rows.append((
            app_link(r['app_id']), escape(r['album_name']), 
            escape(meta.get('confidence_score', '')), escape(meta.get('strategy', '')), escape(msg)
        ))

    # --- Section 2: Unnatural Archive ---
    unnatural_archives = []
    for r in archives:
        meta = r["meta"]
        reasons = []
        for track in meta.get("tracks", []):
            mbz_album = track.get("tags", {}).get("album", "")
            if mbz_album and string_similarity(meta.get("album_name", ""), mbz_album) < 0.4:
                reasons.append(f"タイトル乖離: Steam '{meta.get('album_name')}' vs MBZ '{mbz_album}'")
                break
        
        ratio = meta.get("archive_vs_review_ratio", {})
        if ratio and ratio.get("review", 0) > 50:
            reasons.append(f"LLM矛盾救済: LLMはReview({ratio.get('review')}%)を推奨したがシステムがArchiveを強行")
            
        steam_count = len(meta.get("steam_info", {}).get("store_tracklist", []))
        actual_count = len(meta.get("tracks", []))
        if steam_count > 0 and abs(steam_count - actual_count) / steam_count > 0.2:
            reasons.append(f"Track Count乖離: Steam公式 {steam_count} vs 実際 {actual_count}")
            
        if reasons:
            unnatural_archives.append((
                app_link(r['app_id']), escape(r['album_name']), "<br>".join([escape(res) for res in reasons]),
                f"Conf: {meta.get('confidence_score')}, Qual: {meta.get('integrity_quality')}"
            ))

    # --- Section 3: Review ---
    reviews = [r for r in results if r["status"] == "review"]
    review_categories = Counter()
    review_rows = []
    for r in reviews:
        meta = r["meta"]
        msg = meta.get("message", "")
        diag = meta.get("diagnostics", {})
        if not msg and diag.get("review_cause_code") == "EARLY_REVIEW_RETURN":
            msg = f"EARLY_REVIEW_RETURN: {diag.get('upstream_cause_code')}"
            
        cat = "その他"
        if "Track#0" in msg: cat = "物理的欠損 (Track#0)"
        elif "Unknown Title" in msg: cat = "物理的欠損 (Unknown Title)"
        elif "Dirty Tags" in msg: cat = "タグ汚染 (Dirty Tags)"
        elif "Duplicate Titles" in msg: cat = "重複タイトル"
        elif "Duplicates" in msg: cat = "重複トラック"
        elif "Quality too low" in msg: cat = "品質不足"
        elif "Confidence too low" in msg: cat = "確信度不足"
        elif "LLM's decision" in msg: cat = "LLM判断 (Ratio)"
        elif "Audio Source Error" in msg: cat = "音声エラー"
        elif "Audio quality warning" in msg: cat = "音声警告"
        elif "EARLY_REVIEW_RETURN" in msg: cat = "LLM初期失敗"
        
        review_categories[cat] += 1
        review_rows.append((
            app_link(r['app_id']), escape(r['album_name']), 
            escape(meta.get('confidence_score', '')), escape(meta.get('integrity_quality', '')), 
            escape(msg), escape(meta.get('confidence_reason', '')), escape(diag.get('review_cause_code', ''))
        ))

    # --- Section 4: Irrational Review ---
    irrational_reviews = []
    for r in reviews:
        meta = r["meta"]
        conf = meta.get("confidence_score") or 0
        qual = meta.get("integrity_quality") or 0
        strategy = meta.get("strategy") or ""
        msg = meta.get("message", "")
        reasons = []
        
        if conf >= 100:
            if qual >= 95:
                reasons.append(f"高品質オーバーライド (Conf:{conf}, Qual:{qual}) -> {msg}")
            elif strategy in ["STEAM_BASED", "STEAM-TRUST"] and 70 <= qual < 75:
                reasons.append(f"Steam-Trust閾値近辺 (Conf:{conf}, Qual:{qual}) -> {msg}")
            else:
                reasons.append(f"高確信度オーバーライド (Conf:{conf}, Qual:{qual}) -> {msg}")
                
        if reasons:
            irrational_reviews.append((
                app_link(r['app_id']), escape(r['album_name']), 
                "<br>".join([escape(res) for res in reasons]),
                f"Validator Message: {escape(msg)}"
            ))

    # --- Section 5: Contradictions ---
    contradictions = []
    for r in results:
        meta = r["meta"]
        conf = meta.get("confidence_score") or 0
        qual = meta.get("integrity_quality") or 0
        ratio = meta.get("archive_vs_review_ratio") or {}
        status = meta.get("status")
        diag = meta.get("diagnostics") or {}
        
        reasons = []
        if conf >= 100 and qual >= 95 and ratio.get("archive", 0) < 50 and status == "review":
            reasons.append("LLM Archive推奨 -> System Review (Validatorによる物理チェック優先)")
        if (ratio.get("review", 0) > 50 or meta.get("strategy") == "REVIEW_REQUIRED") and status == "archive":
            reasons.append("LLM Review推奨 -> System Archive (スコア条件到達による強行)")
        if diag.get("review_cause_code") == "EARLY_REVIEW_RETURN" and conf > 0:
            reasons.append("Phase1成功 -> EARLY_REVIEW_RETURN (Phase2での中断)")
            
        if reasons:
            contradictions.append((
                app_link(r['app_id']), escape(r['album_name']), 
                "<br>".join([escape(res) for res in reasons]),
                f"Status: {escape(status)}, Conf: {conf}, Qual: {qual}, Ratio: {escape(str(ratio))}"
            ))

    # --- Section 6: Errors ---
    errors = [r for r in results if r["status"] == "error"]
    for r in results:
        diag = r["meta"].get("diagnostics", {})
        for t in diag.get("trace", []):
            if t.get("stage") == "EXCEPTION_FALLBACK" and r not in errors:
                errors.append(r)
                break
    error_rows = []
    for r in errors:
        meta = r["meta"]
        diag = meta.get("diagnostics", {})
        err_msg = meta.get("message", "Unknown Error")
        for t in diag.get("trace", []):
            if t.get("stage") == "EXCEPTION_FALLBACK":
                err_msg = t.get("details", {}).get("error", err_msg)
        error_rows.append((app_link(r['app_id']), escape(r['album_name']), escape(err_msg)))

    # --- Generate HTML ---
    def make_table(headers, rows):
        out = "<table><thead><tr>"
        for h in headers: out += f"<th>{h}</th>"
        out += "</tr></thead><tbody>"
        for row in rows:
            out += "<tr>"
            for c in row: out += f"<td>{c}</td>"
            out += "</tr>"
        out += "</tbody></table>"
        return out

    html_out = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head><meta charset="UTF-8"><title>S.S.T Total Analysis Report</title><style>{CSS}</style></head>
    <body>
    <div class="container">
        <h1>📊 S.S.T Total Analysis Report</h1>
        <p>生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="card">
            <h2>全体サマリー</h2>
            <ul>
                <li>Total: {len(results)}</li>
                <li>Archive: {len(archives)}</li>
                <li>Review: {len(reviews)}</li>
                <li>Error: {len(errors)}</li>
            </ul>
        </div>
        
        <div class="card" id="section1">
            <h2>1. Archive送り</h2>
            <p><strong>件数:</strong> {len(archives)}件</p>
            <h3>理由パターンサマリー</h3>
            <ul>
                {"".join([f"<li>{escape(k)}: {v}件</li>" for k, v in archive_reasons.most_common()])}
            </ul>
            <h3>詳細一覧</h3>
            {make_table(["AppID", "Album", "Score", "Strategy", "Message"], archive_rows)}
        </div>
        
        <div class="card" id="section2">
            <h2>2. 不自然なArchive送り</h2>
            <p><strong>件数:</strong> {len(unnatural_archives)}件</p>
            {make_table(["AppID", "Album", "不自然の根拠", "詳細情報"], unnatural_archives)}
        </div>
        
        <div class="card" id="section3">
            <h2>3. Review送り</h2>
            <p><strong>件数:</strong> {len(reviews)}件</p>
            <h3>理由カテゴリサマリー</h3>
            <ul>
                {"".join([f"<li>{escape(k)}: {v}件</li>" for k, v in review_categories.most_common()])}
            </ul>
            <h3>詳細一覧</h3>
            {make_table(["AppID", "Album", "Conf", "Qual", "Message", "Reason", "Cause Code"], review_rows)}
        </div>
        
        <div class="card" id="section4">
            <h2>4. 理不尽なReview送り</h2>
            <p><strong>件数:</strong> {len(irrational_reviews)}件</p>
            {make_table(["AppID", "Album", "理不尽の根拠", "詳細情報"], irrational_reviews)}
        </div>
        
        <div class="card" id="section5">
            <h2>5. LLM決定とシステム処理の矛盾</h2>
            <p><strong>件数:</strong> {len(contradictions)}件</p>
            {make_table(["AppID", "Album", "矛盾パターン", "詳細情報"], contradictions)}
        </div>
        
        <div class="card" id="section6">
            <h2>6. エラー・失敗</h2>
            <p><strong>DB記録エラー件数:</strong> {len(errors)}件</p>
            {make_table(["AppID", "Album", "Error Message"], error_rows)}
            
            <h3>ログ抽出エラー抜粋 (SST_DEBUG_*.log)</h3>
            <pre style="background:#090c10; padding:10px; border-radius:4px; overflow-x:auto;">
{escape(chr(10).join(log_errors)) if log_errors else "ログファイルから対象のエラー・警告は検出されませんでした。"}
            </pre>
        </div>
    </div>
    </body></html>
    """
    
    out_dir = Path("report")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "total_analysis_report.html"
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Report generated successfully at {out_path}")

if __name__ == "__main__":
    main()
