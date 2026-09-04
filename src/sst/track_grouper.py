import html
import re
import logging
import subprocess
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from .ident.embedded import EmbeddedMetadataExtractor

logger = logging.getLogger("sst.track_grouper")

SPEC_AUDIO_FORMAT_PRIORITY = ("wav", "flac", "alac", "aiff", "aif", "ogg", "aac", "m4a", "mp3")

class TrackManager:
    @staticmethod
    def get_quality_tier(file_format: str) -> int:
        fmt = (file_format or "").lower()
        if fmt == "wav":
            return 0
        if fmt in {"flac", "alac", "aiff", "aif"}:
            return 1
        if fmt in {"ogg", "aac", "m4a"}:
            return 2
        return 3

    @staticmethod
    def list_audio_files(directory: Path) -> List[Path]:
        exts = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".aiff", ".aif"}
        audio_files = []
        try:
            if not directory.exists():
                logger.warning(f"ディレクトリが存在しません: {directory}")
                return []
            for p in directory.rglob("*"):
                try:
                    path_parts = {part.lower() for part in p.parts}
                    if (
                        p.suffix.lower() in exts
                        and not p.name.startswith(".")
                        and not p.name.startswith("._")
                        and ".ds_store" not in path_parts
                        and "__macosx" not in path_parts
                    ):
                        audio_files.append(p)
                except OSError as e:
                    logger.warning(f"ファイルアクセス中にエラーが発生しました ({p}): {e}")
                    continue
        except OSError as e:
            logger.error(f"ディレクトリキャン中にエラーが発生しました ({directory}): {e}")
            return []
        return audio_files

    @staticmethod
    def get_duration(path: Path) -> float:
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
            return float(subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip())
        except Exception: return 0.0

    @staticmethod
    def normalize_title(stem: str) -> str:
        stem = html.unescape(stem or "")
        stem = re.sub(r'^(\d+[\s._-]+)+', '', stem)
        stem = re.sub(r'[\s(\[]+(?:aiff|mp3|flac|wav|lossless|high[\s-]*res|ost|soundtrack|official|[\s\-])+[\s)\]]+$', '', stem, flags=re.IGNORECASE)
        stem = re.sub(r'[^a-zA-Z0-9]', ' ', stem)
        stem = " ".join(stem.split()).lower()
        stem = stem.replace("artifical", "artificial")
        stem = re.sub(r'\s*0+(\d+)', r' \1', stem)
        return stem.strip()

    @staticmethod
    def build_file_records(files: List[Path], album_name: Optional[str] = None) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        raw_tracks = []
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
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

            # Check for multi-disc compound pattern in filename: e.g. "1_1", "1-01", "02_05"
            disc_track_match = re.match(r'^(\d+)[-_](\d+)', f.stem)
            if disc_track_match:
                file_disc = int(disc_track_match.group(1))
                file_track = int(disc_track_match.group(2))
                if disc == 1 and file_disc > 0:
                    disc = file_disc
                filename_track_val = file_track
                t_num_str = str(file_track)
            else:
                t_num = re.match(r'^(\d+)', f.stem)
                filename_track_val = int(t_num.group(1)) if t_num else None
                t_num_str = t_num.group(1) if t_num else None

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

            norm_stem = TrackManager.normalize_title(stem)
            
            t_num_val = None
            if t_num_str:
                t_num_val = t_num_str.lstrip('0') or '0'
            elif meta.get("track_number"):
                try:
                    t_str = str(meta.get("track_number")).split('/')[0].strip()
                    if t_str.isdigit():
                        t_num_val = str(int(t_str))
                except Exception:
                    pass
            
            raw_tracks.append({
                "file_id": hashlib.sha1(str(f.resolve()).encode("utf-8")).hexdigest()[:16],
                "path": f, "meta": meta, "duration": TrackManager.get_duration(f), 
                "format": f.suffix.lower().lstrip('.'),
                "filename_track": filename_track_val,
                "t_num_val": t_num_val,
                "norm_stem": norm_stem,
                "disc": disc
            })

        priorities = TrackManager.get_audio_format_priority()
        def sort_key(v):
            fmt = v["format"].lower()
            try:
                return priorities.index(fmt)
            except ValueError:
                return 999

        return {
            (track["disc"], f'{track["norm_stem"]}::{track["file_id"]}'): [track]
            for track in sorted(raw_tracks, key=sort_key)
        }

    @staticmethod
    def get_audio_format_priority() -> List[str]:
        return list(SPEC_AUDIO_FORMAT_PRIORITY)

    @staticmethod
    def get_best_artwork(variants: List[Dict]) -> Optional[bytes]:
        from mutagen import File

        for v in variants:
            try:
                audio = File(v["path"])
                if not audio:
                    continue

                pictures = getattr(audio, "pictures", None) or []
                if pictures:
                    picture_data = getattr(pictures[0], "data", None)
                    if isinstance(picture_data, bytes) and picture_data:
                        return picture_data

                tags = getattr(audio, "tags", None)
                if not tags:
                    continue

                getall = getattr(tags, "getall", None)
                if getall:
                    for frame in getall("APIC"):
                        if getattr(frame, "data", None):
                            return frame.data

                for tag in tags.values():
                    values = tag if isinstance(tag, (list, tuple)) else [tag]
                    for value in values:
                        data = getattr(value, "data", value)
                        if isinstance(data, bytes) and data:
                            return data
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
            sources = [{"type": "filename", "content": variants[0]["path"].name, "file_ids": [v["file_id"] for v in variants], "inferred_track_num": variants[0].get("filename_track"), "duration": round(sum(v["duration"] for v in variants)/len(variants), 2), "weight": "weak"}]
            if merged_tags: sources.append({"type": "embedded_merged", "tags": merged_tags, "duration": sources[0]["duration"], "weight": "strong" if len(variants) > 1 else "moderate"})
            else: sources.append({"type": "no_tags_found", "content": "No metadata found", "weight": "critical_missing"})
            context[tid] = sources
        return context
