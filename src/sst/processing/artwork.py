import logging
from typing import Any, Callable, Dict, List, Optional

import requests

from ..models import SteamMetadata
from ..track_grouper import TrackManager
from ..utils import safe_validate_url

logger = logging.getLogger("sst.processor")


def safe_download_image(
    url: Optional[str],
    timeout: float = 15.0,
    max_bytes: int = 25 * 1024 * 1024,
    block_private: bool = True,
) -> Optional[bytes]:
    """Downloads an image securely with URL scheme validation, SSRF guard, and strict size limit."""
    if not url:
        return None

    block_private_bool = block_private if isinstance(block_private, bool) else True
    valid, reason = safe_validate_url(url, block_private=block_private_bool)
    if not valid:
        logger.warning(f"安全ガード: 画像URLを拒否しました ({reason}): {url}")
        return None

    try:
        timeout_float = float(timeout) if isinstance(timeout, (int, float)) else 15.0
        max_bytes_int = int(max_bytes) if isinstance(max_bytes, (int, float)) else 25 * 1024 * 1024
    except Exception:
        timeout_float = 15.0
        max_bytes_int = 25 * 1024 * 1024

    try:
        response = requests.get(str(url).strip(), timeout=timeout_float)
        if getattr(response, "status_code", None) == 200:
            headers = getattr(response, "headers", None)
            if headers and isinstance(headers, dict):
                content_type = str(headers.get("Content-Type", "")).lower()
                if content_type and not (
                    content_type.startswith("image/")
                    or "octet-stream" in content_type
                    or "binary" in content_type
                ):
                    logger.warning(f"安全ガード: 非画像Content-Typeを拒否しました ({content_type}): {url}")
                    return None

            content = getattr(response, "content", None)
            if content and isinstance(content, (bytes, bytearray)):
                if len(content) > max_bytes_int:
                    logger.warning(f"画像サイズが上限（{max_bytes_int} bytes）を超過したためダウンロードを中止しました: {url}")
                    return None
                if len(content) > 0:
                    return bytes(content)
    except Exception as error:
        logger.debug(f"画像のダウンロードに失敗しました ({url}): {error}")
    return None


def fetch_album_artwork(
    config: Any,
    mbz_client: Any,
    steam_meta: SteamMetadata,
    mbz_candidates: List[Dict[str, Any]],
    track_groups: Optional[Dict] = None,
    mbz_artwork_candidate_provider: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    on_mbz_candidate: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None,
) -> Optional[bytes]:
    if track_groups:
        for (disc, clean_title), files in track_groups.items():
            artwork = TrackManager.get_best_artwork(files)
            if artwork:
                logger.info(f"EMBEDソースからアルバムアートワークを採用しました (トラック: {clean_title})")
                return artwork

    mbz_candidate = mbz_candidates[0] if mbz_candidates else None
    if mbz_candidate is None and mbz_artwork_candidate_provider:
        mbz_candidate = mbz_artwork_candidate_provider()
    if on_mbz_candidate:
        on_mbz_candidate(mbz_candidate)
    if mbz_candidate and mbz_candidate.get("mbid"):
        url = mbz_client.get_release_artwork_url(mbz_candidate["mbid"])
        dl_timeout = float(getattr(config, "image_download_timeout", 15.0)) if isinstance(getattr(config, "image_download_timeout", None), (int, float)) else 15.0
        dl_max_bytes = int(getattr(config, "image_download_max_bytes", 25 * 1024 * 1024)) if isinstance(getattr(config, "image_download_max_bytes", None), (int, float)) else 25 * 1024 * 1024
        dl_block_private = bool(getattr(config, "security_block_private_ips", True)) if isinstance(getattr(config, "security_block_private_ips", None), bool) else True
        if url:
            artwork = safe_download_image(url, timeout=dl_timeout, max_bytes=dl_max_bytes, block_private=dl_block_private)
            if artwork:
                logger.info("MBZソースからアルバムアートワークを採用しました")
                return artwork

    dl_timeout = float(getattr(config, "image_download_timeout", 15.0)) if isinstance(getattr(config, "image_download_timeout", None), (int, float)) else 15.0
    dl_max_bytes = int(getattr(config, "image_download_max_bytes", 25 * 1024 * 1024)) if isinstance(getattr(config, "image_download_max_bytes", None), (int, float)) else 25 * 1024 * 1024
    dl_block_private = bool(getattr(config, "security_block_private_ips", True)) if isinstance(getattr(config, "security_block_private_ips", None), bool) else True

    def fetch_image(image_url: Optional[str], label: str) -> Optional[bytes]:
        artwork = safe_download_image(image_url, timeout=dl_timeout, max_bytes=dl_max_bytes, block_private=dl_block_private)
        if artwork:
            logger.info(f"STEAMソースからアルバムアートワークを採用しました ({label}: {image_url})")
            return artwork
        return None

    prefer_parent = bool(steam_meta.parent_app_id and not getattr(steam_meta, "has_sibling_soundtracks", False))

    steam_candidates = []
    if prefer_parent and steam_meta.parent_header_image_url:
        steam_candidates.append((steam_meta.parent_header_image_url, "親ゲーム公式ヘッダー"))
        if steam_meta.header_image_url:
            steam_candidates.append((steam_meta.header_image_url, "サントラ公式ヘッダー"))
    else:
        if steam_meta.header_image_url:
            label = "サントラ公式ヘッダー(複数サントラ排他)" if getattr(steam_meta, "has_sibling_soundtracks", False) else "サントラ公式ヘッダー"
            steam_candidates.append((steam_meta.header_image_url, label))
        if steam_meta.parent_header_image_url:
            steam_candidates.append((steam_meta.parent_header_image_url, "親ゲーム公式ヘッダー(フォールバック)"))

    if getattr(steam_meta, "capsule_image_url", None):
        steam_candidates.append((steam_meta.capsule_image_url, "サントラ公式カプセル"))
    steam_candidates.append((f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_meta.app_id}/header.jpg", "Steam CDN固定ヘッダー"))

    for image_url, label in steam_candidates:
        artwork = fetch_image(image_url, label)
        if artwork:
            return artwork

    logger.warning("全ソースから有効なアルバムアートワークを取得できませんでした")
    return None