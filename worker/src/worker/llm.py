import os
import json
import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("worker.llm")

class LLMService:
    """Handles communication with OpenAI-compatible APIs (e.g., Open-WebUI)."""
    
    def __init__(self, config: dict, storage: Any):
        self.api_url = config.get("LLM_BASE_URL", "http://localhost:11434/v1")
        self.api_key = config.get("LLM_API_KEY", "ollama")
        self.model = config.get("LLM_MODEL", "llama3.1")
        self.storage = storage
        self.app_id = None
        self.album_name = None

    def set_context(self, app_id: int, album_name: str):
        """Sets the current album context for logging."""
        self.app_id = app_id
        self.album_name = album_name

    def ask(self, task_type: str, messages: List[Dict[str, str]]) -> Optional[str]:
        """
        Sends a request to the LLM and logs the interaction to S3.
        """
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0, # High precision
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"Sending LLM request for {task_type}...")
            response = requests.post(f"{self.api_url}/chat/completions", json=payload, headers=headers, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"LLM request failed: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            answer = result["choices"][0]["message"]["content"]
            
            # Prepare log for S3
            log_data = {
                "app_id": self.app_id,
                "album_name": self.album_name,
                "task_type": task_type,
                "messages": messages + [{"role": "assistant", "content": answer}],
                "model": self.model,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Upload to S3 (logs/llm/{app_id}/{timestamp}.json)
            if self.app_id:
                log_key = f"logs/llm/{self.app_id}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{task_type}.json"
                # Note: storage.upload_json must be capable of handling non-ascii via ensure_ascii=False
                self.storage.upload_json(log_data, log_key)
                logger.info(f"LLM log uploaded to S3: {log_key}")

            return answer

        except Exception as e:
            logger.error(f"Exception during LLM request: {e}")
            return None
