from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
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
            "is_deterministic": self.is_deterministic,
            "override_track": self.override_track,
            "evidence": list(self.evidence),
        }


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
        t.get("v_idx"): t for t in full_ref_fingerprint if t.get("v_idx") is not None
    }
    mbz_search_by_v_idx: Dict[int, Dict[str, Any]] = {
        t.get("v_idx"): t for t in full_ref_mbz_search if t.get("v_idx") is not None
    }
    steam_by_slot_num: Dict[str, Dict[str, Any]] = {
        str(t.get("n")): t for t in full_ref_steam if t.get("n") is not None
    }

    for track in local_tracks:
        file_ids = [str(fid) for fid in track.get("file_ids", [])]
        track_num = track.get("track_num") or track.get("filename_track")

        # AcoustID/MBZ_RELEASE からのシグナル解決
        # ローカルのトラック番号やインデックスに対応する fingerprint を探す
        fp_candidate = None
        if track.get("v_idx") is not None and track.get("v_idx") in fingerprint_by_v_idx:
            fp_candidate = fingerprint_by_v_idx[track["v_idx"]]
        elif track_num is not None:
            # トラック番号一致を探す
            for fp in full_ref_fingerprint:
                if str(fp.get("n")) == str(track_num):
                    fp_candidate = fp
                    break

        mbz_search_candidate = None
        if v_mbz_search:
            if track.get("v_idx") is not None and track.get("v_idx") in mbz_search_by_v_idx:
                mbz_search_candidate = mbz_search_by_v_idx[track["v_idx"]]
            elif track_num is not None:
                for ms in full_ref_mbz_search:
                    if str(ms.get("n")) == str(track_num):
                        mbz_search_candidate = ms
                        break

        for file_id in file_ids:
            res = PrematchResult(file_id=file_id)

            if fp_candidate:
                res.mbz_track_index = fp_candidate.get("mbz_idx")
                if fp_candidate.get("n") is not None:
                    res.override_track = str(fp_candidate.get("n"))
                # Steam スロット番号との照合
                target_slot_num = str(fp_candidate.get("n"))
                if target_slot_num in steam_by_slot_num:
                    steam_slot = steam_by_slot_num[target_slot_num]
                    res.acoustid_steam_slot = int(steam_slot.get("n", target_slot_num)) if str(steam_slot.get("n", "")).isdigit() else None
                    res.evidence.append("acoustid_match")

            if mbz_search_candidate:
                if res.mbz_track_index is None:
                    res.mbz_track_index = mbz_search_candidate.get("mbz_idx")
                if res.override_track is None and mbz_search_candidate.get("n") is not None:
                    res.override_track = str(mbz_search_candidate.get("n"))
                target_slot_num = str(mbz_search_candidate.get("n"))
                if target_slot_num in steam_by_slot_num:
                    steam_slot = steam_by_slot_num[target_slot_num]
                    res.mbz_search_steam_slot = int(steam_slot.get("n", target_slot_num)) if str(steam_slot.get("n", "")).isdigit() else None
                    res.evidence.append("mbz_search_match")

            # 確定的一致（Deterministic 1:1 match）の判定
            # 番号が有効な Steam スロットを指しており、タイトルが一致（または AcoustID が一致）する場合
            det_slot = None
            if res.acoustid_steam_slot is not None:
                det_slot = res.acoustid_steam_slot
                res.evidence.append("deterministic_acoustid")
            elif track_num is not None and str(track_num) in steam_by_slot_num:
                steam_slot = steam_by_slot_num[str(track_num)]
                # タイトル照合
                from ..track_grouper import TrackManager
                s_title = TrackManager.normalize_title(str(steam_slot.get("t") or steam_slot.get("title") or ""))
                l_title = TrackManager.normalize_title(str(track.get("title") or track.get("norm_stem") or ""))
                if not s_title or not l_title or s_title == l_title or s_title in l_title or l_title in s_title:
                    slot_n = steam_slot.get("n", track_num)
                    det_slot = int(slot_n) if str(slot_n).isdigit() else None
                    res.evidence.append("deterministic_number_and_title")

            if det_slot is not None:
                res.deterministic_steam_slot = det_slot
                res.is_deterministic = True
                if res.override_track is None:
                    res.override_track = str(det_slot)

            prematch_map[file_id] = res

    return prematch_map
