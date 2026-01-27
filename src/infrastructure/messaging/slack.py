"""
Slack notification service.
"""
import logging
from typing import Optional
import requests
from requests.exceptions import RequestException

from src.config.settings import settings

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Slack notification service for sending alerts and messages."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.token = settings.slack_token
        self.channel_id = settings.slack_channel_id
        self.enabled = settings.slack_enabled
        self.api_url = "https://slack.com/api/chat.postMessage"
    
    def send_message(
        self,
        text: str,
        channel_id: Optional[str] = None,
        num_retries: int = 3
    ) -> bool:
        """
        Send a message to Slack.
        
        Args:
            text: The message text to send
            channel_id: Optional channel ID (uses default if not provided)
            num_retries: Number of retry attempts on failure
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug(f"Slack disabled, would have sent: {text}")
            return True
        
        if not self.token:
            logger.warning("Slack token not configured")
            return False
        
        target_channel = channel_id or self.channel_id
        if not target_channel:
            logger.warning("Slack channel not configured")
            return False
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "channel": target_channel,
            "text": text
        }
        
        for attempt in range(num_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        return True
                    else:
                        logger.error(f"Slack API error: {result.get('error')}")
                else:
                    logger.error(f"Slack HTTP error: {response.status_code}")
                    
            except RequestException as e:
                logger.error(f"Slack request failed (attempt {attempt + 1}): {e}")
        
        return False
    
    def send_error(self, error_message: str, context: Optional[str] = None) -> bool:
        """Send an error notification."""
        text = f"🚨 *Error*\n{error_message}"
        if context:
            text += f"\n\n*Context:* {context}"
        return self.send_message(text)
    
    def send_warning(self, warning_message: str, context: Optional[str] = None) -> bool:
        """Send a warning notification."""
        text = f"⚠️ *Warning*\n{warning_message}"
        if context:
            text += f"\n\n*Context:* {context}"
        return self.send_message(text)
    
    def send_info(self, info_message: str) -> bool:
        """Send an info notification."""
        return self.send_message(f"ℹ️ {info_message}")
    
    def send_trade_notification(
        self,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        user_id: str
    ) -> bool:
        """Send a trade execution notification."""
        text = (
            f"📈 *Trade Executed*\n"
            f"• Exchange: {exchange}\n"
            f"• Symbol: {symbol}\n"
            f"• Side: {side}\n"
            f"• Quantity: {quantity}\n"
            f"• Price: {price}\n"
            f"• User: {user_id[:8]}..."
        )
        return self.send_message(text)
    
    def send_startup_notification(self, exchange: str, user_count: int, aum: float) -> bool:
        """Send a bot startup notification."""
        text = (
            f"🚀 *Bot Started*\n"
            f"• Exchange: {exchange}\n"
            f"• Active Users: {user_count}\n"
            f"• Total AUM: {aum:,.0f}"
        )
        return self.send_message(text)
    
    def send_api_key_error(self, user_id: str, exchange: str, error_type: str) -> bool:
        """Send an API key error notification."""
        text = (
            f"🔑 *API Key Error*\n"
            f"• User: {user_id[:8]}...\n"
            f"• Exchange: {exchange}\n"
            f"• Error: {error_type}"
        )
        return self.send_message(text)


# Global instance
slack_notifier = SlackNotifier()


# Convenience function for backward compatibility
def post_slack_msg(text: str, num_iter: int = 1) -> bool:
    """
    Post a message to Slack (backward compatible function).
    
    Args:
        text: Message text
        num_iter: Number of retry attempts
        
    Returns:
        True if successful
    """
    return slack_notifier.send_message(text, num_retries=num_iter)
