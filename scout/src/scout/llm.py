import os
import re
import json
import logging
import requests
import time
import collections
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json_repair

logger = logging.getLogger("scout.llm")

class DistributedRateLimiter:
    def __init__(self, rpm: int, tpm: int, rpd: int):
        self.limit_rpm = rpm
        self.limit_tpm = int(tpm * 0.9) if tpm > 0 else 10**9
        self.limit_rpd = rpd
        self.lock = threading.Lock()
        self.request_times = collections.deque()
        self.token_times = collections.deque() 
        
    def _get_usage_file(self):
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        return log_dir / f"llm_usage_{datetime.now().strftime('%Y%m%d')}.json"

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return max(1, total_chars // 3)

    def acquire(self, messages: List[Dict[str, str]]) -> bool:
        tokens = self._estimate_tokens(messages)
        while True:
            with self.lock:
                now = time.time()
                while self.request_times and self.request_times[0] < now - 60:
                    self.request_times.popleft()
                while self.token_times and self.token_times[0][0] < now - 60:
                    self.token_times.popleft()
                
                req_count = len(self.request_times)
                load_factor = req_count / self.limit_rpm if self.limit_rpm > 0 else 0
                
                if load_factor >= 0.9:
                    wait = self.request_times[0] + 61.0 - now
                elif load_factor >= 0.7:
                    import random
                    wait = 2.0 + random.uniform(0, 3.0)
                elif sum(t[1] for t in self.token_times) + tokens > self.limit_tpm:
                    if self.token_times:
                        wait = self.token_times[0][0] + 61.0 - now
                    else: return True
                else:
                    self.request_times.append(now)
                    self.token_times.append((now, tokens))
                    return True
            time.sleep(max(0.1, wait))

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, 
                 model: str = "gemini-1.5-pro", 
                 rpm: int = 15, tpm: int = 10000000, rpd: int = 1500,
                 user_language: str = "ja",
                 llm_backend: str = "GEMINI",
                 draft_model: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.draft_model = draft_model
        self.user_language = user_language
        self.llm_backend = llm_backend.upper()
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def consolidate_metadata(self, app_id: int, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]], mbz_candidates: List[Dict[str, Any]], num_ctx: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        full_logs = []
        
        # --- Phase 1: Determine Global Identity (The "Soul") ---
        # Formatting helpers for Markdown readability
        def format_store_tracks(tracks):
            if not tracks: return "なし"
            md = "\n| Disc | No | Title | Duration (s) |\n|---|---|---|---|\n"
            for t in tracks: md += f"| {t.get('disc','')} | {t.get('number','')} | {t.get('title','')} | {t.get('duration_s','')} |\n"
            return md

        def format_mbz_candidates(cands):
            if not cands: return "なし"
            md = "\n"
            for i, c in enumerate(cands):
                md += f"#### Candidate [{i}]: {c.get('album')} (Score: {c.get('score')})\n"
                md += f"- **Artist**: {c.get('artist')}\n- **Year**: {c.get('year')}\n- **Label**: {c.get('label')}\n- **Tracks**: {c.get('track_count')} (Digital: {c.get('is_digital')})\n- **Evidence**: {', '.join(c.get('evidence', []))}\n"
                md += "- **Tracklist Sample**:\n"
                for t in c.get('tracks', [])[:5]:
                    md += f"  - {t.get('position')}: {t.get('title')}\n"
                if len(c.get('tracks', [])) > 5: md += "  - ...\n"
                md += "\n"
            return md

        def format_local_summary(sources):
            if not sources: return "なし"
            md = "\n| Logical ID | Duration (s) |\n|---|---|\n"
            for tid, s in sources.items():
                dur = s[0].get('duration') if s else 'Unknown'
                md += f"| {tid} | {dur} |\n"
            return md

        steam_tracks_json = json.dumps(steam_info.get('store_tracklist', []), ensure_ascii=False)
        mbz_cands_json = json.dumps(mbz_candidates, indent=2, ensure_ascii=False)
        local_tracks_json = json.dumps([{"id": tid, "duration": s[0].get("duration")} for tid, s in track_sources.items()], indent=2)

        global_id_prompt = f"""
あなたは音楽メタデータ管理の権威ある【マスター・アーカイブ監査官】です。
提供された情報源を分析し、この作品の「Identity（身元）」と「Integrity（品質）」を個別に評価してください。

### 【重要：Dirty Tags（仕様）の解釈】
- MBZ側の公式トラック名にも番号（例: "01. Name"）がある場合、それは「汚染」ではなく「仕様（Spec）」です。
- MBZ側とローカル側で**共通して番号が含まれている**なら、その番号付けは正当なものとして扱いなさい。

### 【監査基準】
1. **Identity Confidence (0-100)**: 
    - Steam情報とMBZ/ローカルが同一作品である確信度。
    - 名前とアーティストが一致し、MBZにDIRECT_STEAM_LINKがあるなら 100点。
    - 候補が複数あり絞り込めない場合は `chosen_mbz_index: null` とし、`strategy: LOCAL_BASED` としなさい。
2. **Integrity Quality (0-100)**:
    - タグがそのままアーカイブ可能か。Dirty Tags（MBZにない番号混入）があれば 50点以下 としなさい。

### 【判定の絶対ルール】
- **ARCHIVE (Ratio 95:5以上)**: Identity Confidence == 100 かつ Integrity Quality >= 95
- **REVIEW**: それ以外、または少しでも音楽的矛盾を感じる場合。確証がない場合は迷わず REVIEW としなさい。
- **STEAM STORE FALLBACK**: MBZに候補がない場合でも、Steam公式のトラックリストとローカルの構成が完全に合致し、Identity Confidence 100% と判断できるなら ARCHIVE を許可する。

### ALBUM CONTEXT:
- アルバム名: {steam_info.get('name')}
- 開発者: {steam_info.get('developer')}
- リリース年: {re.search(r'(\d{{4}})', str(steam_info.get('release_date', ''))).group(1) if re.search(r'(\d{{4}})', str(steam_info.get('release_date', ''))) else 'Unknown'}

### STEAM STORE DATA (OFFICIAL):
- トラックリスト: {steam_tracks_json}
- クレジット情報: {steam_info.get('store_credits', 'なし')}

### MUSICBRAINZ CANDIDATES:
{mbz_cands_json}

### LOCAL TRACK LIST SUMMARY:
{local_tracks_json}

### MANDATORY OUTPUT FORMAT (JSON ONLY):
**注意：分析理由（reason）を含め、すべてのテキストは必ず「日本語」で出力してください。**
```json
{{
  "identity_confidence": number,
  "integrity_quality": number,
  "archive_vs_review_ratio": {{"archive": number, "review": number}},
  "confidence_reason": "詳細な類似性分析と判断理由（日本語）",
  "strategy": "MBZ_BASED" | "LOCAL_BASED" | "HYBRID" | "REVIEW_REQUIRED",
  "semantic_label": "日本語 40文字以内",
  "global_tags": {{
    "canonical_album_artist": "...",
    "canonical_genre": "...",
    "canonical_year": "YYYY",
    "canonical_label": "レーベル名（またはパブリッシャー）",
    "chosen_mbz_index": number | null

  }}
}}
```
"""
        global_res, global_log = self._call_llm(app_id, global_id_prompt, num_ctx=num_ctx)
        
        # Add human-readable version to the log
        human_prompt = global_id_prompt.replace(steam_tracks_json, format_store_tracks(steam_info.get('store_tracklist', [])))
        human_prompt = human_prompt.replace(mbz_cands_json, format_mbz_candidates(mbz_candidates))
        human_prompt = human_prompt.replace(local_tracks_json, format_local_summary(track_sources))
        global_log["human_prompt"] = human_prompt
        full_logs.append(global_log)
        
        if not global_res:
            return None, {"phase1_log": global_log}
            
        id_conf = int(global_res.get("identity_confidence", 0))
        archive_ratio = int(global_res.get("archive_vs_review_ratio", {}).get("archive", 0))
        
        if id_conf < 95 or archive_ratio < 90 or global_res.get("strategy") == "REVIEW_REQUIRED":
            return {}, {"phase1_res": global_res, "phase1_log": global_log}

        # --- Phase 2: Sequential Track Mapping ---
        global_identity = global_res.get("global_tags", {})
        strategy = global_res.get("strategy")
        all_instructions = {}
        
        track_ids = list(track_sources.keys())
        chunk_size = 10 if self.llm_backend == "OLLAMA" else 30

        for i in range(0, len(track_ids), chunk_size):
            chunk = track_ids[i:i + chunk_size]
            chunk_sources = {k: track_sources[k] for k in chunk}

            chunk_json = json.dumps(chunk_sources, indent=2, ensure_ascii=False)
            mapping_prompt = f"""
            精密なトラックマッピングを行いなさい。
            Identity: {json.dumps(global_identity, indent=2)}

            ### STEAM STORE DATA (OFFICIAL):
            - トラックリスト: {steam_tracks_json}
            - クレジット情報: {steam_info.get('store_credits', 'なし')}

            ### INSTRUCTION:
            1. クレジット情報の文章（例: "Track 1 by X"）を読み解き、対応するトラックの composer や artist に紐付けること。
            2. Steam公式トラックリストのタイトルとローカルを照合し、MBZよりもSteam公式を優先する場合（MBZが誤っている、またはSteamがより詳細な場合）はそれを利用しなさい。

            ### TRACKS TO MAP:
            {chunk_json}

            ### MANDATORY OUTPUT FORMAT (JSON ONLY):
            **注意：判断理由（reason）を含め、すべてのテキストは必ず「日本語」で出力してください。**
            ```json
            {{
              "track_instructions": {{
                 "TRACK_ID": {{
                    "action": "use_mbz" | "use_local_tag" | "use_filename" | "needs_review",
                    "mbz_track_index": number,
                    "override_title": string | null,
                    "reason": "判断理由（日本語）"
                 }}
              }}
            }}
            ```
            """
            res, log_data = self._call_llm(app_id, mapping_prompt, num_ctx=num_ctx)

            human_mapping_prompt = mapping_prompt.replace(steam_tracks_json, format_store_tracks(steam_info.get('store_tracklist', [])))
            human_mapping_prompt = human_mapping_prompt.replace(chunk_json, format_local_summary(chunk_sources))
            log_data["human_prompt"] = human_mapping_prompt
            full_logs.append(log_data)
            
            if res and "track_instructions" in res:
                instructions = res["track_instructions"]
                for tid in instructions:
                    instructions[tid].update({
                        "TPE2": global_identity.get("canonical_album_artist"),
                        "TCON": global_identity.get("canonical_genre"),
                        "TDRC": global_identity.get("canonical_year"),
                        "identity_confidence": id_conf,
                        "confidence_score": id_conf,
                        "strategy": strategy,
                        "semantic_label": global_res.get("semantic_label"),
                        "chosen_mbz_index": global_identity.get("chosen_mbz_index", 0)
                    })
                all_instructions.update(instructions)

        return all_instructions, {"phase1_res": global_res, "phase1_log": global_log, "chunks": full_logs}

    def _call_llm(self, app_id: int, prompt: str, num_ctx: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        messages = [{"role": "user", "content": prompt}]
        log_entry = {"timestamp": datetime.utcnow().isoformat(), "prompt": prompt, "response": None, "error": None}

        logger.debug(f"[{app_id}] --- [LLM PROMPT START] ---\n{prompt}\n--- [LLM PROMPT END] ---")

        if self.llm_backend not in ["OLLAMA"] and not self.limiter.acquire(messages):
            log_entry["error"] = "Rate limit reached"
            return None, log_entry

        max_retries = 3
        retry_delay = 5

        if self.llm_backend == "OLLAMA":
            url = f"{self.base_url}/api/chat"
            options = {"temperature": 0.0}
            if num_ctx:
                options["num_ctx"] = num_ctx
            payload = {
                "model": self.model, "messages": messages, "stream": False, "format": "json",
                "options": options
            }
            if self.draft_model:
                payload["draft_model"] = self.draft_model
            headers = {"Content-Type": "application/json"}
        else:
            url = f"{self.base_url}/v1beta/openai/chat/completions" if self.llm_backend == "GEMINI" else f"{self.base_url}/v1/chat/completions"
            payload = {"model": self.model, "messages": messages, "temperature": 0.0, "response_format": {"type": "json_object"}}
            if num_ctx:
                payload["num_ctx"] = num_ctx # Ollama's OpenAI endpoint supports this
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=300)
                if response.status_code == 200:
                    res_json = response.json()
                    content = res_json.get("message", {}).get("content", "") if self.llm_backend == "OLLAMA" else res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    logger.debug(f"[{app_id}] --- [LLM RESPONSE START] ---\n{content}\n--- [LLM RESPONSE END] ---")
                    
                    if not content or not content.strip(): raise ValueError("Empty response")
                    log_entry["response"] = content
                    
                    # Act-15: Strict Parsing (No json-repair)
                    try:
                        # 1. Clean markdown code blocks and reasoning blocks
                        clean_content = re.sub(r'```json\s*(.*?)\s*```', r'\1', content, flags=re.DOTALL)
                        clean_content = re.sub(r'<(thought|reasoning)>.*?</\1>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
                        
                        # 2. Extract first valid {...} block to handle minor chatter
                        start_idx = clean_content.find('{')
                        end_idx = clean_content.rfind('}')
                        
                        if start_idx != -1 and end_idx != -1:
                            json_str = clean_content[start_idx:end_idx + 1]
                            # Minor structural cleaning that isn't "inference" (e.g. trailing commas in arrays)
                            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                            return json.loads(json_str), log_entry
                        else:
                            raise ValueError("No valid JSON object found in response")
                    except Exception as e:
                        logger.warning(f"[{app_id}] JSON strict parsing failed: {e}")
                        raise
                
                log_entry["error"] = f"HTTP {response.status_code}"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                return None, log_entry

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"[{app_id}] LLM {self.llm_backend} attempt {attempt+1} failed: {e}")
                    time.sleep(retry_delay)
                    continue
                log_entry["error"] = str(e)
                return None, log_entry
        return None, log_entry
