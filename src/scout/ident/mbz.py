import musicbrainzngs
import logging
import re
import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from difflib import SequenceMatcher

logger = logging.getLogger("scout.ident.mbz")

class MusicBrainzIdentifier:
    def __init__(self, app_name: str, version: str, contact: str, scoring_config: Optional[Dict[str, Any]] = None):
        musicbrainzngs.set_useragent(app_name, version, contact)
        self.scores = scoring_config or {
            "direct_steam_link": 500,
            "parent_steam_link": 300,
            "direct_steamdb_link": 500,
            "parent_steamdb_link": 300,
            "bandcamp_link": 100,
            "title_similarity_max": 100,
            "track_count_match": 50,
            "track_count_penalty_per_track": 20,
            "track_count_penalty_max": 300,
            "digital_format": 30,
            "date_match": 20,
            "date_penalty_per_year": 20,
            "date_penalty_max": 100,
            "fingerprint_match": 200,
            "direct_recording_match": 1000
        }

    def _safe_year(self, date_str: Any) -> Optional[int]:
        """Safely extracts a 4-digit year from any string."""
        if not date_str: return None
        match = re.search(r'(\d{4})', str(date_str))
        return int(match.group(1)) if match else None

    def get_release_details(self, mbid: str) -> Optional[Dict[str, Any]]:
        """
        Fetches full details for a release, including relationships and tracks.
        """
        try:
            time.sleep(1.1)
            include = [
                "url-rels", "recordings", "artist-credits", "discids", "labels",
                "recording-level-rels", "work-level-rels", "artist-rels", "tags"
            ]
            res = musicbrainzngs.get_release_by_id(mbid, includes=include)
            return res.get('release', {})
        except Exception as e:
            logger.warning(f"Failed to fetch release details for {mbid}: {e}")
            return None

    def fuzzy_match_album(self, local_tracks: List[Tuple[str, float]], mb_tracks: List[Tuple[str, float]], time_threshold_ms: int = 2000) -> float:
        """
        Calculates a set similarity score between local and MB tracks based on name and duration.
        """
        if not local_tracks or not mb_tracks: return 0.0
        
        matched_count = 0
        used_mb_indices = set()
        
        for l_name, l_dur in local_tracks:
            best_match_idx = -1
            best_sim = 0.0
            
            for m_idx, (m_name, m_dur) in enumerate(mb_tracks):
                if m_idx in used_mb_indices: continue
                
                time_match = True
                if l_dur and m_dur:
                    time_match = abs(l_dur - m_dur) < time_threshold_ms
                
                if time_match:
                    name_sim = SequenceMatcher(None, l_name.lower(), m_name.lower()).ratio()
                    if name_sim > 0.8 and name_sim > best_sim:
                        best_sim = name_sim
                        best_match_idx = m_idx
            
            if best_match_idx != -1:
                matched_count += 1
                used_mb_indices.add(best_match_idx)
        
        return matched_count / max(len(local_tracks), len(mb_tracks))

    def search_release(
        self, 
        album_name: str, 
        expected_track_count: int, 
        app_id: Optional[int] = None, 
        parent_app_id: Optional[int] = None,
        year: Optional[str] = None,
        local_baseline: Optional[Dict[str, Any]] = None,
        acoustid_mbids: Optional[List[str]] = None,
        acoustid_release_ids: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Searches MusicBrainz and returns ranked candidates using the NWO Hybrid Scoring System.
        """
        log_data = {
            "query": {"album_name": album_name, "app_id": app_id, "expected_track_count": expected_track_count},
            "timestamp": datetime.utcnow().isoformat(),
            "attempts": []
        }
        
        all_raw_releases = []
        try:
            time.sleep(1.1)
            # 1. Primary: Text-based search
            result = musicbrainzngs.search_releases(release=album_name, limit=20)
            all_raw_releases = result.get('release-list', [])
            log_data["attempts"].append({"query": album_name, "count": len(all_raw_releases)})
        except Exception as e:
            logger.error(f"MBZ search error: {e}")

        # 2. Secondary: Ensure AcoustID-suggested Release IDs are evaluated
        if acoustid_release_ids:
            current_ids = {r['id'] for r in all_raw_releases}
            for rid in acoustid_release_ids:
                if rid not in current_ids:
                    try:
                        time.sleep(1.1)
                        res = musicbrainzngs.get_release_by_id(rid)
                        if res.get('release'):
                            all_raw_releases.append(res['release'])
                            log_data["attempts"].append({"query": f"AcoustID Release {rid}", "count": 1})
                    except Exception: pass

        # 3. Tertiary: Fallback to recording-based search if still empty
        if not all_raw_releases and acoustid_mbids:
            try:
                time.sleep(1.1)
                rec_res = musicbrainzngs.get_recording_by_id(acoustid_mbids[0], includes=["releases"])
                all_raw_releases = rec_res.get("recording", {}).get("release-list", [])
                log_data["attempts"].append({"query": f"AcoustID Recording {acoustid_mbids[0]}", "count": len(all_raw_releases)})
            except Exception: pass

        if not all_raw_releases:
            return [], log_data

        scored_candidates = []
        logger.debug(f"Evaluating {len(all_raw_releases)} MBZ release candidates...")
        for i, r in enumerate(all_raw_releases):
            mbid = r['id']
            title_text = r.get('title', 'Unknown Title')
            logger.debug(f"[{i+1}/{len(all_raw_releases)}] Fetching details for MBZ Release: {title_text} ({mbid})...")
            try:
                time.sleep(1.1)
                full_r = musicbrainzngs.get_release_by_id(mbid, includes=["url-rels", "recordings", "artist-credits", "labels"])
                release_data = full_r.get('release', {})
            except Exception as e:
                logger.warning(f"Failed to fetch details for {mbid}: {e}")
                continue

            score = 0
            evidence_notes = []

            # --- Tier 0: AcoustID Correlation (Release Match) ---
            if acoustid_release_ids and mbid in acoustid_release_ids:
                boost = self.scores.get("acoustid_release_match", 1000)
                score += boost
                evidence_notes.append("ACOUSTID_RELEASE_MATCH")

            # --- Tier 0.5: AcoustID Correlation (Recording Match) ---
            if acoustid_mbids:
                mb_rec_ids = []
                for m in release_data.get('medium-list', []):
                    for t in m.get('track-list', []):
                        rid = t.get('recording', {}).get('id')
                        if rid: mb_rec_ids.append(rid)
                
                intersection = set(acoustid_mbids) & set(mb_rec_ids)
                if intersection:
                    boost = self.scores.get("direct_recording_match", 1000)
                    score += boost
                    evidence_notes.append(f"ACOUSTID_MATCH({len(intersection)} tracks)")
            # --- Tier 1: Deterministic ---
            seen_evidence = set()
            relations = release_data.get('url-relation-list', [])
            for rel in relations:
                url = rel.get('target', '')
                
                # 1. Direct Steam Link
                if app_id and f"store.steampowered.com/app/{app_id}" in url:
                    if "DIRECT_STEAM_LINK" not in seen_evidence:
                        score += self.scores.get("direct_steam_link", 500)
                        evidence_notes.append('DIRECT_STEAM_LINK')
                        seen_evidence.add("DIRECT_STEAM_LINK")
                
                # 2. Parent Steam Link
                elif parent_app_id and f"store.steampowered.com/app/{parent_app_id}" in url:
                    if "PARENT_STEAM_LINK" not in seen_evidence:
                        score += self.scores.get("parent_steam_link", 300)
                        evidence_notes.append('PARENT_STEAM_LINK')
                        seen_evidence.add("PARENT_STEAM_LINK")
                
                # 3. Direct SteamDB Link
                if app_id and f"steamdb.info/app/{app_id}" in url:
                    if "DIRECT_STEAMDB_LINK" not in seen_evidence:
                        score += self.scores.get("direct_steamdb_link", 500)
                        evidence_notes.append('DIRECT_STEAMDB_LINK')
                        seen_evidence.add("DIRECT_STEAMDB_LINK")
                
                # 4. Parent SteamDB Link
                elif parent_app_id and f"steamdb.info/app/{parent_app_id}" in url:
                    if "PARENT_STEAMDB_LINK" not in seen_evidence:
                        score += self.scores.get("parent_steamdb_link", 300)
                        evidence_notes.append('PARENT_STEAMDB_LINK')
                        seen_evidence.add("PARENT_STEAMDB_LINK")

                # Bandcamp
                if "bandcamp.com" in url:
                    if "BANDCAMP_LINK" not in seen_evidence:
                        score += self.scores.get("bandcamp_link", 100)
                        evidence_notes.append('BANDCAMP_LINK')
                        seen_evidence.add("BANDCAMP_LINK")

            # --- Tier 2: Structural ---
            mb_tracks = 0
            try:
                for m in release_data.get('medium-list', []):
                    mb_tracks += len(m.get('track-list', []))
                
                # Publisher/Label Alignment (New Steam Anchor)
                mb_labels = []
                canonical_label = "Unknown"
                for l_entry in release_data.get('label-info-list', []):
                    lname = l_entry.get('label', {}).get('name')
                    if lname:
                        mb_labels.append(lname.lower())
                        if canonical_label == "Unknown": canonical_label = lname
            except Exception: pass
            
            # Steam Publisher matching
            if local_baseline and local_baseline.get("publisher"):
                pub = local_baseline["publisher"].lower()
                if any(pub in lbl or lbl in pub for lbl in mb_labels):
                    boost = self.scores.get("publisher_label_match", 100)
                    score += boost
                    evidence_notes.append('PUBLISHER_LABEL_MATCH')

            if mb_tracks == expected_track_count:
                score += self.scores.get("track_count_match", 50)
                evidence_notes.append("TRACK_COUNT_MATCH")
            elif mb_tracks > 0:
                diff = abs(mb_tracks - expected_track_count)
                # Stronger penalty for mismatch to prevent false positives in "data void" areas
                penalty = min(self.scores.get("track_count_penalty_max", 300), diff * self.scores.get("track_count_penalty_per_track", 20))
                score -= penalty
                evidence_notes.append(f"TRACK_COUNT_DIFF(-{penalty})")

            # --- Tier 3: Corroborative ---
            is_digital = any(m.get('format') == 'Digital Media' for m in release_data.get('medium-list', []))
            if is_digital:
                score += self.scores.get("digital_format", 30)
                evidence_notes.append("DIGITAL_FORMAT")

            # --- Tier 4: Collective (Set Similarity) ---
            set_match_score = 0.0
            if local_baseline and local_baseline.get("tracks"):
                mb_tracks_data = []
                for m in release_data.get('medium-list', []):
                    for t in m.get('track-list', []):
                        t_name = t.get('recording', {}).get('title') or t.get('title', 'Unknown')
                        try:
                            t_len = int(t.get('length') or t.get('recording', {}).get('length') or 0)
                        except Exception: t_len = 0
                        mb_tracks_data.append((t_name, t_len))
                
                # local_baseline["tracks"] now contains (name, duration_ms) tuples
                local_tracks_data = local_baseline.get("tracks", [])
                
                set_match_ratio = self.fuzzy_match_album(local_tracks_data, mb_tracks_data)
                set_match_score = int(set_match_ratio * self.scores.get("fingerprint_match", 200))
                score += set_match_score
                evidence_notes.append(f"SET_SIMILARITY({set_match_score})")

            mb_y = self._safe_year(release_data.get('date'))
            comp_y = self._safe_year(year) or (self._safe_year(local_baseline.get("year")) if local_baseline else None)
            
            if mb_y and comp_y:
                if mb_y == comp_y:
                    score += self.scores.get("date_match", 20)
                    evidence_notes.append("DATE_MATCH")
                else:
                    year_diff = abs(mb_y - comp_y)
                    penalty = min(self.scores.get("date_penalty_max", 100), year_diff * self.scores.get("date_penalty_per_year", 20))
                    score -= penalty
                    evidence_notes.append(f"DATE_MISMATCH(-{penalty})")

            # --- Tracklist Fingerprint ---
            mb_tracks_data = []
            for m in release_data.get('medium-list', []):
                for t in m.get('track-list', []):
                    rec = t.get('recording', {})
                    if rec.get('title'):
                        mb_tracks_data.append({
                            "title": rec['title'],
                            "position": str(t.get('position', '0'))
                        })
            
            if local_baseline and local_baseline.get("tracks") and mb_tracks_data:
                local_tracks = [t[0].lower() for t in local_baseline["tracks"]]
                matches = 0
                for lt in local_tracks:
                    if any(SequenceMatcher(None, lt, mt['title'].lower()).ratio() > 0.85 for mt in mb_tracks_data):
                        matches += 1
                
                # Fair comparison: how much of the MBZ album is matched? (Topic 12)
                # This handles cases where local might have more tracks (duplicates, bonus) than MBZ.
                if len(mb_tracks_data) > 0:
                    match_ratio = matches / len(mb_tracks_data)
                    if match_ratio >= 0.8:
                        score += self.scores.get("fingerprint_match", 200)
                        evidence_notes.append(f"FINGERPRINT_MATCH({int(match_ratio*100)}%)")

            scored_candidates.append({
                "mbid": mbid,
                "mbid_url": f"https://musicbrainz.org/release/{mbid}",
                "score": score,
                "evidence": evidence_notes,
                "album": title_text,
                "artist": release_data.get('artist-credit-phrase'),
                "label": canonical_label,
                "year": str(mb_y) if mb_y else "",
                "track_count": mb_tracks,
                "is_digital": is_digital,
                "tracks": mb_tracks_data
            })

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = scored_candidates[:5]
        log_data["ranked_candidates"] = top_candidates
        return top_candidates, log_data

    def get_release_artwork_url(self, mbid: str) -> Optional[str]:
        try:
            images = musicbrainzngs.get_image_list(mbid)
            for img in images.get('images', []):
                if img.get('front') and img.get('image'): return img.get('image')
        except Exception: pass
        return None
