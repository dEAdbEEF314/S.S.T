import json
import zipfile
import re
from pathlib import Path

archive_dir = Path("output/archive")
suspicious_albums = []

if not archive_dir.exists():
    print("Archive directory not found.")
    exit()

print("Scanning archived albums for suspicious metadata...\n")

for zip_path in archive_dir.glob("*.zip"):
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            if "metadata.json" in z.namelist():
                with z.open("metadata.json") as f:
                    meta = json.load(f)
                    
                    app_id = meta.get("app_id")
                    album_name = meta.get("album_name")
                    tracks = meta.get("tracks", [])
                    
                    unknown_count = 0
                    fallback_count = 0
                    suspicious_titles = 0
                    
                    for t in tracks:
                        tags = t.get("tags", {})
                        title = str(tags.get("title", "")).lower()
                        artist = str(tags.get("artist", "")).lower()
                        source = str(t.get("source", "")).lower()
                        
                        # 1. "Unknown" の混入チェック
                        if "unknown" in title or "unknown" in artist or not title.strip():
                            unknown_count += 1
                        
                        # 2. System Fallback（最終手段）のチェック
                        if "fallback" in source:
                            fallback_count += 1
                            
                        # 3. 連番タイトルの捏造チェック (e.g., "Track 01", "T01")
                        if re.match(r'^(track\s*|t)\d+$', title):
                            suspicious_titles += 1
                            
                    total_tracks = len(tracks)
                    if total_tracks == 0:
                        suspicious_albums.append(f"[APP: {app_id}] {album_name} - NO TRACKS FOUND")
                        continue
                        
                    # 疑惑スコアの計算（不備率20%以上を警告対象とする）
                    failure_rate = (unknown_count + suspicious_titles) / total_tracks
                    
                    if failure_rate > 0.1 or fallback_count / total_tracks > 0.5:
                        suspicious_albums.append(
                            f"[APP: {app_id}] {album_name}\n"
                            f"  -> Tracks: {total_tracks} | Unknowns: {unknown_count} | Fallbacks: {fallback_count} | Suspicious Titles: {suspicious_titles}"
                        )
                        
    except Exception as e:
        print(f"Error reading {zip_path.name}: {e}")

if suspicious_albums:
    print(f"--- ⚠️ {len(suspicious_albums)} SUSPICIOUS ALBUMS FOUND IN ARCHIVE ⚠️ ---")
    for s in suspicious_albums:
        print(s)
        print("-" * 40)
else:
    print("✅ All archived albums look relatively clean based on basic heuristics.")
