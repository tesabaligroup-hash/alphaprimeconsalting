"""Уведомления менеджерам в Telegram-группу (MANAGERS_CHAT_ID в .env).

Как настроить: добавьте бота в группу менеджеров, напишите в группе /chatid —
бот ответит номером группы. Впишите его в .env: MANAGERS_CHAT_ID=-100… и перезапустите.
"""
import logging
from html import escape

import httpx

from .config import get_settings

log = logging.getLogger(__name__)


def kommo_lead_url(lead_id: int | None) -> str | None:
    s = get_settings()
    return f"{s.kommo_base_url.rstrip('/')}/leads/detail/{lead_id}" if lead_id and s.kommo_base_url else None


def notify_managers(title: str, lines: list[str], lead_id: int | None = None) -> bool:
    """Отправляет сообщение в группу менеджеров. Ошибки не ломают основную операцию."""
    s = get_settings()
    if not s.bot_token or not s.managers_chat_id:
        return False
    text = f"<b>{escape(title)}</b>\n" + "\n".join(escape(x) for x in lines if x)
    url = kommo_lead_url(lead_id) if lead_id else None  # lead_id=0 — сделки и не должно быть
    if url:
        text += f'\n\n<a href="{url}">Открыть сделку в Kommo</a>'
    elif lead_id is None:
        text += "\n\n⚠️ Сделку в Kommo создать не удалось — заведите вручную."
    try:
        r = httpx.post(f"https://api.telegram.org/bot{s.bot_token}/sendMessage", timeout=10,
                       json={"chat_id": s.managers_chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
        return r.status_code == 200
    except httpx.HTTPError as exc:
        log.warning("Уведомление менеджерам не отправлено: %s", exc)
        return False
