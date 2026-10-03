import logging
import requests
import time
from typing import Dict, Any, List
from datetime import datetime

from .utils import sanitize_log_text

logger = logging.getLogger("sst.notify")

class NotificationManager:
    def __init__(self, config: Any):
        self.config = config
        self.enabled = getattr(config, "notify_enabled", False)
        self.cooldown = getattr(config, "notify_cooldown", 60)
        self.mask_secrets_enabled = getattr(config, "security_mask_secrets_in_logs", True)
        self.webhooks = {
            "critical": getattr(config, "discord_webhook_critical", None),
            "warning": getattr(config, "discord_webhook_warning", None),
            "info": getattr(config, "discord_webhook_info", None),
            "completion": getattr(config, "discord_webhook_completion", None),
        }
        self.last_sent: Dict[str, float] = {} # { "key": timestamp }

    def notify(self, level: str, title: str, message: str, fields: List[Dict[str, str]] = None, color: int = 0x3498db):
        """
        Sends a Discord notification via Webhook with an Embed.
        Protects sensitive webhook URLs and secrets from leaking into logs.
        """
        if not self.enabled:
            return

        webhook_url = self.webhooks.get(level.lower())
        if not webhook_url:
            return

        # Cooldown check
        cooldown_key = f"{level}:{title}"
        now = time.time()
        if cooldown_key in self.last_sent:
            if now - self.last_sent[cooldown_key] < self.cooldown:
                logger.debug(f"クールダウンのため通知が抑制されました: {cooldown_key}")
                return

        # Prepare Embed
        embed = {
            "title": title,
            "description": message,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "S.S.T (Steam Soundtrack Tagger)"}
        }
        
        if fields:
            embed["fields"] = fields

        payload = {"embeds": [embed]}
        
        known_secrets = [v for v in self.webhooks.values() if v]
        max_retries = 3
        retry_delay = 2
        for attempt in range(max_retries):
            try:
                response = requests.post(webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                self.last_sent[cooldown_key] = now
                logger.debug(f"Discordへの通知を送信しました: [{level}] {title}")
                if message:
                    clean_msg = sanitize_log_text(message, known_secrets) if self.mask_secrets_enabled else message
                    logger.debug(f"通知内容:\n{clean_msg}")
                break
            except Exception as e:
                err_msg = sanitize_log_text(str(e), known_secrets) if self.mask_secrets_enabled else str(e)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logger.error(f"Discordへの通知送信に失敗しました (3 回再試行): {err_msg}")

    def notify_critical(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("critical", f"🚨 {title}", message, fields, color=0xe74c3c) # Red

    def notify_warning(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("warning", f"⚠️ {title}", message, fields, color=0xf1c40f) # Yellow

    def notify_info(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("info", f"ℹ️ {title}", message, fields, color=0x3498db) # Blue

    def notify_completion(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("completion", f"🏁 {title}", message, fields, color=0x2ecc71) # Green
