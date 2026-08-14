import re
import json
import logging
import requests
import time
from typing import cast, Dict, Any, Optional, Tuple, Callable
from datetime import UTC, datetime

from ..rate_limit import DistributedRateLimiter
from .prompts import get_system_prompt

logger = logging.getLogger("sst.llm.client")

ProgressCallback = Callable[[Dict[str, Any]], None]

class LLMClient:
    def __init__(self, api_key: str, base_url: str, 
                 model: str = "gemini-1.5-pro", 
                 rpm: int = 15, tpm: int = 10000000, rpd: int = 1500,
                 llm_backend: str = "GEMINI",
                 draft_model: Optional[str] = None,
                 llm_cloud_max_tokens: int = 8192,
                 ollama_num_ctx: int = 32768,
                 ollama_num_predict: int = 4096,
                 llm_vram_scheduling_enabled: bool = True,
                 request_timeout: int = 3600,
                 chunk_output_tokens_per_track: int = 180):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.draft_model = draft_model
        self.llm_cloud_max_tokens = llm_cloud_max_tokens
        self.llm_limit_tpm = tpm
        self.ollama_num_ctx = ollama_num_ctx
        self.ollama_num_predict = ollama_num_predict
        self.llm_vram_scheduling_enabled = llm_vram_scheduling_enabled
        self.request_timeout = request_timeout
        self.chunk_output_tokens_per_track = max(1, chunk_output_tokens_per_track)
        self.llm_backend = llm_backend.upper()
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)
        self.vram_manager = None

    def set_vram_manager(self, vram_manager: Any):
        self.vram_manager = vram_manager

    def _estimate_expected_output_tokens(self, request_kind: str, request_units: int) -> int:
        if request_kind == "identity":
            return min(self.ollama_num_predict, 4096)
        if request_kind == "track_mapping":
            per_track = max(80, self.chunk_output_tokens_per_track)
            return max(512, min(self.ollama_num_predict, 512 + request_units * per_track))
        return max(512, min(self.ollama_num_predict, 512 + request_units * self.chunk_output_tokens_per_track))

    def _notify_progress(self, progress_callback: Optional[ProgressCallback], **event: Any):
        if not progress_callback:
            return
        try:
            progress_callback(event)
        except Exception as e:
            logger.debug(f"LLM progress callback failed: {e}")

    def check_availability(self) -> bool:
        """起動時にLLMサービスの可用性をチェックする"""
        try:
            if self.llm_backend == "OLLAMA":
                url = f"{self.base_url}/api/tags"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    logger.info(f"Ollamaサーバーとの接続に成功しました: {self.base_url}")
                    return True
                else:
                    logger.error(f"Ollamaサーバーから予期せぬ応答がありました: HTTP {response.status_code}")
                    return False

            elif self.llm_backend in ["GEMINI", "OPENAI_COMPATIBLE"]:
                if not self.api_key or self.api_key == "your_api_key":
                    logger.error(f"{self.llm_backend} のAPIキーが設定されていません。.env ファイルを確認してください。")
                    return False
                
                # Modelsエンドポイントで簡易接続テスト
                if self.llm_backend == "GEMINI":
                    url = f"{self.base_url}/v1beta/openai/models"
                else:
                    url = f"{self.base_url}/v1/models"
                    
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    logger.info(f"{self.llm_backend} との接続およびAPIキーの有効性を確認しました。")
                    return True
                elif response.status_code in [401, 403]:
                    logger.error(f"{self.llm_backend} のAPIキーが無効です (HTTP {response.status_code})。.env を確認してください。")
                    return False
                else:
                    logger.warning(f"{self.llm_backend} のAPIキーチェックで予期せぬ応答がありました (HTTP {response.status_code})。")
                    return True # Some compatible servers might not implement /models properly

            else:
                logger.error(f"未知のLLM_BACKENDです: {self.llm_backend}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"LLMサーバー ({self.llm_backend}) との接続テストに失敗しました: {e}")
            return False

    def call_llm(
        self,
        app_id: int,
        prompt: str,
        num_ctx: Optional[int] = None,
        request_kind: str = "generic",
        request_units: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        system_prompt = get_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "prompt": prompt,
            "response": None,
            "error": None,
            "request_kind": request_kind,
            "attempts": [],
        }

        logger.debug(f"[{app_id}] --- [LLM PROMPT START] ---\n{prompt}\n--- [LLM PROMPT END] ---")

        if self.llm_backend not in ["OLLAMA"] and not self.limiter.acquire(messages):
            log_entry["error"] = "Rate limit reached"
            return None, log_entry

        max_retries = 3
        retry_delay = 5
        effective_num_ctx = num_ctx or self.ollama_num_ctx
        request_started = time.monotonic()

        self._notify_progress(
            progress_callback,
            phase="llm_prepare",
            app_id=app_id,
            request_kind=request_kind,
            request_units=request_units,
        )

        output_budget = max(1, self._estimate_expected_output_tokens(request_kind, request_units))
        try:
            if self.llm_backend == "OLLAMA":
                url = f"{self.base_url}/api/chat"
                # Keep the backend output budget aligned with the adaptive
                # chunk planner. Unlimited generation caused repeated backend
                # truncation at the server's context boundary.
                if effective_num_ctx:
                    approx_prompt_tokens = max(512, len(prompt) // 3)
                    max_safe_output = max(256, effective_num_ctx - approx_prompt_tokens - 256)
                    output_budget = min(output_budget, max_safe_output)
                options = {"temperature": 0.0, "num_predict": output_budget}
                if effective_num_ctx:
                    options["num_ctx"] = effective_num_ctx
                payload = {
                    "model": self.model, "messages": messages, "stream": False, "format": "json",
                    "options": options
                }
                if self.draft_model:
                    payload["draft_model"] = self.draft_model
                headers = {"Content-Type": "application/json"}
            else:
                url = f"{self.base_url}/v1beta/openai/chat/completions" if self.llm_backend == "GEMINI" else f"{self.base_url}/v1/chat/completions"
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                }
                payload["max_tokens"] = self.llm_cloud_max_tokens
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

            for attempt in range(max_retries + 1):
                self._notify_progress(
                    progress_callback,
                    phase="llm_request_running",
                    app_id=app_id,
                    request_kind=request_kind,
                    request_units=request_units,
                    attempt=attempt + 1,
                    num_ctx=effective_num_ctx,
                )
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=self.request_timeout)
                    if response.status_code == 200:
                        res_json = response.json()
                        message = res_json.get("message", {})
                        content = message.get("content", "")
                        thinking = message.get("thinking", "")
                        done_reason = res_json.get("done_reason")
                        log_entry["meta"] = {
                            "done": res_json.get("done"),
                            "done_reason": done_reason,
                            "prompt_eval_count": res_json.get("prompt_eval_count"),
                            "eval_count": res_json.get("eval_count"),
                        }

                        if done_reason in {"length", "max_tokens"}:
                            log_entry["error"] = f"response truncated by backend (done_reason={done_reason})"
                            log_entry["error_code"] = "response_truncated"
                            log_entry["truncated"] = True
                            log_entry["truncation_attempt"] = attempt + 1
                            log_entry["attempts"].append({
                                "attempt": attempt + 1,
                                "done_reason": done_reason,
                                "duration_seconds": round(time.monotonic() - request_started, 3),
                            })
                            logger.warning(f"[{app_id}] LLM output truncated by backend: done_reason={done_reason}")
                            # At temperature 0, identical retries will deterministically truncate again.
                            # Skip wasteful retries and return immediately so organizer can shrink chunk size.
                            return None, log_entry

                        if self.llm_backend != "OLLAMA":
                            content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")

                        logger.debug(f"[{app_id}] --- [LLM RESPONSE START] ---\n{content}\n--- [LLM RESPONSE END] ---")
                        if thinking:
                            logger.debug(f"[{app_id}] --- [LLM THINKING START] ---\n{thinking}\n--- [LLM THINKING END] ---")

                        if not content or not content.strip():
                            if thinking and '{' in thinking:
                                content = thinking
                            else:
                                raise ValueError("Empty response")

                        log_entry["response"] = content

                        try:
                            clean_content = re.sub(r'```json\s*(.*?)\s*```', r'\1', content, flags=re.DOTALL)
                            clean_content = re.sub(r'<(thought|reasoning)>.*?</\1>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
                            start_idx = clean_content.find('{')
                            end_idx = clean_content.rfind('}')
                            if start_idx != -1 and end_idx != -1:
                                json_str = clean_content[start_idx:end_idx + 1]
                                json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                                parsed = json.loads(json_str)
                                if not isinstance(parsed, dict):
                                    raise ValueError("LLM response JSON must be an object")
                                if request_kind == "identity" and isinstance(parsed, dict):
                                    def lower_keys(d):
                                        if isinstance(d, dict):
                                            return {k.lower(): lower_keys(v) for k, v in d.items()}
                                        if isinstance(d, list):
                                            return [lower_keys(v) for v in d]
                                        return d

                                    parsed = lower_keys(parsed)
                                total_duration = round(time.monotonic() - request_started, 3)
                                prompt_eval_count = log_entry.get("meta", {}).get("prompt_eval_count")
                                eval_count = log_entry.get("meta", {}).get("eval_count")
                                log_entry["attempts"].append({
                                    "attempt": attempt + 1,
                                    "done_reason": done_reason,
                                    "duration_seconds": total_duration,
                                    "prompt_eval_count": log_entry.get("meta", {}).get("prompt_eval_count"),
                                    "eval_count": log_entry.get("meta", {}).get("eval_count"),
                                })
                                logger.info(
                                    "LLM_REQUEST_DONE %s",
                                    json.dumps({
                                        "app_id": app_id,
                                        "request_kind": request_kind,
                                        "request_units": request_units,
                                        "attempt": attempt + 1,
                                        "duration_seconds": total_duration,
                                        "num_ctx": effective_num_ctx,
                                        "prompt_eval_count": prompt_eval_count,
                                        "eval_count": eval_count,
                                        "total_tokens": (prompt_eval_count or 0) + (eval_count or 0),
                                        "output_budget": output_budget,
                                        "wait_seconds": 0,
                                    }, ensure_ascii=False),
                                )
                                self._notify_progress(
                                    progress_callback,
                                    phase="llm_request_done",
                                    app_id=app_id,
                                    request_kind=request_kind,
                                    request_units=request_units,
                                    duration_seconds=total_duration,
                                )
                                return cast(Dict[str, Any], parsed), log_entry
                            raise ValueError("No valid JSON object found in response")
                        except Exception as e:
                            logger.warning(f"[{app_id}] JSON strict parsing failed: {e}")
                            log_entry["error_code"] = "json_parse_error"
                            raise

                    log_entry["error"] = f"HTTP {response.status_code}"
                    logger.warning(f"[{app_id}] LLM {self.llm_backend} attempt {attempt+1} failed with HTTP {response.status_code}: {response.text}")
                    if attempt < max_retries:
                        self._notify_progress(
                            progress_callback,
                            phase="llm_request_retry",
                            app_id=app_id,
                            request_kind=request_kind,
                            request_units=request_units,
                            attempt=attempt + 1,
                            reason=log_entry["error"],
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 1.5
                        continue
                    return None, log_entry

                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"[{app_id}] LLM {self.llm_backend} attempt {attempt+1} failed: {e}")
                        self._notify_progress(
                            progress_callback,
                            phase="llm_request_retry",
                            app_id=app_id,
                            request_kind=request_kind,
                            request_units=request_units,
                            attempt=attempt + 1,
                            reason=str(e),
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 1.5
                        continue
                    log_entry["error"] = str(e)
                    logger.info(
                        "LLM_REQUEST_FAIL %s",
                        json.dumps({
                            "app_id": app_id,
                            "request_kind": request_kind,
                            "request_units": request_units,
                            "duration_seconds": round(time.monotonic() - request_started, 3),
                            "num_ctx": effective_num_ctx,
                            "error": str(e),
                        }, ensure_ascii=False),
                    )
                    self._notify_progress(
                        progress_callback,
                        phase="llm_request_failed",
                        app_id=app_id,
                        request_kind=request_kind,
                        request_units=request_units,
                        error=str(e),
                    )
                    return None, log_entry
            return None, log_entry
        finally:
            pass
