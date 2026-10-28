import html
import re
import unicodedata
import logging
import subprocess
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import os
import mutagen
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
                    name = p.name
                    if name.startswith(".") or name.startswith("._"):
                        continue
                    if p.suffix.lower() not in exts:
                        continue
                    path_parts = {part.lower() for part in p.parts}
                    if ".ds_store" in path_parts or "__macosx" in path_parts:
                        continue
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
        # 1. Fast path: Mutagen length extraction directly from headers (no subprocess)
        try:
            file_loader = getattr(mutagen, "File")
            audio = file_loader(path)
            if audio is not None and getattr(audio, "info", None) is not None:
                length = getattr(audio.info, "length", None)
                if length is not None and isinstance(length, (int, float)) and length > 0:
                    return float(length)
        except Exception:
            pass

        # 2. Fallback: ffprobe process invocation (with configurable timeout)
        try:
            timeout_sec = float(os.getenv("FFPROBE_TIMEOUT", "10"))
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
            return float(subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec).stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def normalize_title(stem: str, strip_track_prefix: bool = True) -> str:
        stem = html.unescape(stem or "")
        stem = unicodedata.normalize("NFKC", stem)
        stem = re.sub(r'\.(?:aiff|aif|mp3|flac|wav|ogg|m4a|aac|wma|opus)$', '', stem, flags=re.IGNORECASE)
        if strip_track_prefix:
            stem = re.sub(r'^\d+(?:[-_.]\d+)?[\s._-]+', '', stem)
        stem = re.sub(r'[\s(\[]+(?:aiff|mp3|flac|wav|lossless|high[\s-]*res|ost|soundtrack|official|[\s\-])+[\s)\]]+$', '', stem, flags=re.IGNORECASE)
        stem = "".join(ch if unicodedata.category(ch)[0] in {"L", "N"} else " " for ch in stem)
        stem = " ".join(stem.split()).lower()
        stem = stem.replace("artifical", "artificial")
        stem = re.sub(r'(?:^|(?<=\s))0+(\d+)', r'\1', stem)
        return stem.strip()

    @staticmethod
    def build_file_records(files: List[Path], album_name: Optional[str] = None) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        file_previews = []
        compound_candidates: Dict[Path, Tuple[int, int]] = {}
        discs_tracks_map: Dict[int, List[int]] = {}

        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            disc = 1
            if meta.get("disc_number"):
                try:
                    d_str = str(meta.get("disc_number")).split('/')[0].strip()
                    if d_str.isdigit() and int(d_str) > 0:
                        disc = int(d_str)
                except Exception:
                    pass

            if disc == 1:
                # Look for "disc N" or "CD N" in directory path parts (not filename itself)
                for part in reversed(f.parts[:-1]):
                    d_match = re.search(r'(?:disc|cd)\s*(\d+)', part, re.IGNORECASE)
                    if d_match:
                        disc = int(d_match.group(1))
                        break

            embedded_track = None
            if meta.get("track_number"):
                try:
                    t_str = str(meta.get("track_number")).split('/')[0].strip()
                    if t_str.isdigit() and int(t_str) > 0:
                        embedded_track = int(t_str)
                except Exception:
                    pass

            clean_stem = f.stem
            if album_name:
                escaped_album = re.escape(album_name)
                clean_stem = re.sub(escaped_album, '', clean_stem, flags=re.IGNORECASE)
                short_album = re.sub(r'\s*(Soundtrack|Original Soundtrack|OST)\s*$', '', album_name, flags=re.IGNORECASE)
                if short_album and short_album != album_name:
                    clean_stem = re.sub(re.escape(short_album), '', clean_stem, flags=re.IGNORECASE)
            clean_stem = clean_stem.strip(" -_")

            # Check for multi-disc compound pattern candidate:
            # Must match ^(\d{1,2})[-_](\d{1,3})(?:[^\d]|$)
            # and not be followed by decimal digit (e.g. 05_4.8)
            c_match = re.match(r'^(\d{1,2})[-_](\d{1,3})(?:[^\d]|$)', clean_stem)
            if c_match and not re.match(r'^\d{1,2}[-_]\d{1,3}\.\d', clean_stem):
                c_disc = int(c_match.group(1))
                c_track = int(c_match.group(2))
                # Check non-conflict with embedded track
                if embedded_track is not None and embedded_track == c_disc and embedded_track != c_track:
                    pass
                elif 1 <= c_disc <= 10:
                    compound_candidates[f] = (c_disc, c_track)
                    discs_tracks_map.setdefault(c_disc, []).append(c_track)

            file_previews.append({
                "file": f,
                "meta": meta,
                "disc": disc,
                "embedded_track": embedded_track,
                "clean_stem": clean_stem,
            })

        # Album-wide validation of compound pattern:
        # Genuine multi-disc albums have:
        # 1. Disc 1 must be present in the compound candidates
        # 2. If multiple discs exist, each disc starts with track 1 (1 in tracks),
        #    or at least one disc has multiple tracks (>= 2 tracks)
        # 3. If only one disc exists (Disc 1), it must have multiple tracks (>= 2 tracks) starting with track 1
        is_genuine_compound = False
        if discs_tracks_map and 1 in discs_tracks_map:
            if len(discs_tracks_map) >= 2:
                has_track_one_in_all = all(1 in tracks for tracks in discs_tracks_map.values())
                has_multi_tracks = any(len(tracks) >= 2 for tracks in discs_tracks_map.values())
                is_genuine_compound = has_track_one_in_all or has_multi_tracks
            else:
                is_genuine_compound = len(discs_tracks_map[1]) >= 2 and 1 in discs_tracks_map[1]

        raw_tracks = []
        for info in file_previews:
            f = info["file"]
            meta = info["meta"]
            disc = info["disc"]
            embedded_track = info["embedded_track"]
            clean_stem = info["clean_stem"]

            filename_track_val = None
            t_num_str = None
            norm_stem = ""

            if is_genuine_compound and f in compound_candidates:
                file_disc, file_track = compound_candidates[f]
                if disc == 1 and file_disc > 0:
                    disc = file_disc
                filename_track_val = file_track
                t_num_str = str(file_track)
                title_part = re.sub(r'^\d{1,2}[-_]\d{1,3}[\s._-]*', '', clean_stem)
                norm_stem = TrackManager.normalize_title(title_part, strip_track_prefix=False) if title_part else TrackManager.normalize_title(clean_stem)
            else:
                leading_match = re.match(r'^(\d+)', clean_stem)
                if leading_match:
                    file_track = int(leading_match.group(1))
                    filename_track_val = file_track
                    t_num_str = leading_match.group(1)
                    title_part = re.sub(r'^\d+[\s._-]+', '', clean_stem)
                    if title_part == clean_stem:
                        title_part = re.sub(r'^\d+', '', clean_stem)
                    norm_stem = TrackManager.normalize_title(title_part, strip_track_prefix=False) if title_part else TrackManager.normalize_title(clean_stem)
                else:
                    # No leading number: middle number search or embedded track
                    if embedded_track is not None and embedded_track > 0:
                        filename_track_val = embedded_track
                        t_num_str = str(embedded_track)
                        num_pattern = re.compile(rf'(?:^|[\s\-_])0*{embedded_track}(?=[\s\-_.]|$)')
                        m = num_pattern.search(clean_stem)
                        if m:
                            title_part = clean_stem[m.end():].strip(" -_") or clean_stem[:m.start()].strip(" -_")
                            norm_stem = TrackManager.normalize_title(title_part, strip_track_prefix=False) if title_part else TrackManager.normalize_title(clean_stem)
                        else:
                            norm_stem = TrackManager.normalize_title(clean_stem, strip_track_prefix=False)
                    else:
                        matches = list(re.finditer(r'(?:^|[\s\-_])(\d{1,3})(?=[\s\-_.]|$)', clean_stem))
                        valid_matches = []
                        for m in matches:
                            following = clean_stem[m.end():]
                            if re.match(r'^\s*(?:master|bit|kbps|khz|bpm|vbr|cbr)\b', following, re.IGNORECASE):
                                continue
                            valid_matches.append(m)

                        if valid_matches:
                            best_match = valid_matches[-1]
                            t_num_str = best_match.group(1)
                            filename_track_val = int(t_num_str)
                            title_part = clean_stem[best_match.end():].strip(" -_") or clean_stem[:best_match.start()].strip(" -_")
                            norm_stem = TrackManager.normalize_title(title_part, strip_track_prefix=False) if title_part else TrackManager.normalize_title(clean_stem)
                        else:
                            norm_stem = TrackManager.normalize_title(clean_stem, strip_track_prefix=False)

            t_num_val = None
            if t_num_str:
                t_num_val = t_num_str.lstrip('0') or '0'
            elif embedded_track is not None:
                t_num_val = str(embedded_track)

            raw_tracks.append({
                "file_id": hashlib.sha1(str(f.resolve()).encode("utf-8")).hexdigest()[:16],
                "path": f, "meta": meta, "duration": meta.get("duration") or TrackManager.get_duration(f), 
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
        file_loader = getattr(mutagen, "File")

        for v in variants:
            try:
                audio = file_loader(v["path"])
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
            except Exception:
                continue
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
                        if v["meta"].get("album"):
                            albums.append(v["meta"]["album"])
                        if v["meta"].get("artist"):
                            artists.append(v["meta"]["artist"])
                        if v["meta"].get("year"):
                            years.append(str(v["meta"]["year"]))
                        if not t_name and v["meta"].get("title"):
                            t_name = v["meta"]["title"]
            
            # 3. Fallback to filename
            if not t_name and variants:
                t_name = variants[0]["path"].stem
                t_name = re.sub(r'^(\d+[\s.-]+)+', '', t_name).strip()
            
            if t_name:
                track_data.append((t_name, int(avg_dur * 1000)))
        
        def most_common(lst):
            return Counter(lst).most_common(1)[0][0] if lst else None

        return {
            "album": most_common(albums),
            "artist": most_common(artists),
            "year": most_common(years),
            "tracks": track_data,
        }

    @staticmethod
    def prepare_llm_track_context(track_groups: Dict) -> Dict[str, List[Dict[str, Any]]]:
        context = {}
        for (disc, clean_title), variants in track_groups.items():
            merged_tags = {}
            for v in variants:
                if v["meta"]:
                    for k, val in v["meta"].items():
                        if val and str(val).lower() not in ["", "none", "unknown", "0"] and k not in merged_tags:
                            merged_tags[k] = val
            tid = f"{disc}_{clean_title}"
            sources = [{
                "type": "filename",
                "content": variants[0]["path"].name,
                "file_ids": [v["file_id"] for v in variants],
                "inferred_track_num": variants[0].get("filename_track"),
                "duration": round(sum(v["duration"] for v in variants) / len(variants), 2),
                "weight": "weak",
            }]
            if merged_tags:
                sources.append({
                    "type": "embedded_merged",
                    "tags": merged_tags,
                    "duration": sources[0]["duration"],
                    "weight": "strong" if len(variants) > 1 else "moderate",
                })
            else:
                sources.append({
                    "type": "no_tags_found",
                    "content": "No metadata found",
                    "weight": "critical_missing",
                })
            context[tid] = sources
        return context
