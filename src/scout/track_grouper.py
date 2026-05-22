import re
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from .ident.embedded import EmbeddedMetadataExtractor

logger = logging.getLogger("scout.track_grouper")

class TrackManager:
    @staticmethod
    def list_audio_files(directory: Path) -> List[Path]:
        exts = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".aiff"}
        return [p for p in directory.rglob("*") if p.suffix.lower() in exts and not p.name.startswith(".") and "__MACOSX" not in p.parts]

    @staticmethod
    def get_duration(path: Path) -> float:
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
            return float(subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip())
        except: return 0.0

    @staticmethod
    def group_by_logical_track(files: List[Path]) -> Dict[Tuple[int, str], List[Dict[str, Any]]]:
        temp_groups = {}
        for f in files:
            meta = EmbeddedMetadataExtractor.extract(f)
            t_num = re.match(r'^(\d+)', f.stem)
            disc = 1
            if meta.get("disc_number"):
                try:
                    d_str = str(meta.get("disc_number")).split('/')[0]
                    if d_str.isdigit(): disc = int(d_str)
                except: pass

            stem = f.stem
            stem = re.sub(r'^(\d+[\s._-]+)+', '', stem)
            stem = re.sub(r'[\s(\[]+(aiff|mp3|flac|wav|lossless|high-res|ost|soundtrack|official)[\s)\]]+$', '', stem, flags=re.IGNORECASE)
            stem = re.sub(r'[^a-zA-Z0-9]', ' ', stem)
            stem = " ".join(stem.split()).lower()
            stem = stem.replace("artifical", "artificial")
            stem = re.sub(r'\s*0+(\d+)', r' \1', stem)
            
            norm_stem = stem.strip()
            t_num_val = t_num.group(1).lstrip('0') or '0' if t_num else None
            
            temp_key = (disc, norm_stem)
            if temp_key not in temp_groups: temp_groups[temp_key] = []
            temp_groups[temp_key].append({
                "path": f, "meta": meta, "duration": TrackManager.get_duration(f), 
                "format": f.suffix.lower().lstrip('.'),
                "filename_track": int(t_num.group(1)) if t_num else None,
                "t_num_val": t_num_val
            })
            
        groups = {}
        for (disc, norm_stem), variants in temp_groups.items():
            t_nums = {v["t_num_val"] for v in variants if v["t_num_val"] is not None}
            if len(t_nums) <= 1:
                groups[(disc, norm_stem)] = variants
            else:
                for v in variants:
                    final_track_id = f"{norm_stem} {v['t_num_val']}" if v["t_num_val"] else f"{norm_stem} unnum {variants.index(v)}"
                    key = (disc, final_track_id)
                    if key not in groups: groups[key] = []
                    groups[key].append(v)
        return groups

    @staticmethod
    def adopt_optimal_files(track_groups: Dict) -> Dict:
        adopted = {}
        for key, variants in track_groups.items():
            chosen = next((v for v in variants if v["format"] in ["flac", "wav", "aiff", "alac"]), None)
            if chosen: adopted[key] = {"path": chosen["path"], "tier": "lossless", "filename_track": chosen["filename_track"]}
            else:
                chosen = next((v for v in variants if v["format"] in ["ogg", "aac", "m4a"]), variants[0])
                adopted[key] = {"path": chosen["path"], "tier": "lossy" if chosen["format"] != "mp3" else "mp3", "filename_track": chosen["filename_track"]}
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
            except: continue
        return None

    @staticmethod
    def extract_local_baseline(track_groups: Dict) -> Dict[str, Any]:
        from collections import Counter
        albums, artists, years, track_names = [], [], [], []
        for (disc, title), variants in track_groups.items():
            t_name = None
            for v in variants:
                if v["meta"]:
                    if v["meta"].get("album"): albums.append(v["meta"]["album"])
                    if v["meta"].get("artist"): artists.append(v["meta"]["artist"])
                    if v["meta"].get("year"): years.append(str(v["meta"]["year"]))
                    if not t_name and v["meta"].get("title"): t_name = v["meta"]["title"]
            if not t_name and variants:
                t_name = variants[0]["path"].stem
                t_name = re.sub(r'^(\d+[\s.-]+)+', '', t_name).strip()
            if t_name: track_names.append(t_name)
        def most_common(lst): return Counter(lst).most_common(1)[0][0] if lst else None
        return {"album": most_common(albums), "artist": most_common(artists), "year": most_common(years), "tracks": track_names}

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
