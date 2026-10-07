from typing import Any, Dict, List


def send_notifications(
    notifier: Any,
    app_id: int,
    name: str,
    status: str,
    message: str,
    score: int,
    reason: str,
    llm_log: Dict[str, Any],
    any_audio_failures: bool,
    track_count: int,
    mbz_candidates: List[Dict[str, Any]],
) -> str:
    p1_res = llm_log.get("phase1_res") or {}
    id_conf = p1_res.get("album_confidence", p1_res.get("identity_confidence", 0))
    mapping_conf = p1_res.get("mapping_confidence", id_conf)
    quality = p1_res.get("data_quality", p1_res.get("integrity_quality", 0))
    ratio = p1_res.get("archive_vs_review_ratio", {"archive": 0, "review": 0})
    is_fast = llm_log.get("fast_track", False)

    route = llm_log.get("processing_route") or ("FAST_TRACK" if is_fast else "LLM_ONE_SHOT")
    route_display_map = {
        "FAST_TRACK": "⚡ FAST_TRACK (決定論的即時確定 / LLMバイパス)",
        "LLM_ONE_SHOT": "🧠 LLM_ONE_SHOT (オンデマンド信号収集 + 1-Shot推論)",
        "LLM_CHUNKED": "🧩 LLM_CHUNKED (分割チャンク推論)",
        "SKIP_NO_AUDIO": "⏩ SKIP_NO_AUDIO (音源なしスキップ)",
        "ERROR": "❌ ERROR (処理エラー)",
    }
    route_display = route_display_map.get(route, f"🛣️ {route}")

    fields = [
        {"name": "AppID", "value": f"[{app_id}](https://store.steampowered.com/app/{app_id})", "inline": True},
        {"name": "Status", "value": f"**{status.upper()}**", "inline": True},
        {"name": "Tracks", "value": str(track_count), "inline": True},
        {"name": "🛣️ 処理経路 (Route)", "value": f"**{route_display}**", "inline": False},
        {"name": "Album / Mapping / Data", "value": f"Alb: {id_conf}% / Map: {mapping_conf}% / Data: {quality}%", "inline": True},
        {"name": "Decision Ratio", "value": f"Arch {ratio.get('archive', 0)}% : Rev {ratio.get('review', 0)}%", "inline": True},
    ]

    if mbz_candidates:
        top_mbz = mbz_candidates[0]
        mbz_value = f"[{top_mbz.get('album')}](https://musicbrainz.org/release/{top_mbz.get('mbid')}) (Score: {top_mbz.get('score')})"
        fields.append({"name": "MusicBrainz (Top Candidate)", "value": mbz_value, "inline": False})

    fields.append({"name": "⚙️ System Logic Reason", "value": f"**{message}**", "inline": False})

    llm_reason = "Bypassed for Fast-Track" if is_fast else (reason or "No reason provided.")
    if len(llm_reason) > 1000:
        llm_reason = llm_reason[:997] + "..."
    fields.append({"name": "🧠 LLM Judgment Reason", "value": llm_reason, "inline": False})

    diagnostics = llm_log.get("diagnostics") or {}
    audio_warned_tracks = diagnostics.get("audio_warned_tracks") or []
    if audio_warned_tracks:
        warned_tracks = ", ".join(str(track) for track in audio_warned_tracks)
        fields.append({
            "name": "⚠️ 音声品質警告（本来Archive相当 / 微小異常あり）",
            "value": f"構造・タグは完全一致していますが、微小な音声フレーム警告が発生したためReview送りとしました（対象: `{warned_tracks}`）",
            "inline": False,
        })

    if any_audio_failures:
        fields.append({"name": "🚨 CRITICAL ALERT", "value": "One or more tracks failed to encode correctly.", "inline": False})

    if status == "review":
        notifier.notify_warning(f"要レビュー: {name}", f"AppID {app_id} は手動確認が必要です", fields)
    else:
        notifier.notify_info(f"アーカイブ完了: {name}", f"AppID {app_id} の自動アーカイブに成功しました", fields)

    markdown_lines = [f"# {status.upper()}: {name}", f"AppID: {app_id}", ""]
    for field in fields:
        markdown_lines.append(f"**{field['name']}**: {field['value']}")
    return "\n".join(markdown_lines)