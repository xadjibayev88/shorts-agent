"""Ixtiyoriy: natijani Telegram'ga xabar qilish (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)."""
import requests

from .utils import env, log


def telegram(text: str):
    token = env("TELEGRAM_BOT_TOKEN", required=False)
    chat = env("TELEGRAM_CHAT_ID", required=False)
    if not (token and chat):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "disable_web_page_preview": False},
            timeout=20,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram xabar yuborilmadi: %s", e)
