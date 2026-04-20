import os
import json
import logging
import requests
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("scout.llm")

class LLMOrganizer:
    """
    Acts as a Factual Metadata Organizer using LLM (Gemini).
    Strictly follows TAGGING_RULE.md: Consolidation only, no hallucination.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-pro"):
        # We use the OpenAI-compatible endpoint of Google AI SDK if possible, 
        # or direct Gemini API. For this impl, assuming OpenAI-compatible proxy or direct.
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        self.api_key = api_key
        self.model = model
        self.app_id = None
        self.album_name = None

    def set_context(self, app_id: int, album_name: str):
        self.app_id = app_id
        self.album_name = album_name

    def consolidate_metadata(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Takes multiple metadata sources and returns a single, finalized metadata structure.
        """
        system_prompt = """
You are a Factual Metadata Organizer for a game soundtrack tagging system.
Your goal is to consolidate multiple metadata sources into a single, accurate, and consistent JSON structure.

### STRICT RULES:
1. ABSOLUTE PROHIBITION ON HALLUCINATION: Do not invent track names, artists, or dates. If a piece of information is missing across ALL sources, leave it blank or use "Unknown".
2. NO INFERENCE: Do not guess based on your training data. Use ONLY the provided source data.
3. CONFLICT RESOLUTION: If sources conflict, prioritize accuracy. MusicBrainz is generally authoritative for tracklists, but Steam is authoritative for Publisher/Developer.
4. LANGUAGE PRIORITY: If multiple languages exist, select in this order: User's Configured Language > English > Original Language.
5. FORMATTING: Return ONLY a valid JSON object.

### TARGET MAPPING:
Map the consolidated truth to these specific fields:
- TIT2: Original Track Title (most detailed).
- TPE1: Artist (Composer/Performer names).
- TALB: Album Name (exactly as provided in .acf source).
- TPE2: Album Artist (format: "[Developer] | [Publisher]").
- TCON: Genre (format: "STEAM VGM, [Original Game Genre]").
- TIT1: Grouping (format: "[Series or Game Title] | Steam").
- COMM: Comment (format: "[Game Title] | [Steam Tags] | [AppID] | [URL]").
- TCOM: Composer (Individual/Unit names).
- TDRC: Year (YYYY).
- TRCK: Track Number.
- TPOS: Disc Number (format: "Disc/Total", e.g., "1/1").
- TLAN: Language Code.
"""

        user_prompt = f"""
Consolidate the following metadata sources for App ID {self.app_id}:

{json.dumps(context, indent=2, ensure_ascii=False)}

Return a JSON object where keys are the internal track identifiers and values are the 13 fields defined above.
Include an 'album_global' key for shared fields like Album, Album Artist, etc.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            logger.info(f"Requesting LLM consolidation for {self.album_name}...")
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=90)
            
            if response.status_code != 200:
                logger.error(f"LLM request failed: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Extract JSON if LLM returned it with markdown blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            return json.loads(content)

        except Exception as e:
            logger.error(f"Exception during LLM consolidation: {e}")
            return None
