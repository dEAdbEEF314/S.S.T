import sqlite3
import json
import re

db_path = 'data/sst_local_state.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT app_id, album_name, status, metadata_json FROM processed_albums ORDER BY processed_at DESC LIMIT 100")
rows = cursor.fetchall()

analysis = []

for app_id, album_name, status, metadata_json in rows:
    try:
        data = json.loads(metadata_json)
    except:
        continue
    
    id_conf = data.get('confidence_score', 0)
    reason = data.get('confidence_reason', '')
    tracks = data.get('tracks', [])
    
    # Analyze why it's review if it is
    review_reasons = []
    if status == 'review':
        # Check for track #0
        z_count = sum(1 for t in tracks if str(t.get('tags', {}).get('track_number')) == '0')
        if z_count > 0:
            review_reasons.append(f"Track#0 (x{z_count})")
        
        # Check for Dirty Tags in summary/reason
        if 'Dirty/Conflicting Tags' in reason or 'Dirty/Conflicting Tags' in data.get('message', ''):
            # Try to extract count
            m = re.search(r'Dirty/Conflicting Tags x(\d+)', data.get('message', ''))
            if m:
                review_reasons.append(f"Dirty Tags (x{m.group(1)})")
            else:
                review_reasons.append("Dirty Tags")
        
        # Check for confidence threshold
        if id_conf < 100:
            review_reasons.append(f"Conf < 100 ({id_conf})")
        
        # Check for Integrity Quality in classification basis (if available in logs, but here we only have metadata_json)
        # Note: metadata_json usually has 'confidence_reason' which is the LLM's reason.
        
        # Fallback/Manual check required mentions
        if any("確認が必要です" in t.get('source', '') for t in tracks):
            review_reasons.append("Manual check in source")

    analysis.append({
        "app_id": app_id,
        "name": album_name,
        "status": status,
        "conf": id_conf,
        "llm_reason": reason,
        "system_reasons": review_reasons
    })

print(json.dumps(analysis, ensure_ascii=False, indent=2))
conn.close()
