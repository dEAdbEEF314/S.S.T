import re
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from .ident.embedded import EmbeddedMetadataExtractor

logger = logging.getLogger("sst.track_grouper")

class TrackManager:
    @staticmethod
    def list_audio_files(directory: Path) -> List[Path]:
        exts = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".aiff", ".aif"}
        return [p for p in directory.rglob("*") if p.suffix.lower() in exts and not p.name.startswith(".") and "__MACOSX" not in p.parts]

    @staticmethod
    def get_duration(path: Path) -> float:
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
            return float(subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip())
        except Exception: return 0.0

    @staticmethod
    def group_by_logical_track(files: List[Path], album_name: Optional[str] = None) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        from difflib import SequenceMatcher
        
        raw_tracks = []
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            t_num = re.match(r'^(\d+)', f.stem)
            disc = 1
            if meta.get("disc_number"):
                try:
                    d_str = str(meta.get("disc_number")).split('/')[0]
                    if d_str.isdigit(): disc = int(d_str)
                except Exception: pass
            
            # Fallback to directory name if disc is still 1
            if disc == 1:
                # Look for "disc N" or "CD N" in path parts (reversed to find the innermost one)
                for part in reversed(f.parts):
                    d_match = re.search(r'(?:disc|cd)\s*(\d+)', part, re.IGNORECASE)
                    if d_match:
                        disc = int(d_match.group(1))
                        break

            stem = f.stem
            # Remove album name if present (case-insensitive)
            if album_name:
                # Escape album name for regex and remove it
                escaped_album = re.escape(album_name)
                stem = re.sub(escaped_album, '', stem, flags=re.IGNORECASE)
                # Also try removing common variations (e.g. without "Soundtrack")
                short_album = re.sub(r'\s*(Soundtrack|Original Soundtrack|OST)\s*$', '', album_name, flags=re.IGNORECASE)
                if short_album and short_album != album_name:
                    stem = re.sub(re.escape(short_album), '', stem, flags=re.IGNORECASE)

            stem = re.sub(r'^(\d+[\s._-]+)+', '', stem)
            
            # --- Smart Normalization (Improved) ---
            # 1. Remove obvious noise (extensions, quality, etc.) with word boundaries
            noise_pattern = r'\b(aiff|mp3|flac|wav|lossless|high-res|digital|official)\b'
            stem = re.sub(noise_pattern, '', stem, flags=re.IGNORECASE)
            
            # 2. Remove soundtrack-related noise only at the end
            stem = re.sub(r'\b(ost|soundtrack|original soundtrack)\b$', '', stem.strip(), flags=re.IGNORECASE)

            # 3. Handle symbols: replace with space but keep alphanumeric content
            stem = re.sub(r'[^a-zA-Z0-9]', ' ', stem)
            
            # 4. Collapse whitespace and lowercase
            stem = " ".join(stem.split()).lower()
            stem = stem.replace("artifical", "artificial")
            stem = re.sub(r'\s*0+(\d+)', r' \1', stem)
            norm_stem = stem.strip()
            
            t_num_val = None
            if t_num:
                t_num_val = t_num.group(1).lstrip('0') or '0'
            elif meta.get("track_number"):
                try:
                    t_str = str(meta.get("track_number")).split('/')[0].strip()
                    if t_str.isdigit():
                        t_num_val = str(int(t_str))
                except Exception:
                    pass
            
            raw_tracks.append({
                "path": f, "meta": meta, "duration": TrackManager.get_duration(f), 
                "format": f.suffix.lower().lstrip('.'),
                "filename_track": int(t_num.group(1)) if t_num else None,
                "t_num_val": t_num_val,
                "norm_stem": norm_stem,
                "disc": disc
            })

        groups: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
        
        for track in raw_tracks:
            matched = False
            for (g_disc, g_norm_stem), variants in groups.items():
                if track["disc"] != g_disc:
                    continue
                
                # Hybrid matching criteria
                duration_diff = abs(track["duration"] - variants[0]["duration"])
                is_duration_match = duration_diff < 1.0
                
                # 1. Exact stem match
                if track["norm_stem"] == g_norm_stem:
                    variants.append(track)
                    matched = True
                    break
                
                # 2. Track number + Duration match
                if track["t_num_val"] and track["t_num_val"] == variants[0]["t_num_val"] and is_duration_match:
                    variants.append(track)
                    matched = True
                    break
                
                # 3. Fuzzy match + Duration match
                similarity = SequenceMatcher(None, track["norm_stem"], g_norm_stem).ratio()
                if similarity >= 0.85 and is_duration_match:
                    variants.append(track)
                    matched = True
                    break
            
            if not matched:
                groups[(track["disc"], track["norm_stem"])] = [track]

        # Post-process: Split groups that have different track numbers but same stem
        priorities = TrackManager.get_audio_format_priority()
        def sort_key(v):
            fmt = v["format"].lower()
            try:
                return priorities.index(fmt)
            except ValueError:
                return 999

        final_groups = {}
        for (disc, norm_stem), variants in groups.items():
            sorted_variants = sorted(variants, key=sort_key)
            t_nums = {v["t_num_val"] for v in sorted_variants if v["t_num_val"] is not None}
            if len(t_nums) <= 1:
                final_groups[(disc, norm_stem)] = sorted_variants
            else:
                for v in sorted_variants:
                    final_track_id = f"{norm_stem} {v['t_num_val']}" if v["t_num_val"] else f"{norm_stem} unnum {sorted_variants.index(v)}"
                    final_groups[(disc, final_track_id)] = [v]
                    
        return final_groups

    @staticmethod
    def get_audio_format_priority() -> List[str]:
        import os
        priority_str = os.getenv("AUDIO_FORMAT_PRIORITY", "flac,alac,aiff,wav,mp3,m4a,ogg")
        return [fmt.strip().lower() for fmt in priority_str.split(",") if fmt.strip()]

    @staticmethod
    def adopt_optimal_files(track_groups: Dict) -> Dict:
        adopted = {}
        for key, variants in track_groups.items():
            # variants はすでに group_by_logical_track 側でソートされているため、
            # 先頭のファイルが最優先フォーマットとなる
            chosen = variants[0]
            
            is_lossless = chosen["format"] in ["flac", "wav", "aiff", "alac", "aif"]
            adopted[key] = {
                "path": chosen["path"],
                "tier": "lossless" if is_lossless else ("lossy" if chosen["format"] != "mp3" else "mp3"),
                "filename_track": chosen["filename_track"]
            }
        return adopted

    @staticmethod
    def get_best_artwork(variants: List[Dict]) -> Optional[bytes]:
        from mutagen import File
        for v in variants:
            try:
                audio = File(v["path"])
                if audio and audio.tags:
                    if v["format"] in ["mp3", "aiff"]:
                        for tag in audio.tags.values():
                            if hasattr(tag, 'data') and getattr(tag, 'FrameID', None) == "APIC": return tag.data
                    elif v["format"] == "flac" and audio.pictures: return audio.pictures[0].data
            except Exception: continue
        return None

    @staticmethod
    def extract_local_baseline(track_groups: Dict, acoustid_evidence: Optional[Dict] = None) -> Dict[str, Any]:
        from collections import Counter
        albums, artists, years, track_data = [], [], [], []
        for (disc, title), variants in track_groups.items():
            t_name = None
            avg_dur = sum(v["duration"] for v in variants) / len(variants) if variants else 0
            
            # 1. Use AcoustID evidence if available (High Trust)
            if acoustid_evidence and (disc, title) in acoustid_evidence:
                evidence = acoustid_evidence[(disc, title)]
                t_name = evidence.get("title")
                logger.debug(f"Using AcoustID-provided title for track {(disc, title)}: {t_name}")
                if evidence.get("artist"):
                    artists.append(evidence["artist"])
            
            # 2. Use embedded metadata if AcoustID failed or was not available
            if not t_name:
                for v in variants:
                    if v["meta"]:
                        if v["meta"].get("album"): albums.append(v["meta"]["album"])
                        if v["meta"].get("artist"): artists.append(v["meta"]["artist"])
                        if v["meta"].get("year"): years.append(str(v["meta"]["year"]))
                        if not t_name and v["meta"].get("title"): t_name = v["meta"]["title"]
            
            # 3. Fallback to filename
            if not t_name and variants:
                t_name = variants[0]["path"].stem
                t_name = re.sub(r'^(\d+[\s.-]+)+', '', t_name).strip()
            
            if t_name:
                track_data.append((t_name, int(avg_dur * 1000)))
        
        def most_common(lst): return Counter(lst).most_common(1)[0][0] if lst else None
        return {"album": most_common(albums), "artist": most_common(artists), "year": most_common(years), "tracks": track_data}

    @staticmethod
    def prepare_llm_track_context(track_groups: Dict) -> Dict[str, List[Dict[str, Any]]]:
        context = {}
        for (disc, clean_title), variants in track_groups.items():
            merged_tags = {}
            for v in variants:
                if v["meta"]:
                    for k, val in v["meta"].items():
                        if val and str(val).lower() not in ["", "none", "unknown", "0"] and k not in merged_tags: merged_tags[k] = val
            tid = f"{disc}_{clean_title}"
            sources = [{"type": "filename", "content": variants[0]["path"].name, "inferred_track_num": variants[0].get("filename_track"), "duration": round(sum(v["duration"] for v in variants)/len(variants), 2), "weight": "weak"}]
            if merged_tags: sources.append({"type": "embedded_merged", "tags": merged_tags, "duration": sources[0]["duration"], "weight": "strong" if len(variants) > 1 else "moderate"})
            else: sources.append({"type": "no_tags_found", "content": "No metadata found", "weight": "critical_missing"})
            context[tid] = sources
        return context
