import requests
import logging
import re
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger("scout.ident.vgmdb")

class VGMdbClient:
    """
    Client for interacting with VGMdb.net via the CDDB (FreeDB) protocol.
    Used to retrieve high-quality, multilingual metadata for video game soundtracks.
    """
    
    ENDPOINTS = {
        "ja": "http://vgmdb.net/cddb/ja.utf8",
        "en": "http://vgmdb.net/cddb/en",
        "romaji": "http://vgmdb.net/cddb/ja-Latn"
    }

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        }

    def calculate_hex_discid(self, offsets: List[int], total_sectors: int) -> str:
        """
        Calculates the standard FreeDB DiscID hex string.
        """
        def sum_digits(n):
            s = 0
            while n > 0:
                s += n % 10
                n //= 10
            return s

        n = 0
        for off in offsets:
            n += sum_digits(int(off) // 75)
        
        total_sec = int(total_sectors) // 75
        res = ((n % 0xFF) << 24) | (total_sec << 8) | len(offsets)
        return f"{res:08x}"

    def calculate_discid_from_durations(self, durations_ms: List[float]) -> Tuple[str, List[int], int]:
        """
        Calculates DiscID and offsets from track durations.
        Useful for digital soundtracks where physical TOC is missing.
        """
        num_tracks = len(durations_ms)
        offsets = [150] # Lead-in 2s
        current_sectors = 150
        
        for dur in durations_ms[:-1]:
            current_sectors += int((dur * 75) / 1000)
            offsets.append(current_sectors)
            
        total_sectors = current_sectors + int((durations_ms[-1] * 75) / 1000)
        discid = self.calculate_hex_discid(offsets, total_sectors)
        return discid, offsets, total_sectors // 75

    def fetch_bilingual_metadata_by_durations(self, durations_ms: List[float]) -> Optional[Dict[str, Any]]:
        """
        Convenience wrapper to fetch metadata using only durations.
        """
        discid, offsets, total_sec = self.calculate_discid_from_durations(durations_ms)
        return self.fetch_bilingual_metadata(len(durations_ms), offsets, total_sec * 75)

    def _parse_cddb_response(self, text: str) -> Dict[str, Any]:
        """
        Parses the raw CDDB 'read' response into a structured dictionary.
        """
        data = {
            "title": "",
            "artist": "",
            "year": "",
            "genre": "",
            "tracks": {},
            "extd": "",
            "extt": {}
        }
        
        lines = text.splitlines()
        for line in lines:
            if line.startswith("#") or not line: continue
            
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                
                if key == "DTITLE":
                    # CDDB format is usually Artist / Album
                    if " / " in val:
                        parts = val.split(" / ", 1)
                        data["artist"] = parts[0]
                        data["title"] = parts[1]
                    else:
                        data["title"] = val
                elif key == "DYEAR": data["year"] = val
                elif key == "DGENRE": data["genre"] = val
                elif key.startswith("TTITLE"):
                    try:
                        idx = int(key[6:])
                        data["tracks"][idx] = val
                    except: pass
                elif key == "EXTD": data["extd"] += val
                elif key.startswith("EXTT"):
                    try:
                        idx = int(key[4:])
                        data["extt"][idx] = data["extt"].get(idx, "") + val
                    except: pass
        
        return data

    def fetch_bilingual_metadata(self, tracks: int, offsets: List[int], total_sectors: int) -> Optional[Dict[str, Any]]:
        """
        Attempts to fetch both Japanese and English metadata for a given disc structure.
        Returns a dictionary with combined bilingual track names.
        """
        discid = self.calculate_hex_discid(offsets, total_sectors)
        logger.debug(f"Querying VGMdb for DiscID: {discid}")
        
        total_sec = total_sectors // 75
        query_cmd = f"cddb query {discid} {tracks} " + " ".join(map(str, offsets)) + f" {total_sec}"
        
        # 1. Verify match on any endpoint (using JA as representative)
        params = {"cmd": query_cmd, "hello": "sst-client localhost sst 1.0", "proto": 6}
        try:
            resp = requests.get(self.ENDPOINTS["ja"], params=params, headers=self.headers, timeout=10)
            if not (resp.status_code == 200 and (resp.text.startswith("200") or resp.text.startswith("211"))):
                logger.debug(f"No VGMdb match for {discid}")
                return None
            
            # Extract category and confirmed discid from the first match
            lines = resp.text.splitlines()
            match_line = lines[1] if resp.text.startswith("211") else lines[0]
            parts = match_line.split()
            if len(parts) < 3: return None
            
            category = parts[1]
            real_discid = parts[2]
            
            # 2. Read details from both JA and EN endpoints
            read_cmd = f"cddb read {category} {real_discid}"
            read_params = {"cmd": read_cmd, "hello": "sst-client localhost sst 1.0", "proto": 6}
            
            resp_ja = requests.get(self.ENDPOINTS["ja"], params=read_params, headers=self.headers, timeout=10)
            resp_en = requests.get(self.ENDPOINTS["en"], params=read_params, headers=self.headers, timeout=10)
            
            if resp_ja.status_code != 200 or resp_en.status_code != 200:
                return None
                
            data_ja = self._parse_cddb_response(resp_ja.text)
            data_en = self._parse_cddb_response(resp_en.text)
            
            # 3. Combine into bilingual metadata
            combined = {
                "album_ja": data_ja["title"],
                "album_en": data_en["title"],
                "artist_ja": data_ja["artist"],
                "artist_en": data_en["artist"],
                "year": data_ja["year"],
                "genre_ja": data_ja["genre"],
                "genre_en": data_en["genre"],
                "tracks": {},
                "credits": data_ja.get("extd", "") # Keep credits from JA as they might be richer
            }
            
            for idx in data_ja["tracks"]:
                ja_title = data_ja["tracks"][idx]
                en_title = data_en["tracks"].get(idx, "")
                
                if ja_title and en_title and ja_title != en_title:
                    # Bilingual Plan B format: {Local} / {English}
                    # We'll use a 60 char limit for the combined title later in builder/tagger
                    combined["tracks"][idx + 1] = f"{ja_title} / {en_title}"
                else:
                    combined["tracks"][idx + 1] = ja_title or en_title
            
            logger.info(f"Successfully retrieved bilingual metadata from VGMdb for: {data_ja['title']}")
            return combined

        except Exception as e:
            logger.warning(f"VGMdb query failed: {e}")
            return None
