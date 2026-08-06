import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


def validate_llm_tracklist(
    response: Any,
    local_track_count: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not isinstance(response, dict):
        return [], ["response_not_object"]

    tracks = response.get("tracks")
    if not isinstance(tracks, list):
        return [], ["tracks_not_list"]
    if len(tracks) < 2:
        return [], ["too_few_tracks"]
    if local_track_count is not None and len(tracks) != local_track_count:
        return [], ["track_count_mismatch"]

    normalized: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen_slots = set()
    for index, track in enumerate(tracks):
        if not isinstance(track, dict):
            errors.append(f"track_{index}_not_object")
            continue
        disc = _positive_integer(track.get("disc", 1))
        number = _positive_integer(track.get("number"))
        title = track.get("title")
        slot = (disc, number)
        if disc is not None and number is not None:
            if slot in seen_slots:
                errors.append(f"duplicate_slot_{disc}_{number}")
            seen_slots.add(slot)
        if disc is None:
            errors.append(f"track_{index}_invalid_disc")
        if number is None:
            errors.append(f"track_{index}_invalid_number")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"track_{index}_empty_title")
        if disc is None or number is None or not isinstance(title, str) or not title.strip():
            continue

        normalized_track = {
            "disc": disc,
            "number": str(number),
            "title": title.strip(),
            "duration_s": _optional_duration(track.get("duration_s")),
            "source": "STEAM_TEXT_TRACKLIST_LLM",
        }
        normalized.append(normalized_track)

    if errors:
        return [], errors

    disc_numbers: Dict[int, List[int]] = {}
    for track in normalized:
        disc_numbers.setdefault(track["disc"], []).append(int(track["number"]))
    for disc, numbers in disc_numbers.items():
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            errors.append(f"non_contiguous_disc_{disc}")

    if errors:
        return [], errors
    return normalized, []


def _positive_integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_duration(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+):([0-5]\d)\s*", value)
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
    return None