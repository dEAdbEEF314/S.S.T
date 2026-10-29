from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, List, Dict, Any, Optional, Tuple
import logging
import re

from ..track_grouper import TrackManager

logger = logging.getLogger("sst.llm.prematch")

_VERSION_QUALIFIERS = frozenset({
    "short", "long", "full", "extended", "inst", "instrumental",
    "vocal", "offvocal", "karaoke", "demo", "proto", "prototype",
    "beta", "unused", "alternate", "alt", "remix", "arrange",
    "arranged", "8bit", "16bit", "chiptune", "piano", "acoustic",
    "live", "orchestra", "orchestral", "cinematic", "trailer",
    "opening", "ending", "op", "ed", "intro", "outro", "loop",
})


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


def _has_conflicting_numbers_or_qualifiers(title_a: str, title_b: str) -> bool:
    nums_a = re.findall(r"\d+", title_a)
    nums_b = re.findall(r"\d+", title_b)
    if nums_a != nums_b:
        return True
    tokens_a = set(title_a.split()) & _VERSION_QUALIFIERS
    tokens_b = set(title_b.split()) & _VERSION_QUALIFIERS
    if tokens_a != tokens_b:
        return True
    return False


def _strip_parenthetical_and_subtitle(raw: str) -> str:
    from ..track_grouper import TrackManager

    cleaned = re.sub(r"\s*[\(\[（【].*?[\)\]）】]", "", raw)
    cleaned = re.sub(r"\s*[〜~].*?[〜~]", "", cleaned)
    if " - " in cleaned:
        cleaned = cleaned.split(" - ", 1)[0]
    return TrackManager.normalize_title(cleaned)


def _extract_steam_candidates(steam_slot: Dict[str, Any]) -> List[str]:
    from ..track_grouper import TrackManager

    s_raw = str(steam_slot.get("t") or steam_slot.get("title") or "").strip()
    if not s_raw:
        return []
    raw_list = [s_raw]
    s_no_by = re.sub(r"\s+by\s+.+$", "", s_raw, flags=re.IGNORECASE).strip()
    if s_no_by and s_no_by != s_raw:
        raw_list.append(s_no_by)
    result: List[str] = []
    for item in raw_list:
        norm = TrackManager.normalize_title(item)
        if norm and norm not in result:
            result.append(norm)
    return result


def _extract_local_candidates(local_track: Dict[str, Any]) -> List[str]:
    from ..track_grouper import TrackManager

    raw_list: List[str] = []
    for key in ("title", "norm_stem"):
        val = local_track.get(key)
        if isinstance(val, str) and val.strip():
            raw_list.append(val.strip())
    local_key = local_track.get("local_key")
    if isinstance(local_key, (tuple, list)) and len(local_key) >= 2:
        lk_val = str(local_key[1]).strip()
        if lk_val:
            raw_list.append(lk_val)

    expanded: List[str] = []
    for item in raw_list:
        expanded.append(item)
        if " - " in item:
            after_sep = item.split(" - ", 1)[1].strip()
            if after_sep:
                expanded.append(after_sep)
        no_by = re.sub(r"\s+by\s+.+$", "", item, flags=re.IGNORECASE).strip()
        if no_by and no_by != item:
            expanded.append(no_by)

    result: List[str] = []
    for item in expanded:
        norm = TrackManager.normalize_title(item)
        if norm and norm not in result:
            result.append(norm)
    return result


def _exact_title_match(local_track: Dict[str, Any], steam_slot: Dict[str, Any]) -> bool:
    from ..track_grouper import TrackManager

    s_raw = str(steam_slot.get("t") or steam_slot.get("title") or "").strip()
    l_raw = str(local_track.get("title") or local_track.get("t") or "").strip()
    lk_raw = ""
    local_key = local_track.get("local_key")
    if isinstance(local_key, (tuple, list)) and len(local_key) >= 2:
        lk_raw = str(local_key[1]).strip()

    # 1. 非ストリップ（生タイトル）完全一致の検査 (strip_track_prefix=False)
    s_norm_raw = TrackManager.normalize_title(s_raw, strip_track_prefix=False)
    for l_cand_raw in filter(None, [l_raw, lk_raw, str(local_track.get("norm_stem") or "").strip()]):
        l_norm_raw = TrackManager.normalize_title(l_cand_raw, strip_track_prefix=False)
        if s_norm_raw and l_norm_raw and (s_norm_raw == l_norm_raw or s_norm_raw.replace(" ", "") == l_norm_raw.replace(" ", "")):
            return True

    # 2. 先頭番号プレフィックス食い違いガード:
    # steam_slot の生タイトル自体が ^\d{1,3}[\s._-]+ で始まっており、
    # かつローカルの生タイトルも ^\d{1,3}[\s._-]+ で始まっている場合、
    # 先頭数値同士が異なる場合は後続のストリップ後比較で誤マッチしないよう False を返す
    m_s = re.match(r"^\s*(\d{1,3})[\s._-]+", s_raw)
    m_l = re.match(r"^\s*(\d{1,3})[\s._-]+", l_raw)
    if not m_l and lk_raw:
        m_l = re.match(r"^\s*(\d{1,3})[\s._-]+", lk_raw)
    if m_s and m_l:
        if int(m_s.group(1)) != int(m_l.group(1)):
            return False

    # 3. 通常の候補比較（ストリップ後等）
    s_cands = _extract_steam_candidates(steam_slot)
    l_cands = _extract_local_candidates(local_track)
    if not s_cands or not l_cands:
        return False
    for s_title in s_cands:
        s_compact = s_title.replace(" ", "")
        for l_title in l_cands:
            if s_title == l_title or (s_compact and s_compact == l_title.replace(" ", "")):
                return True
    return False


def _titles_match(
    local_track: Dict[str, Any],
    steam_slot: Dict[str, Any],
    full_ref_steam: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    s_raw = str(steam_slot.get("t") or steam_slot.get("title") or "").strip()
    l_raw = str(local_track.get("title") or local_track.get("t") or "").strip()
    lk_raw = ""
    local_key = local_track.get("local_key")
    if isinstance(local_key, (tuple, list)) and len(local_key) >= 2:
        lk_raw = str(local_key[1]).strip()

    # 先頭番号プレフィックス食い違いガード:
    m_s = re.match(r"^\s*(\d{1,3})[\s._-]+", s_raw)
    m_l = re.match(r"^\s*(\d{1,3})[\s._-]+", l_raw)
    if not m_l and lk_raw:
        m_l = re.match(r"^\s*(\d{1,3})[\s._-]+", lk_raw)
    if m_s and m_l and int(m_s.group(1)) != int(m_l.group(1)):
        return False

    s_cands = _extract_steam_candidates(steam_slot)
    l_cands = _extract_local_candidates(local_track)
    if not s_cands or not l_cands:
        return False

    l_num = local_track.get("track_num") or local_track.get("filename_track")
    s_num = steam_slot.get("n")
    l_dur = local_track.get("duration_ms")
    s_dur = steam_slot.get("duration_ms")
    if s_dur is None and steam_slot.get("dur") is not None:
        try:
            s_dur = int(steam_slot["dur"]) * 1000
        except (TypeError, ValueError):
            s_dur = None

    same_slot_and_duration = False
    if l_num is not None and s_num is not None and str(l_num) == str(s_num):
        if l_dur is not None and s_dur is not None and int(l_dur) > 0 and int(s_dur) > 0:
            same_slot_and_duration = abs(int(l_dur) - int(s_dur)) <= 5000
        else:
            same_slot_and_duration = True

    for s_title in s_cands:
        s_compact = s_title.replace(" ", "")
        for l_title in l_cands:
            l_compact = l_title.replace(" ", "")
            # 1. 完全一致またはスペース除去一致
            if s_title == l_title or (s_compact and s_compact == l_compact):
                return True

            # 2. 単語境界を伴う包含一致（数値トークン・バージョン修飾語が矛盾しない場合のみ）
            if not _has_conflicting_numbers_or_qualifiers(s_title, l_title):
                if f" {s_title} " in f" {l_title} " or f" {l_title} " in f" {s_title} ":
                    return True

            # 3. 同一トラック番号かつ尺整合時の緩和マッチング
            if same_slot_and_duration and not _has_conflicting_numbers_or_qualifiers(s_title, l_title):
                if SequenceMatcher(None, s_title, l_title).ratio() >= 0.84:
                    return True

    if same_slot_and_duration:
        s_no_by = re.sub(r"\s+by\s+.+$", "", s_raw, flags=re.IGNORECASE).strip()
        s_no_paren = re.sub(r"[\(（\[【][^\)）\]】]*[\)）\]】]", "", s_no_by).strip()
        s_variants = [TrackManager.normalize_title(s_no_paren)]
        if " - " in s_no_paren:
            after_sep = s_no_paren.split(" - ", 1)[1].strip()
            if after_sep:
                s_variants.append(TrackManager.normalize_title(after_sep))

        steam_has_duplicates = False
        if full_ref_steam:
            norm_s_main = TrackManager.normalize_title(s_no_paren)
            dup_count = sum(
                1
                for st in full_ref_steam
                if TrackManager.normalize_title(
                    re.sub(r"[\(（\[【][^\)）\]】]*[\)）\]】]", "", str(st.get("t") or st.get("title") or ""))
                ) == norm_s_main
            )
            steam_has_duplicates = dup_count > 1

        for key in ("title", "norm_stem"):
            l_raw_val = str(local_track.get(key) or "")
            if not l_raw_val:
                continue
            l_no_paren = re.sub(r"[\(（\[【][^\)）\]】]*[\)）\]】]", "", l_raw_val).strip()
            l_norm = TrackManager.normalize_title(l_no_paren)
            if not l_norm:
                continue

            for s_var in filter(None, s_variants):
                if steam_has_duplicates:
                    m_suffix = re.match(rf"^{re.escape(s_var)}\s+(\d{{1,2}})$", l_norm)
                    if m_suffix:
                        return True
                    l_norm_fixed = l_norm.replace("artifical", "artificial")
                    if re.match(rf"^{re.escape(s_var)}\s+(\d{{1,2}})$", l_norm_fixed):
                        return True
                    if SequenceMatcher(None, s_var, re.sub(r"\s+\d+$", "", l_norm)).ratio() >= 0.88:
                        return True

                if not _has_conflicting_numbers_or_qualifiers(l_norm, s_var):
                    if (
                        s_var == l_norm
                        or s_var.replace(" ", "") == l_norm.replace(" ", "")
                        or f" {s_var} " in f" {l_norm} "
                        or f" {l_norm} " in f" {s_var} "
                        or SequenceMatcher(None, s_var, l_norm).ratio() >= 0.84
                    ):
                        return True

    return False


def _find_matching_steam_slot(
    track: Dict[str, Any],
    target_slot_num: str,
    disc_val: int,
    steam_by_disc_and_track: Dict[tuple[int, str], Dict[str, Any]],
    steam_slots_by_num: Dict[str, List[Dict[str, Any]]],
    exact_owner_v_indices: Optional[set[int]] = None,
    full_ref_steam: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    slot_list = steam_slots_by_num.get(str(target_slot_num), [])

    # Step 0: (disc_val, target_slot_num) で厳密一致する場合は最優先
    slot_a = steam_by_disc_and_track.get((disc_val, str(target_slot_num)))
    if slot_a and _exact_title_match(track, slot_a):
        return slot_a

    # Step 0b: 該当トラック番号のスロットのうち厳密タイトル一致が唯一存在する場合
    exact_candidates = [s for s in slot_list if _exact_title_match(track, s)]
    if len(exact_candidates) == 1:
        return exact_candidates[0]

    # Step A: (disc_val, target_slot_num) で存在し、タイトル整合する場合
    if slot_a and _titles_match(track, slot_a, full_ref_steam=full_ref_steam):
        v_idx = slot_a.get("v_idx")
        if not exact_owner_v_indices or v_idx not in exact_owner_v_indices:
            return slot_a

    # Step B: 該当トラック番号のスロットのうちタイトル整合するスロットがただ1つ存在する場合
    candidates = [
        s for s in slot_list
        if _titles_match(track, s, full_ref_steam=full_ref_steam)
        and (
            not exact_owner_v_indices
            or s.get("v_idx") not in exact_owner_v_indices
            or _exact_title_match(track, s)
        )
    ]
    if len(candidates) == 1:
        return candidates[0]

    # Step C: マルチディスクにおけるグローバル通し連番（v_idx = int(target_slot_num) - 1）照合
    # (disc_val == 1 かつ Steam の該当スロットが Disc 2 以降、タイトル一致＋再生時間差 <= 3.0s)
    if full_ref_steam and str(target_slot_num).isdigit() and int(disc_val) == 1:
        global_idx = int(target_slot_num) - 1
        if 0 <= global_idx < len(full_ref_steam):
            global_slot = full_ref_steam[global_idx]
            slot_disc = int(global_slot.get("d") or global_slot.get("disc") or 1)
            if slot_disc > 1 and _titles_match(track, global_slot):
                t_dur = (
                    float(track.get("duration_ms") or 0) / 1000.0
                    if track.get("duration_ms")
                    else float(track.get("dur") or 0)
                )
                s_dur = float(
                    global_slot.get("dur") or global_slot.get("duration_s") or 0
                )
                if t_dur > 0 and s_dur > 0:
                    if abs(t_dur - s_dur) <= 3.0:
                        return global_slot
                else:
                    return global_slot

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

    # 厳密一致オーナーの事前計算（部分一致による横取り防止）
    exact_owner_v_indices: set[int] = set()
    for track in local_tracks:
        t_num = track.get("track_num") or track.get("filename_track")
        d_val = int(track.get("disc") or 1)
        if t_num is not None:
            slot_exact = steam_by_disc_and_track.get((d_val, str(t_num)))
            if slot_exact and _exact_title_match(track, slot_exact):
                if slot_exact.get("v_idx") is not None:
                    exact_owner_v_indices.add(int(slot_exact["v_idx"]))
        else:
            matching_slots = [s for s in full_ref_steam if _exact_title_match(track, s)]
            if len(matching_slots) == 1 and matching_slots[0].get("v_idx") is not None:
                exact_owner_v_indices.add(int(matching_slots[0]["v_idx"]))

    for track in local_tracks:
        file_ids = [str(fid) for fid in track.get("file_ids", [])]
        track_num = track.get("track_num") or track.get("filename_track")
        disc_val = int(track.get("disc") or 1)

        # AcoustID/MBZ_RELEASE からのシグナル解決
        fp_candidate = None
        if track.get("v_idx") is not None and track.get("v_idx") in fingerprint_by_v_idx:
            fp_candidate = fingerprint_by_v_idx[track["v_idx"]]
        elif track_num is not None:
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
                target_slot_num = str(fp_candidate.get("n"))
                fp_disc = int(fp_candidate.get("d") or fp_candidate.get("disc") or disc_val)
                steam_slot = _find_matching_steam_slot(
                    track,
                    target_slot_num,
                    fp_disc,
                    steam_by_disc_and_track,
                    steam_slots_by_num,
                    exact_owner_v_indices,
                    full_ref_steam=full_ref_steam,
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
                    track,
                    target_slot_num,
                    ms_disc,
                    steam_by_disc_and_track,
                    steam_slots_by_num,
                    exact_owner_v_indices,
                    full_ref_steam=full_ref_steam,
                )
                if steam_slot:
                    slot_n = steam_slot.get("n", target_slot_num)
                    res.mbz_search_steam_slot = int(slot_n) if str(slot_n).isdigit() else None
                    if res.target_v_idx is None:
                        res.target_v_idx = steam_slot.get("v_idx")
                    res.evidence.append("mbz_search_match")

            # 確定的一致（Deterministic 1:1 match）の判定
            det_slot = None
            target_v = None
            if res.acoustid_steam_slot is not None:
                det_slot = res.acoustid_steam_slot
                target_v = res.target_v_idx
                res.evidence.append("deterministic_acoustid")
            elif track_num is not None:
                steam_slot = _find_matching_steam_slot(
                    track,
                    str(track_num),
                    disc_val,
                    steam_by_disc_and_track,
                    steam_slots_by_num,
                    exact_owner_v_indices,
                    full_ref_steam=full_ref_steam,
                )
                if steam_slot:
                    slot_n = steam_slot.get("n", track_num)
                    det_slot = int(slot_n) if str(slot_n).isdigit() else None
                    target_v = steam_slot.get("v_idx")
                    res.evidence.append("deterministic_number_and_title")
                else:
                    # 指示書 04 3.1-2: 番号一致スロット不成立時のアルバム全体1対1厳密タイトル＋尺一致フォールバック
                    same_disc_slots = [
                        s for s in full_ref_steam if int(s.get("d", 1) or 1) == disc_val
                    ]
                    exact_candidates = [
                        s for s in same_disc_slots if _exact_title_match(track, s)
                    ]
                    if not exact_candidates:
                        exact_candidates = [
                            s for s in full_ref_steam if _exact_title_match(track, s)
                        ]

                    # 括弧部分を除去したコアタイトル検索 (AppID 4206020 型)
                    if not exact_candidates:
                        l_raw = str(track.get("title") or track.get("t") or "")
                        local_key = track.get("local_key")
                        lk_raw = (
                            str(local_key[1]).strip()
                            if (isinstance(local_key, (tuple, list)) and len(local_key) >= 2)
                            else ""
                        )
                        core_candidates = []
                        for raw_t in filter(None, [l_raw, lk_raw]):
                            no_bracket = re.sub(
                                r"[\(（\[【][^\)）\]】]*[\)）\]】]", "", raw_t
                            ).strip()
                            if no_bracket:
                                norm_core = TrackManager.normalize_title(no_bracket)
                                if norm_core:
                                    core_candidates.append(norm_core)

                        if core_candidates:
                            exact_candidates = [
                                s
                                for s in (same_disc_slots or full_ref_steam)
                                if any(
                                    TrackManager.normalize_title(
                                        str(s.get("t") or s.get("title") or "")
                                    )
                                    == core_t
                                    for core_t in core_candidates
                                )
                            ]

                    if len(exact_candidates) == 1:
                        cand_slot = exact_candidates[0]
                        l_dur = (
                            float(track.get("duration_ms") or 0) / 1000.0
                            if track.get("duration_ms")
                            else float(track.get("dur") or 0)
                        )
                        s_dur = float(
                            cand_slot.get("dur") or cand_slot.get("duration_s") or 0
                        )
                        dur_ok = True
                        if l_dur > 0 and s_dur > 0:
                            dur_ok = abs(l_dur - s_dur) <= 3.0

                        cand_d = int(cand_slot.get("d", 1) or 1)
                        cand_n = str(cand_slot.get("n", ""))
                        conflict = False
                        for other in local_tracks:
                            if other is track:
                                continue
                            o_d = int(other.get("disc") or 1)
                            o_n = str(
                                other.get("track_num")
                                or other.get("filename_track")
                                or ""
                            )
                            if o_d == cand_d and o_n == cand_n and _titles_match(other, cand_slot):
                                conflict = True
                                break

                        if dur_ok and not conflict:
                            slot_n = cand_slot.get("n")
                            det_slot = (
                                int(slot_n)
                                if slot_n is not None and str(slot_n).isdigit()
                                else None
                            )
                            target_v = cand_slot.get("v_idx")
                            res.evidence.append("deterministic_exact_title_offset")
            else:
                # トラック番号欠損時の厳密タイトル一意照合フォールバック
                exact_slots = [s for s in full_ref_steam if _exact_title_match(track, s)]
                if len(exact_slots) == 1:
                    steam_slot = exact_slots[0]
                    slot_n = steam_slot.get("n")
                    if slot_n is None and steam_slot.get("v_idx") is not None:
                        slot_n = int(steam_slot["v_idx"]) + 1
                    det_slot = int(slot_n) if slot_n is not None and str(slot_n).isdigit() else None
                    target_v = steam_slot.get("v_idx")
                    res.evidence.append("deterministic_exact_title_unnumbered")

            if det_slot is not None:
                res.deterministic_steam_slot = det_slot
                res.target_v_idx = target_v
                res.is_deterministic = True
                if res.override_track is None:
                    res.override_track = str(det_slot)

            prematch_map[file_id] = res

    return prematch_map


def _are_coherent_slot_variants(
    track_indices: set[int],
    local_tracks: List[Dict[str, Any]],
    steam_slot: Dict[str, Any],
    full_ref_steam: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    tracks = [local_tracks[idx] for idx in track_indices]
    durations = [
        int(t["duration_ms"])
        for t in tracks
        if t.get("duration_ms") is not None and int(t["duration_ms"]) > 0
    ]
    if len(durations) >= 2 and (max(durations) - min(durations)) > 3000:
        return False

    same_numbers = all(
        (t.get("track_num") or t.get("filename_track")) is not None
        and (t.get("track_num") or t.get("filename_track"))
        == (tracks[0].get("track_num") or tracks[0].get("filename_track"))
        for t in tracks
    )
    if same_numbers and (len(durations) < 2 or max(durations) - min(durations) <= 2000):
        stems = [
            TrackManager.normalize_title(
                str(t.get("norm_stem") or t.get("title") or "")
            )
            for t in tracks
        ]
        if all(
            stems[0] == s or SequenceMatcher(None, stems[0], s).ratio() >= 0.88
            for s in stems
        ):
            return True

    return all(
        _titles_match(t, steam_slot, full_ref_steam=full_ref_steam) for t in tracks
    )


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

    # 1b. 指示書 05 3.1-1: 同一 (disc, track_num)・同一 norm_stem・同一尺のフォーマットバリアントに対するプレマッチ伝播
    for u_idx, u_track in enumerate(local_tracks):
        u_fids = [str(fid) for fid in u_track.get("file_ids", [])]
        if any(fid in {c[0] for cands in v_idx_to_candidates.values() for c in cands} for fid in u_fids):
            continue
        u_d = u_track.get("disc") or 1
        u_n = u_track.get("track_num") or u_track.get("filename_track")
        u_dur = (
            float(u_track.get("duration_ms") or 0) / 1000.0
            if u_track.get("duration_ms")
            else float(u_track.get("dur") or 0)
        )
        u_stem = TrackManager.normalize_title(
            str(u_track.get("norm_stem") or u_track.get("title") or "")
        )

        if u_n is None:
            continue

        for matched_v_idx, candidates in list(v_idx_to_candidates.items()):
            found_sibling = False
            for m_fid, m_pm, m_idx in list(candidates):
                m_track = local_tracks[m_idx]
                m_d = m_track.get("disc") or 1
                m_n = m_track.get("track_num") or m_track.get("filename_track")
                m_dur = (
                    float(m_track.get("duration_ms") or 0) / 1000.0
                    if m_track.get("duration_ms")
                    else float(m_track.get("dur") or 0)
                )
                m_stem = TrackManager.normalize_title(
                    str(m_track.get("norm_stem") or m_track.get("title") or "")
                )

                if m_n is not None and str(u_d) == str(m_d) and str(u_n) == str(m_n):
                    dur_ok = True
                    if u_dur > 0 and m_dur > 0:
                        dur_ok = abs(u_dur - m_dur) <= 2.0
                    stem_ok = (
                        u_stem == m_stem
                        or SequenceMatcher(None, u_stem, m_stem).ratio() >= 0.88
                    )
                    if dur_ok and stem_ok:
                        for u_fid in u_fids:
                            v_idx_to_candidates[matched_v_idx].append((u_fid, m_pm, u_idx))
                        found_sibling = True
                        break
            if found_sibling:
                break

    # 2. 同一 v_idx への異タイトル多重確定の防止（衝突検出）
    # 指示書 06 3.3: 同一拡張子・ファイル名乖離（別スロットタイトル完全一致）重複ファイルの除外
    for matched_v_idx, candidates in list(v_idx_to_candidates.items()):
        distinct_track_indices = {c[2] for c in candidates}
        if len(distinct_track_indices) > 1:
            steam_slot = full_ref_steam[matched_v_idx]
            steam_slot_norm = TrackManager.normalize_title(str(steam_slot.get("t") or steam_slot.get("title") or ""))
            other_steam_norms = {
                TrackManager.normalize_title(str(s.get("t") or s.get("title") or ""))
                for s in full_ref_steam
                if s.get("v_idx") != matched_v_idx
            }
            other_steam_norms.discard("")

            ext_to_indices: Dict[str, List[int]] = defaultdict(list)
            for idx in distinct_track_indices:
                t = local_tracks[idx]
                ext = str(t.get("ext") or "").lower()
                ext_to_indices[ext].append(idx)

            bad_indices: set[int] = set()
            for ext, idx_list in ext_to_indices.items():
                if len(idx_list) > 1:
                    for idx in idx_list:
                        t = local_tracks[idx]
                        raw_stem = ""
                        if isinstance(t.get("local_key"), (tuple, list)) and len(t["local_key"]) > 1:
                            raw_stem = str(t["local_key"][1]).split("::")[0]
                        if not raw_stem:
                            raw_stem = str(t.get("title") or t.get("norm_stem") or "")

                        stems_to_test = set()
                        stems_to_test.add(TrackManager.normalize_title(raw_stem))
                        stems_to_test.add(TrackManager.normalize_title(str(t.get("norm_stem") or "")))
                        if " - " in raw_stem:
                            parts = raw_stem.split(" - ")
                            for p in parts:
                                stems_to_test.add(TrackManager.normalize_title(p))
                            stems_to_test.add(TrackManager.normalize_title(parts[-1]))
                        no_num = re.sub(r"^\d{1,3}(?:[\s._-]+)", "", raw_stem).strip()
                        if no_num:
                            stems_to_test.add(TrackManager.normalize_title(no_num))
                            if " - " in no_num:
                                stems_to_test.add(TrackManager.normalize_title(no_num.split(" - ", 1)[1]))
                        stems_to_test.discard("")

                        matches_self = any(s == steam_slot_norm or steam_slot_norm in s for s in stems_to_test)
                        matches_other = any(s in other_steam_norms for s in stems_to_test)
                        if not matches_self and matches_other:
                            bad_indices.add(idx)

            if bad_indices:
                v_idx_to_candidates[matched_v_idx] = [
                    c for c in candidates if c[2] not in bad_indices
                ]
                logger.warning(
                    f"決定論的プレマッチ異常ファイル除外: v_idx={matched_v_idx} から別スロットタイトルと一致する異名ファイル {bad_indices} を除外しました。"
                )

    colliding_v_indices: set[int] = set()
    for matched_v_idx, candidates in v_idx_to_candidates.items():
        distinct_track_indices = {c[2] for c in candidates}
        if len(distinct_track_indices) > 1:
            steam_slot = full_ref_steam[matched_v_idx]
            norm_titles = {
                TrackManager.normalize_title(
                    str(local_tracks[idx].get("title") or local_tracks[idx].get("norm_stem") or "")
                )
                for idx in distinct_track_indices
            }
            if len(norm_titles) > 1 and not _are_coherent_slot_variants(
                distinct_track_indices, local_tracks, steam_slot, full_ref_steam=full_ref_steam
            ):
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
