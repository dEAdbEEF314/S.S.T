import sqlite3
import json
import re
from pathlib import Path
from collections import Counter

def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def string_similarity(s1, s2):
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    s1 = re.sub(r'[\s\-_:\.\,\(\)\[\]\'\"]', '', s1)
    s2 = re.sub(r'[\s\-_:\.\,\(\)\[\]\'\"]', '', s2)
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    dist = levenshtein_distance(s1, s2)
    return 1.0 - (dist / max_len)

def main():
    db_path = Path("/home/sexyroot/src/S.S.T/data/sst_local_state.db")
    if not db_path.exists():
        print(f"Error: DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cur.fetchall()]
    
    if "processed_albums" not in tables:
        print("Error: processed_albums table not found")
        return
        
    cur.execute("SELECT app_id, status, album_name, metadata_json FROM processed_albums")
    rows = cur.fetchall()
    
    total = len(rows)
    print(f"============================================================")
    print(f"S.S.T Batch Process Inspector - Analysis Summary")
    print(f"Total Processed Albums: {total}")
    print(f"============================================================")
    
    status_counts = Counter()
    archive_reasons = Counter()
    review_reasons = Counter()
    abnormal_archives = []
    abnormal_reviews = []
    
    for app_id, status, album_name, metadata_json in rows:
        status_counts[status] += 1
        meta = {}
        if metadata_json:
            try:
                meta = json.loads(metadata_json)
            except Exception:
                pass
        
        if status == 'archive':
            msg = meta.get("message") or f"Success (Strategy: {meta.get('strategy', 'UNKNOWN')})"
            archive_reasons[msg] += 1
            
            # Unnatural Archive check (similarity < 0.4)
            mbz_titles_in_tracks = set()
            for t in meta.get("tracks", []):
                t_tags = t.get("tags", {})
                if t_tags.get("album") and t.get("source") and any(k in t.get("source") for k in ["MusicBrainz", "use_mbz", "MBZ"]):
                    mbz_titles_in_tracks.add(t_tags.get("album"))
            
            for mbz_album in mbz_titles_in_tracks:
                sim = string_similarity(album_name, mbz_album)
                if sim < 0.4:
                    abnormal_archives.append({
                        "app_id": app_id,
                        "album_name": album_name,
                        "mbz_album": mbz_album,
                        "similarity": sim
                    })
                    
        elif status == 'review':
            msg = meta.get("message", "Unknown Review Reason")
            extracted_reasons = []
            if msg.startswith("[") and msg.endswith("]"):
                inner = msg[1:-1]
                parts = re.split(r',\s*(?![^(]*\))', inner)
                for p in parts:
                    extracted_reasons.append(p.strip())
            else:
                extracted_reasons.append(msg)
                
            for r in extracted_reasons:
                review_reasons[r] += 1
                
            # Unnatural Review check (LLM Conf == 100% but REVIEW)
            id_conf = meta.get("confidence_score", 0)
            if id_conf >= 100:
                abnormal_reviews.append({
                    "app_id": app_id,
                    "album_name": album_name,
                    "id_conf": id_conf,
                    "quality": meta.get("integrity_quality", 0),
                    "system_message": msg,
                    "confidence_reason": meta.get("confidence_reason", "N/A")
                })
                
    print("\n[Status Distribution]")
    for stat, cnt in status_counts.items():
        print(f" - {stat.upper()}: {cnt} ({cnt/total*100:.2f}%)")
        
    print("\n[Archive Reason Patterns]")
    for r, cnt in archive_reasons.most_common():
        print(f" - {r}: {cnt}")
        
    print("\n[Review Reason Patterns (Categorized)]")
    for r, cnt in review_reasons.most_common():
        print(f" - {r}: {cnt}")
        
    print("\n[Unnatural Archive Candidates (Similarity < 40%)]")
    print(f"Count: {len(abnormal_archives)}")
    for item in abnormal_archives:
        print(f" - AppID: {item['app_id']} | '{item['album_name']}' vs MBZ '{item['mbz_album']}' (Sim: {item['similarity']:.2f})")
        
    print("\n[Unnatural Review Candidates (LLM Conf >= 100% but REVIEW)]")
    print(f"Count: {len(abnormal_reviews)}")
    for item in abnormal_reviews:
        print(f" - AppID: {item['app_id']} | '{item['album_name']}' | Conf: {item['id_conf']}% | Qual: {item['quality']}% | Msg: {item['system_message']}")
        print(f"   Reason: {item['confidence_reason']}")
    print(f"============================================================")

if __name__ == "__main__":
    main()
