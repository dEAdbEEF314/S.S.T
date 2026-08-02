import sqlite3
import json
import collections

db_path = 'data/sst_local_state.db'
try:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT app_id, metadata_json 
            FROM processed_albums 
            WHERE status = 'review'
        """)
        rows = cursor.fetchall()
        
    print(f"Total review rows found: {len(rows)}")
    
    reasons_counter = collections.Counter()
    detailed_logs = []
    
    for app_id, meta_str in rows:
        if meta_str:
            try:
                meta = json.loads(meta_str)
                # Check if it's an "Unknown Review Reason"
                # report_generator.py seems to categorize them by meta.get('message') or similar
                msg = meta.get('message', '')
                if not msg or msg == 'Unknown Review Reason':
                    conf = meta.get('identity_confidence', 'N/A')
                    reason = meta.get('confidence_reason', 'No reason provided by LLM')
                    reasons_counter[reason] += 1
                    detailed_logs.append({"app_id": app_id, "conf": conf, "reason": reason})
            except Exception as e:
                print(f"Error parsing JSON for {app_id}: {e}")
                
    # Output to a JSON file for the agent to read
    with open('scratch/unknown_review_results.json', 'w', encoding='utf-8') as f:
        json.dump({"summary": dict(reasons_counter), "details": detailed_logs}, f, ensure_ascii=False, indent=2)

    print("Successfully wrote results to scratch/unknown_review_results.json")
    
except Exception as e:
    print(f"Database error: {e}")
