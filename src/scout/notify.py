import logging
import requests
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger("scout.notify")

class NotificationManager:
    def __init__(self, config: Any):
        self.enabled = config.notify_enabled
        self.cooldown = config.notify_cooldown
        self.webhooks = {
            "critical": config.discord_webhook_critical,
            "warning": config.discord_webhook_warning,
            "info": config.discord_webhook_info,
            "completion": config.discord_webhook_completion
        }
        self.last_sent: Dict[str, float] = {} # { "key": timestamp }

    def notify(self, level: str, title: str, message: str, fields: List[Dict[str, str]] = None, color: int = 0x3498db):
        """
        Sends a Discord notification via Webhook with an Embed.
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
                logger.debug(f"Notification suppressed due to cooldown: {cooldown_key}")
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

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            self.last_sent[cooldown_key] = now
            logger.debug(f"Discord notification sent: [{level}] {title}")
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")

    def notify_critical(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("critical", f"🚨 {title}", message, fields, color=0xe74c3c) # Red

    def notify_warning(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("warning", f"⚠️ {title}", message, fields, color=0xf1c40f) # Yellow

    def notify_info(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("info", f"ℹ️ {title}", message, fields, color=0x3498db) # Blue

    def notify_completion(self, title: str, message: str, fields: List[Dict[str, str]] = None):
        self.notify("completion", f"🏁 {title}", message, fields, color=0x2ecc71) # Green
