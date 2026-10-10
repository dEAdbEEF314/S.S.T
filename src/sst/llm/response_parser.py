import json
import re
from typing import Any, Callable, Dict, Optional


def _repair_duplicate_quote_before_chosen_mbz_id(
    json_str: str,
    error: json.JSONDecodeError,
) -> Optional[str]:
    if error.msg != "Expecting ':' delimiter" or error.pos < 2:
        return None
    if json_str[error.pos - 2:error.pos] != '""':
        return None
    prefix = json_str[:error.pos - 2].rstrip()
    if not prefix or prefix[-1] not in "{,":
        return None
    if not re.match(r"chosen_mbz_id\"\s*:", json_str[error.pos:]):
        return None

    repaired = json_str[:error.pos - 1] + json_str[error.pos:]
    try:
        parsed = json.loads(repaired)
    except json.JSONDecodeError:
        return None
    return repaired if isinstance(parsed, dict) else None


def _lower_mapping_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key.lower(): _lower_mapping_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_lower_mapping_keys(item) for item in value]
    return value


def parse_llm_response(
    content: str,
    request_kind: str,
    degraded_active: bool,
    repair_callback: Optional[Callable[[Dict[str, str]], None]] = None,
) -> Dict[str, Any]:
    clean_content = re.sub(r"```json\s*(.*?)\s*```", r"\1", content, flags=re.DOTALL)
    clean_content = re.sub(
        r"<(thought|reasoning)>.*?</\1>",
        "",
        clean_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    start_idx = clean_content.find("{")
    end_idx = clean_content.rfind("}")
    if start_idx == -1 or end_idx == -1:
        raise ValueError("No valid JSON object found in response")

    json_str = clean_content[start_idx : end_idx + 1]
    json_str = re.sub(r",\s*([\]}])", r"\1", json_str)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as parse_error:
        if request_kind != "identity":
            raise
        repaired_json = _repair_duplicate_quote_before_chosen_mbz_id(
            json_str,
            parse_error,
        )
        if repaired_json is None:
            raise
        parsed = json.loads(repaired_json)
        if repair_callback:
            repair_callback(
                {
                    "repair_code": "duplicate_quote_before_chosen_mbz_id",
                    "field": "chosen_mbz_id",
                }
            )
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    if request_kind == "identity":
        parsed = _lower_mapping_keys(parsed)

    if degraded_active:
        if request_kind == "identity":
            parsed.setdefault("confidence_reason", "縮退プロンプト適用（最小フォーマット判定）")
            parsed.setdefault("concerns", [])
            parsed.setdefault(
                "semantic_label",
                "Archive" if parsed.get("album_confidence", 0) >= 80 else "Review",
            )
            parsed.setdefault(
                "archive_vs_review_ratio",
                {
                    "archive": parsed.get("album_confidence", 0),
                    "review": 100 - parsed.get("album_confidence", 0),
                },
            )
            parsed.setdefault("identity_confidence", parsed.get("album_confidence", 0))
            parsed.setdefault("integrity_quality", parsed.get("data_quality", 0))
        elif request_kind == "track_mapping":
            slots = parsed.get("slots")
            if isinstance(slots, dict):
                for slot_info in slots.values():
                    if isinstance(slot_info, dict):
                        slot_info.setdefault("reason", "Degraded mapping")
            parsed.setdefault("unassigned_files", [])
            parsed.setdefault("unassigned_reason", "")

    return parsed