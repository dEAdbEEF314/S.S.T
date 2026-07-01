import logging
import threading
import subprocess
import requests
from typing import Optional, Tuple
import tiktoken

logger = logging.getLogger("sst.vram_manager")

class VramResourceManager:
    """
    Token Stingy戦略に基づく動的VRAMセマフォマネージャー
    """
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model
        
        self.total_vram_bytes = self._detect_total_vram()
        self.model_vram_bytes, self.bytes_per_token = self._preflight_check()
        
        if self.total_vram_bytes and self.model_vram_bytes:
            available = self.total_vram_bytes - self.model_vram_bytes
            # KV Cache枠を空きVRAMの80%に設定 (安全閾値)
            self.kv_budget_bytes = int(available * 0.8)
        else:
            # nvidia-smi等が失敗した場合のフォールバック (6GB)
            self.kv_budget_bytes = 1024 * 1024 * 1024 * 6
            self.bytes_per_token = 128 * 1024 # 128KBの安全マージン
            
        logger.info(f"[VRAM Manager] システム総VRAM容量: {self.total_vram_bytes/(1024**3) if self.total_vram_bytes else 0:.2f} GB")
        logger.info(f"[VRAM Manager] モデル占有VRAM (実測値): {self.model_vram_bytes/(1024**3):.2f} GB")
        logger.info(f"[VRAM Manager] 並列処理用KVキャッシュ枠 (80%): {self.kv_budget_bytes/(1024**3):.2f} GB")
        
        self.available_vram = self.kv_budget_bytes
        self.cond = threading.Condition()

    def _detect_total_vram(self) -> Optional[int]:
        """nvidia-smiを使用して物理VRAMの総量を自律検出する (Zero-Config)"""
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
            # 1. ウォームアップ: ダミープロンプトを送信し、モデルをVRAMにロードさせる
            requests.post(f"{self.base_url}/api/chat", json={
                "model": self.model,
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "options": {"num_predict": 1}
            }, timeout=120)
            
            # 2. /api/ps の解析: 実際の占有VRAMを取得
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

    def estimate_album_vram(self, track_count: int, album_name: str) -> int:
        """指定されたトラック数から、処理に必要なVRAM容量(バイト)を厳密に予測する"""
        # 1-1. 入力トークン予測 (/api/tokenize)
        dummy_track = '{"local_key": [1, 1], "title": "Long Dummy Track Title With Lots Of Words", "duration_ms": 300000},'
        dummy_prompt = f"ALBUM: {album_name}\n" + dummy_track * track_count
        
        try:
            res = requests.post(f"{self.base_url}/api/tokenize", json={
                "model": self.model,
                "prompt": dummy_prompt
            }, timeout=10)
            if res.status_code == 200:
                input_tokens = len(res.json().get("tokens", []))
            else:
                # 404等の場合は例外を投げてtiktokenのフォールバックへ移行させる
                raise ValueError(f"tokenize API returned {res.status_code}")
        except Exception:
            try:
                # tiktokenによるフォールバック計算
                enc = tiktoken.get_encoding("cl100k_base")
                input_tokens = len(enc.encode(dummy_prompt))
            except Exception as e:
                logger.warning(f"tiktoken fallback failed: {e}")
                input_tokens = 1000 + (track_count * 100)
            
        # 1-2. 出力トークン予測 (スキーマ制約と最大500文字制限の合算)
        max_output_tokens = track_count * 300
        
        # 1-3. トークン予測の安全マージン (1.25倍)
        total_tokens = int((input_tokens + max_output_tokens) * 1.25)
        
        vram_bytes = total_tokens * self.bytes_per_token
        return vram_bytes

    def acquire(self, amount_bytes: int):
        """必要なVRAM枠が空くまで安全に待機（ブロック）する"""
        # 安全装置: 要求サイズが最大予算(kv_budget_bytes)を超える場合は、最大予算にクリップして単独実行させる(CPUオフロード許容)
        if amount_bytes > self.kv_budget_bytes:
            logger.warning(f"要求VRAM({amount_bytes/(1024**2):.1f}MB)が最大枠({self.kv_budget_bytes/(1024**2):.1f}MB)を超過しています。最大枠にクリップします。")
            amount_bytes = self.kv_budget_bytes

        with self.cond:
            while self.available_vram < amount_bytes:
                logger.debug(f"VRAM枠の空きを待機中... 要求: {amount_bytes/(1024**2):.1f}MB, 空き: {self.available_vram/(1024**2):.1f}MB")
                self.cond.wait()
            self.available_vram -= amount_bytes
            logger.debug(f"VRAM枠を確保しました: {amount_bytes/(1024**2):.1f}MB. 残り: {self.available_vram/(1024**2):.1f}MB")

    def release(self, amount_bytes: int):
        """VRAM枠を返却し、待機中の他のタスクに通知する"""
        with self.cond:
            self.available_vram += amount_bytes
            logger.debug(f"VRAM枠を返却しました: {amount_bytes/(1024**2):.1f}MB. 残り: {self.available_vram/(1024**2):.1f}MB")
            self.cond.notify_all()
