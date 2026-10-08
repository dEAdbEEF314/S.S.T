from .processing.fast_track import (
    apply_mbz_track_artists as _apply_mbz_track_artists,
)
from .processing.artwork import (
    fetch_album_artwork as _fetch_album_artwork,
    safe_download_image as _safe_download_image,
)
from .processing.slot_variants import (
    build_slot_variant_index as _build_slot_variant_index,
    merge_embedded_tags_for_slot as _merge_embedded_tags_for_slot,
)
from .processing.file_selection import (
    adopt_best_file_per_slot as _adopt_best_file_per_slot,
    select_best_unassigned_files as _select_best_unassigned_files,
    select_slot_conflict_candidates as _select_slot_conflict_candidates,
)
from .processing.unassigned import (
    reconcile_deterministic_unassigned_slots as _reconcile_deterministic_unassigned_slots,
)
from .processing.notifications import send_notifications as _send_notifications
from .processing.duplicate_mappings import resolve_duplicate_mappings as _resolve_duplicate_mappings

apply_mbz_track_artists_to_fast_track = _apply_mbz_track_artists
fetch_album_artwork = _fetch_album_artwork
safe_download_image = _safe_download_image
build_slot_variant_index = _build_slot_variant_index
merge_embedded_tags_for_slot = _merge_embedded_tags_for_slot
adopt_best_file_per_slot = _adopt_best_file_per_slot
select_best_unassigned_files = _select_best_unassigned_files
select_slot_conflict_candidates = _select_slot_conflict_candidates
reconcile_deterministic_unassigned_slots = _reconcile_deterministic_unassigned_slots
send_notifications = _send_notifications
resolve_duplicate_mappings = _resolve_duplicate_mappings
