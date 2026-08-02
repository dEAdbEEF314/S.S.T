import logging
import threading
import subprocess
import requests
from dataclasses import dataclass
from typing import Optional, Tuple
import tiktoken

logger = logging.getLogger("sst.vram_manager")


@dataclass(frozen=True)
class RequestVramEstimate:
    kind: str
    prompt_tokens: int
    expected_output_tokens: int
    total_tokens: int
    resolved_num_ctx: int
    required_bytes: int
    clipped_to_budget: bool

class VramResourceManager:
    """
    起動時に一度だけシステムとOllamaのVRAMを計算し、固定num_ctx環境下での安全な最大並列数（スロット数）を決定するマネージャー
    """
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model
        
        self.total_vram_bytes = self._detect_total_vram()
        self.model_vram_bytes, self.bytes_per_token = self._preflight_check()
        
        if self.total_vram_bytes and self.model_vram_bytes:
            available = self.total_vram_bytes - self.model_vram_bytes
            # KV Cache枠を空きVRAMの75%に設定 (安全閾値25%マージン)
            self.kv_budget_bytes = int(available * 0.75)
        else:
            # nvidia-smi等が失敗した場合のフォールバック (6GB)
            self.kv_budget_bytes = 1024 * 1024 * 1024 * 6
            self.bytes_per_token = 128 * 1024 # 128KBの安全マージン
            
        logger.info(f"[VRAM Manager] システム総VRAM容量: {self.total_vram_bytes/(1024**3) if self.total_vram_bytes else 0:.2f} GB")
        logger.info(f"[VRAM Manager] モデル基礎占有VRAM (実測値): {self.model_vram_bytes/(1024**3):.2f} GB")
        logger.info(f"[VRAM Manager] 利用可能KVキャッシュ枠 (75%): {self.kv_budget_bytes/(1024**3):.2f} GB")

    def _detect_total_vram(self) -> Optional[int]:
        """nvidia-smiを使用して物理VRAMの総量を自律検出する"""
        try:
            cmd = ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                total_mib = sum(int(line.strip()) for line in lines if line.strip().isdigit())
                return total_mib * 1024 * 1024
        except Exception as e:
            logger.warning(f"nvidia-smi による総VRAMの取得に失敗しました: {e}")
        return None

    def _preflight_check(self) -> Tuple[int, int]:
        """Ollamaの状態を自己キャリブレーションする"""
        logger.info("Ollama プレフライト・チェックを実行中 (ウォームアップと /api/ps の解析)...")
        try:
            requests.post(f"{self.base_url}/api/chat", json={
                "model": self.model,
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "options": {"num_predict": 1}
            }, timeout=120)
            
            ps_res = requests.get(f"{self.base_url}/api/ps", timeout=10).json()
            model_vram = 0
            for m in ps_res.get("models", []):
                if m.get("name") == self.model or self.model in m.get("name"):
                    model_vram = m.get("size_vram", 0)
                    break
                    
            if model_vram == 0:
                logger.warning("/api/ps から対象モデルのVRAMサイズを取得できませんでした。")
                model_vram = 1024 * 1024 * 1024 * 5 # 5GB Fallback
                
            return model_vram, 128 * 1024 # 推定 128KB/Token
        except Exception as e:
            logger.warning(f"プレフライト・チェックが失敗しました: {e}")
            return 1024 * 1024 * 1024 * 5, 128 * 1024

    def calculate_max_workers(self, fixed_num_ctx: int, default_workers: int) -> int:
        """
        固定された num_ctx において、利用可能KVキャッシュ枠に収まる安全な最大並列スロット数を計算する
        """
        vram_per_slot = fixed_num_ctx * self.bytes_per_token
        if vram_per_slot <= 0:
            return default_workers
            
        calculated_slots = max(1, self.kv_budget_bytes // vram_per_slot)
        # 上限はOllama側のOLLAMA_NUM_PARALLEL設定にも依存するが、ここではSST側のキューリミッターとして返す
        logger.info(f"[VRAM Manager] 固定コンテキスト({fixed_num_ctx})による1スロットあたり推定VRAM: {vram_per_slot/(1024**2):.1f} MB")
        logger.info(f"[VRAM Manager] 計算上の安全な最大並列スロット数: {calculated_slots} (デフォルト設定: {default_workers})")
        
        return int(calculated_slots)
