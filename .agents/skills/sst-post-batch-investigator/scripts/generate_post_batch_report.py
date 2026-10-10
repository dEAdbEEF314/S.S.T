import sqlite3
import json
import html
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


IO_ERROR_PATTERN = re.compile(
    r"Host is down|Permission denied|PermissionError|(?:OSError|IOError|Errno\s*\d+)",
    re.IGNORECASE,
)
APP_ID_PATTERN = re.compile(r"\[(\d+)\]")
LOG_TIMESTAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")
IO_ERROR_LOOKBACK = timedelta(hours=6)


def _normalize_slot(disc, number):
    def normalize(value, default):
        normalized = str(value or default).split("/", 1)[0].strip().lstrip("0")
        return normalized or ("0" if default == "0" else "1")

    return normalize(disc, "1"), normalize(number, "0")


def _track_key(track):
    tags = track.get("tags") or {}
    return _normalize_slot(tags.get("disc_number", "1"), tags.get("track_number", "0"))


def _normalize_official_title(value):
    decoded = html.unescape(str(value or ""))
    normalized = unicodedata.normalize("NFKC", decoded)
    return " ".join(normalized.split()).casefold()


def _integrity_snapshot(meta, tracks):
    steam_info = meta.get("steam_info") or {}
    steam_tracklist = steam_info.get("store_tracklist") or []
    expected_slots = [
        _normalize_slot(slot.get("disc", 1), slot.get("number", "0"))
        for slot in steam_tracklist
    ]
    expected_titles = defaultdict(list)
    for slot, key in zip(steam_tracklist, expected_slots):
        expected_titles[key].append(str(slot.get("title") or slot.get("name") or "").strip())

    track_keys = [_track_key(track) for track in tracks]
    slot_keys = [str(track.get("slot_key") or "").strip() for track in tracks]
    format_counts = {}
    for track in tracks:
        suffix = Path(str(track.get("file_path", ""))).suffix.lower() or "unknown"
        format_counts[suffix] = format_counts.get(suffix, 0) + 1

    legitimate_unknown_count = 0
    anomalous_unknown_count = 0
    official_title_mismatch_count = 0
    for track, key in zip(tracks, track_keys):
        title = str((track.get("tags") or {}).get("title") or "Unknown").strip()
        official_titles = expected_titles.get(key, [])
        if official_titles and not any(
            _normalize_official_title(title) == _normalize_official_title(official_title)
            for official_title in official_titles
        ):
            official_title_mismatch_count += 1
        if title.casefold().startswith("unknown"):
            steam_titles = expected_titles.get(key, [])
            if steam_titles and all(value.casefold().startswith("unknown") for value in steam_titles):
                legitimate_unknown_count += 1
            else:
                anomalous_unknown_count += 1

    return {
        "expected_slot_count": len(expected_slots),
        "duplicate_expected_slot_count": len(expected_slots) - len(set(expected_slots)),
        "track_keys": track_keys,
        "duplicate_key_count": len(track_keys) - len(set(track_keys)),
        "missing_slots": sorted(set(expected_slots) - set(track_keys)),
        "unexpected_slots": sorted(set(track_keys) - set(expected_slots)) if expected_slots else [],
        "slot_key_count": len({key for key in slot_keys if key}),
        "missing_slot_key_count": sum(not key for key in slot_keys),
        "duplicate_slot_key_count": sum(bool(key) for key in slot_keys) - len({key for key in slot_keys if key}),
        "format_counts": format_counts,
        "fallback_count": sum(track.get("source") == "Fallback" for track in tracks),
        "local_title_count": sum(track.get("title_source") == "LOCAL" for track in tracks),
        "track_zero_count": sum(key[1] == "0" for key in track_keys),
        "unknown_title_count": legitimate_unknown_count + anomalous_unknown_count,
        "legitimate_unknown_title_count": legitimate_unknown_count,
        "anomalous_unknown_title_count": anomalous_unknown_count,
        "official_title_mismatch_count": official_title_mismatch_count,
    }


def _archive_integrity_issues(meta, tracks, integrity):
    issues = []
    html_entities = []
    for track in tracks:
        title = str((track.get("tags") or {}).get("title", ""))
        if any(entity in title for entity in ["&amp;", "&quot;", "&#39;", "&lt;", "&gt;"]):
            html_entities.append(title)

    if html_entities:
        issues.append(f"HTMLエンティティ未デコード ({len(html_entities)}トラック)")
    if not integrity["expected_slot_count"]:
        issues.append("Steamトラックリスト不在")
    if integrity["duplicate_expected_slot_count"]:
        issues.append(f"Steam期待slot重複 ({integrity['duplicate_expected_slot_count']})")
    if integrity["duplicate_key_count"]:
        issues.append(f"最終Disc/Track重複 ({integrity['duplicate_key_count']})")
    if integrity["duplicate_slot_key_count"]:
        issues.append(f"最終slot_key重複 ({integrity['duplicate_slot_key_count']})")
    if integrity["missing_slot_key_count"]:
        issues.append(f"最終slot_key欠落 ({integrity['missing_slot_key_count']})")
    if integrity["missing_slots"]:
        issues.append(f"Steam slot欠落 ({len(integrity['missing_slots'])})")
    if integrity["unexpected_slots"]:
        issues.append(f"Steam外slot ({len(integrity['unexpected_slots'])})")
    if integrity["expected_slot_count"] and len(tracks) != integrity["expected_slot_count"]:
        issues.append(f"Steam slot数不一致 ({len(tracks)}/{integrity['expected_slot_count']})")
    if integrity["track_zero_count"]:
        issues.append(f"Track#0 ({integrity['track_zero_count']})")
    if integrity["anomalous_unknown_title_count"]:
        issues.append(f"Steam根拠のないUnknownタイトル ({integrity['anomalous_unknown_title_count']})")
    if integrity["official_title_mismatch_count"]:
        issues.append(f"正本タイトル不一致 ({integrity['official_title_mismatch_count']})")
    if integrity["fallback_count"] or integrity["local_title_count"]:
        issues.append(f"Fallback/LOCAL残留 ({integrity['fallback_count']}/{integrity['local_title_count']})")
    return issues


def _read_io_error_events(log_dir):
    events = []
    for log_path in sorted(Path(log_dir).glob("*.log")):
        with log_path.open("r", encoding="utf-8", errors="ignore") as log_file:
            for line in log_file:
                if not IO_ERROR_PATTERN.search(line):
                    continue
                app_match = APP_ID_PATTERN.search(line)
                timestamp_match = LOG_TIMESTAMP_PATTERN.search(line)
                if app_match and timestamp_match:
                    timestamp = datetime.fromisoformat(timestamp_match.group(1)).astimezone()
                    events.append((int(app_match.group(1)), timestamp))
    return events


def _has_matching_io_error(item, io_error_events):
    processed_at = item["meta"].get("processed_at")
    if not processed_at:
        return False
    processed_time = datetime.fromisoformat(str(processed_at)).astimezone()
    return any(
        app_id == item["app_id"]
        and timedelta(0) <= processed_time - event_time <= IO_ERROR_LOOKBACK
        for app_id, event_time in io_error_events
    )


def _classify_review_causes(item, io_error_events):
    meta = item["meta"]
    diagnostics = meta.get("diagnostics") or {}
    message = str(item["msg"])
    reason = str(item["reason"])
    structured_causes = [
        diagnostics.get("primary_review_cause"),
        diagnostics.get("upstream_cause_code"),
        *(diagnostics.get("secondary_review_causes") or []),
    ]
    evidence = " ".join([message, reason, *(str(cause) for cause in structured_causes if cause)])
    causes = []

    if _has_matching_io_error(item, io_error_events) or "CRITICAL: Audio Source Error" in evidence or diagnostics.get("audio_source_failures"):
        causes.append("physical_io")
    if (
        "Audio quality warning" in evidence
        or bool(diagnostics.get("audio_quality_warnings"))
        or bool(diagnostics.get("conversion_warnings"))
    ):
        causes.append("audio_warning")
    if (
        message == "N/A (Early Review)"
        or "PRE_ALIGNMENT_REVIEW_GATE" in evidence
        or "Steam Tracklist Missing" in evidence
        or "No LLM response" in evidence
        or "EARLY_REVIEW" in str(diagnostics)
    ):
        causes.append("early_review")

    structural_tokens = (
        "Slots Missing",
        "Slots Unexpected",
        "Track Count Mismatch",
        "Duplicates",
        "Contradictory Slot Assignments",
        "Track#0",
        "Unknown Title",
        "Dirty Tags",
        "Official Title Mismatch",
    )
    integrity = item["integrity"]
    has_structural_issue = any(token in evidence for token in structural_tokens) or any(
        integrity[key]
        for key in (
            "duplicate_key_count",
            "duplicate_expected_slot_count",
            "duplicate_slot_key_count",
            "missing_slot_key_count",
            "missing_slots",
            "unexpected_slots",
            "track_zero_count",
            "anomalous_unknown_title_count",
            "official_title_mismatch_count",
        )
    )
    if has_structural_issue:
        causes.append("structural")

    if item["unassigned_count"] > 0 or "Unassigned Files" in evidence:
        causes.append("unassigned")
    if not causes:
        causes.append("confidence_or_other")
    return causes


def analyze_and_generate_report(db_path="data/sst_local_state.db", output_dir="report", log_dir="logs"):
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
    review_causes = {
        "physical_io": [],
        "audio_warning": [],
        "early_review": [],
        "structural": [],
        "unassigned": [],
        "confidence_or_other": [],
    }

    fast_track_count = 0

    io_error_events = _read_io_error_events(log_dir)

    for app_id, name, status, meta_str in rows:
        meta = json.loads(meta_str) if meta_str else {}
        tracks = meta.get('tracks', [])
        integrity = _integrity_snapshot(meta, tracks)
        conf = meta.get('confidence_score', 0)
        qual = meta.get('integrity_quality', 0)
        msg = meta.get('message') or 'N/A (Early Review)'
        reason = meta.get('confidence_reason') or 'No reason captured'
        strategy = meta.get('strategy') or 'N/A'

        diagnostics = meta.get("diagnostics") or {}
        processing_route = meta.get("processing_route") or diagnostics.get("processing_route")
        if processing_route == "FAST_TRACK":
            fast_track_count += 1

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
            issues = _archive_integrity_issues(meta, tracks, integrity)
            if issues:
                unnatural_archives.append({
                    'app_id': app_id,
                    'name': name,
                    'issues': issues
                })

        else:
            reviews.append(item)
            item["review_causes"] = _classify_review_causes(item, io_error_events)
            for cause in item["review_causes"]:
                review_causes[cause].append(item)

    review_cause_specs = (
        ("physical_io", "物理I/O / 音声ソース障害", "Permission denied、共有ストレージ障害、または致命的な音声ソースエラー。"),
        ("audio_warning", "音声品質警告", "変換またはデコード警告があり、物理破損の確定とは区別します。"),
        ("early_review", "早期Review / Steam情報不足", "通常のalignment・validatorより前にReviewとなった結果です。"),
        ("structural", "Steam構造・slot不整合", "重複、欠落・余分なslot、track 0、Steam根拠のないUnknown等。"),
        ("unassigned", "未割当ファイル / alignment残差", "最終的な未割当マニフェストまたはReview理由に未割当が記録されています。"),
        ("confidence_or_other", "信頼度不足・その他", "上記の物理・構造要因で説明されないReviewです。"),
    )
    review_cause_sections = []
    for cause, title, description in review_cause_specs:
        items = review_causes[cause]
        if cause == "unassigned":
            file_total = sum(item["unassigned_count"] for item in items)
            description += f" 該当{len(items)}アルバム、未割当ファイル記録{file_total}件。"
        examples = "".join(
            f"<li><code>AppID {item['app_id']}</code>: {html.escape(item['name'])} "
            f"(原因: {html.escape(str(item['msg']))})</li>"
            for item in items[:5]
        )
        review_cause_sections.append(
            f'<h3 class="card-subhead">{html.escape(title)} ({len(items)}件)</h3>'
            f'<div class="highlight-box warning"><p>{html.escape(description)}</p>'
            f'<ul>{examples}</ul></div>'
        )
    multi_cause_review_count = sum(
        len(item["review_causes"]) > 1 for item in reviews
    )

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
            <div class="kpi-label">Fast-Track 実行route件数</div>
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
        <p>各原因はmetadata・validator理由・診断ログから独立して付与する複数ラベルです。原因件数の合計はReviewアルバム数と一致するとは限りません。</p>
        <p>Reviewアルバム: {len(reviews)}件。複数原因に該当: {multi_cause_review_count}件。</p>
        {''.join(review_cause_sections)}
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
