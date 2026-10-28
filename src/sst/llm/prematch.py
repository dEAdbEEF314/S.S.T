from dataclasses import dataclass, field
from typing import Callable, List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger("sst.llm.prematch")


@dataclass
class PrematchResult:
    """LLM呼び出し前に解決済みのシグナル-スロット対応"""
    file_id: str
    acoustid_steam_slot: Optional[int] = None
    mbz_track_index: Optional[int] = None
    mbz_search_steam_slot: Optional[int] = None
    deterministic_steam_slot: Optional[int] = None
    target_v_idx: Optional[int] = None
    is_deterministic: bool = False
    override_track: Optional[str] = None
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "acoustid_steam_slot": self.acoustid_steam_slot,
            "mbz_track_index": self.mbz_track_index,
            "mbz_search_steam_slot": self.mbz_search_steam_slot,
            "deterministic_steam_slot": self.deterministic_steam_slot,
            "target_v_idx": self.target_v_idx,
            "is_deterministic": self.is_deterministic,
            "override_track": self.override_track,
            "evidence": list(self.evidence),
        }


def _titles_match(local_track: Dict[str, Any], steam_slot: Dict[str, Any]) -> bool:
    from ..track_grouper import TrackManager

    s_raw = str(steam_slot.get("t") or steam_slot.get("title") or "")
    l_raw = str(local_track.get("title") or local_track.get("norm_stem") or "")
    s_title = TrackManager.normalize_title(s_raw)
    l_title = TrackManager.normalize_title(l_raw)
    if not s_title or not l_title:
        return False
    return s_title == l_title or s_title in l_title or l_title in s_title


def _find_matching_steam_slot(
    track: Dict[str, Any],
    target_slot_num: str,
    disc_val: int,
    steam_by_disc_and_track: Dict[tuple[int, str], Dict[str, Any]],
    steam_slots_by_num: Dict[str, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    # Step A: (disc_val, target_slot_num) で存在し、タイトル整合する場合
    slot_a = steam_by_disc_and_track.get((disc_val, str(target_slot_num)))
    if slot_a and _titles_match(track, slot_a):
        return slot_a

    # Step B: 該当トラック番号のスロットのうちタイトル整合するスロットがただ1つ存在する場合
    candidates = [
        s for s in steam_slots_by_num.get(str(target_slot_num), [])
        if _titles_match(track, s)
    ]
    if len(candidates) == 1:
        return candidates[0]

    return None


def resolve_prematch_signals(
    local_tracks: List[Dict[str, Any]],
    full_ref_steam: List[Dict[str, Any]],
    full_ref_fingerprint: List[Dict[str, Any]],
    full_ref_mbz_search: List[Dict[str, Any]],
    v_mbz_search: Optional[Dict[str, Any]] = None,
) -> Dict[str, PrematchResult]:
    """
    ローカルファイルの各 file_id に対し、AcoustID/MBZ_RELEASE/MBZ_SEARCH と
    Steam スロットの対応関係を機械的に事前解決する。
    """
    prematch_map: Dict[str, PrematchResult] = {}

    # 1. full_ref_fingerprint を (disc, track_num) または v_idx でインデックス化
    fingerprint_by_v_idx: Dict[int, Dict[str, Any]] = {
        int(t["v_idx"]): t for t in full_ref_fingerprint if t.get("v_idx") is not None
    }
    mbz_search_by_v_idx: Dict[int, Dict[str, Any]] = {
        int(t["v_idx"]): t for t in full_ref_mbz_search if t.get("v_idx") is not None
    }
    steam_by_disc_and_track: Dict[tuple[int, str], Dict[str, Any]] = {
        (int(t.get("d") or t.get("disc") or 1), str(t.get("n"))): t
        for t in full_ref_steam if t.get("n") is not None
    }
    steam_slots_by_num: Dict[str, List[Dict[str, Any]]] = {}
    for t in full_ref_steam:
        if t.get("n") is not None:
            steam_slots_by_num.setdefault(str(t.get("n")), []).append(t)

    for track in local_tracks:
        file_ids = [str(fid) for fid in track.get("file_ids", [])]
        track_num = track.get("track_num") or track.get("filename_track")
        disc_val = int(track.get("disc") or 1)

        # AcoustID/MBZ_RELEASE からのシグナル解決
        # ローカルのトラック番号やインデックスに対応する fingerprint を探す
        fp_candidate = None
        if track.get("v_idx") is not None and track.get("v_idx") in fingerprint_by_v_idx:
            fp_candidate = fingerprint_by_v_idx[track["v_idx"]]
        elif track_num is not None:
            # トラック番号一致を探す（ディスク番号一致を優先）
            for fp in full_ref_fingerprint:
                if str(fp.get("n")) == str(track_num):
                    fp_disc = int(fp.get("d") or fp.get("disc") or 1)
                    if fp_disc == disc_val:
                        fp_candidate = fp
                        break
                    elif fp_candidate is None:
                        fp_candidate = fp

        mbz_search_candidate = None
        if v_mbz_search:
            if track.get("v_idx") is not None and track.get("v_idx") in mbz_search_by_v_idx:
                mbz_search_candidate = mbz_search_by_v_idx[track["v_idx"]]
            elif track_num is not None:
                for ms in full_ref_mbz_search:
                    if str(ms.get("n")) == str(track_num):
                        ms_disc = int(ms.get("d") or ms.get("disc") or 1)
                        if ms_disc == disc_val:
                            mbz_search_candidate = ms
                            break
                        elif mbz_search_candidate is None:
                            mbz_search_candidate = ms

        for file_id in file_ids:
            res = PrematchResult(file_id=file_id)

            if fp_candidate:
                res.mbz_track_index = fp_candidate.get("mbz_idx")
                if fp_candidate.get("n") is not None:
                    res.override_track = str(fp_candidate.get("n"))
                # Steam スロット番号との照合
                target_slot_num = str(fp_candidate.get("n"))
                fp_disc = int(fp_candidate.get("d") or fp_candidate.get("disc") or disc_val)
                steam_slot = _find_matching_steam_slot(
                    track, target_slot_num, fp_disc, steam_by_disc_and_track, steam_slots_by_num
                )
                if steam_slot:
                    slot_n = steam_slot.get("n", target_slot_num)
                    res.acoustid_steam_slot = int(slot_n) if str(slot_n).isdigit() else None
                    res.target_v_idx = steam_slot.get("v_idx")
                    res.evidence.append("acoustid_match")

            if mbz_search_candidate:
                if res.mbz_track_index is None:
                    res.mbz_track_index = mbz_search_candidate.get("mbz_idx")
                if res.override_track is None and mbz_search_candidate.get("n") is not None:
                    res.override_track = str(mbz_search_candidate.get("n"))
                target_slot_num = str(mbz_search_candidate.get("n"))
                ms_disc = int(mbz_search_candidate.get("d") or mbz_search_candidate.get("disc") or disc_val)
                steam_slot = _find_matching_steam_slot(
                    track, target_slot_num, ms_disc, steam_by_disc_and_track, steam_slots_by_num
                )
                if steam_slot:
                    slot_n = steam_slot.get("n", target_slot_num)
                    res.mbz_search_steam_slot = int(slot_n) if str(slot_n).isdigit() else None
                    if res.target_v_idx is None:
                        res.target_v_idx = steam_slot.get("v_idx")
                    res.evidence.append("mbz_search_match")

            # 確定的一致（Deterministic 1:1 match）の判定
            # 番号が有効な Steam スロットを指しており、タイトルが一致（または AcoustID が一致）する場合
            det_slot = None
            target_v = None
            if res.acoustid_steam_slot is not None:
                det_slot = res.acoustid_steam_slot
                target_v = res.target_v_idx
                res.evidence.append("deterministic_acoustid")
            elif track_num is not None:
                steam_slot = _find_matching_steam_slot(
                    track, str(track_num), disc_val, steam_by_disc_and_track, steam_slots_by_num
                )
                if steam_slot:
                    slot_n = steam_slot.get("n", track_num)
                    det_slot = int(slot_n) if str(slot_n).isdigit() else None
                    target_v = steam_slot.get("v_idx")
                    res.evidence.append("deterministic_number_and_title")

            if det_slot is not None:
                res.deterministic_steam_slot = det_slot
                res.target_v_idx = target_v
                res.is_deterministic = True
                if res.override_track is None:
                    res.override_track = str(det_slot)

            prematch_map[file_id] = res

    return prematch_map


def extract_deterministic_prematches(
    local_tracks: List[Dict[str, Any]],
    full_ref_steam: List[Dict[str, Any]],
    prematch_map: Dict[str, Any],
    global_res: Dict[str, Any],
    *,
    resolve_slot_key: Callable[[str, Optional[List[Dict[str, Any]]]], Optional[int]],
) -> Tuple[
    Dict[str, Dict[str, Any]],
    set[int],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    deterministic_instructions: Dict[str, Dict[str, Any]] = {}
    resolved_v_indices: set[int] = set()
    resolved_local_indices: set[int] = set()

    fid_to_track_idx = {}
    for index, track in enumerate(local_tracks):
        for file_id in track.get("file_ids", []):
            fid_to_track_idx[str(file_id)] = index

    from collections import defaultdict
    from ..track_grouper import TrackManager

    # 1. 決定論的プレマッチ候補を matched_v_idx ごとに集計
    v_idx_to_candidates: Dict[int, List[Tuple[str, Any, int]]] = defaultdict(list)
    for file_id, prematch in prematch_map.items():
        if not prematch or not prematch.is_deterministic:
            continue
        matched_v_idx = prematch.target_v_idx
        if matched_v_idx is None and prematch.deterministic_steam_slot is not None:
            matched_v_idx = resolve_slot_key(
                str(prematch.deterministic_steam_slot),
                full_ref_steam,
            )

        if matched_v_idx is None or not (0 <= matched_v_idx < len(full_ref_steam)):
            continue

        track_index = fid_to_track_idx.get(file_id)
        if track_index is None:
            continue
        v_idx_to_candidates[matched_v_idx].append((file_id, prematch, track_index))

    # 2. 同一 v_idx への異タイトル多重確定の防止（衝突検出）
    colliding_v_indices: set[int] = set()
    for matched_v_idx, candidates in v_idx_to_candidates.items():
        distinct_track_indices = {c[2] for c in candidates}
        if len(distinct_track_indices) > 1:
            norm_titles = {
                TrackManager.normalize_title(
                    str(local_tracks[idx].get("title") or local_tracks[idx].get("norm_stem") or "")
                )
                for idx in distinct_track_indices
            }
            if len(norm_titles) > 1:
                colliding_v_indices.add(matched_v_idx)
                logger.warning(
                    f"決定論的プレマッチ衝突検出: v_idx={matched_v_idx} に異なるタイトルのトラック {distinct_track_indices} が多重割り当てされました。LLM Phase 2 に委ねるため除外します。"
                )

    # 3. 衝突していないスロットのみ決定論的指示を生成
    for matched_v_idx, candidates in v_idx_to_candidates.items():
        if matched_v_idx in colliding_v_indices:
            for file_id, prematch, _ in candidates:
                prematch.is_deterministic = False
            continue

        resolved_v_indices.add(matched_v_idx)
        steam_slot = full_ref_steam[matched_v_idx]
        tags = global_res.get("global_tags", {})
        if not isinstance(tags, dict):
            tags = {}

        for file_id, prematch, track_index in candidates:
            resolved_local_indices.add(track_index)
            matching_track = local_tracks[track_index]
            track_id = f"{matching_track['local_key'][0]}_{matching_track['local_key'][1]}"
            slot_number = steam_slot.get("n") or prematch.override_track or (matched_v_idx + 1)
            deterministic_instructions[track_id] = {
                "matched_v_idx": matched_v_idx,
                "mbz_track_index": prematch.mbz_track_index,
                "override_title": None,
                "override_track": str(slot_number),
                "override_disc": str(steam_slot.get("d") or steam_slot.get("disc") or 1),
                "reason": f"SYSTEM: Deterministic match ({prematch.evidence[0] if prematch.evidence else 'exact'})",
                "TPE2": tags.get("canonical_album_artist"),
                "TCON": tags.get("canonical_genre"),
                "TDRC": tags.get("canonical_year"),
                "TPUB": tags.get("canonical_label"),
            }

    unmatched_local_tracks = [
        track
        for index, track in enumerate(local_tracks)
        if index not in resolved_local_indices
    ]
    unfilled_steam_slots = [
        slot
        for slot in full_ref_steam
        if slot.get("v_idx") not in resolved_v_indices
    ]
    return (
        deterministic_instructions,
        resolved_v_indices,
        unmatched_local_tracks,
        unfilled_steam_slots,
    )
