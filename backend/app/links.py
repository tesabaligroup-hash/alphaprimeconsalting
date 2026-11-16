"""Персональные ссылки партнёра (на каждое его кодовое слово — своя ссылка и QR)."""
import re
from urllib.parse import quote

from .config import get_settings
from .models import Partner

START_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def start_payload(p: Partner, word: str | None = None) -> str:
    """Telegram разрешает в ?start= только латиницу, цифры, _ и -. Кириллическое слово заменяем на id."""
    w = word or p.codeword
    if w and START_RE.match(w):
        return w
    return f"p{p.id}"


MANAGERS_TELEGRAM = "alpha_prime_id"  # если в .env не задан COMPANY_TELEGRAM


def partner_links(p: Partner, word: str | None = None) -> dict:
    """Ссылки и QR ведут прямо в чат с менеджерами (WhatsApp / Telegram) с готовым сообщением «Я от СЛОВО».
    Менеджер видит слово и ставит партнёра в поле «Партнёр» в Kommo (или бот подскажет: /kod СЛОВО)."""
    s = get_settings()
    w = word or p.codeword or ""
    hello = quote("Здравствуйте! Я от " + w)
    tg_user = (s.company_telegram or MANAGERS_TELEGRAM).lstrip("@")
    return {
        "tg": f"https://t.me/{tg_user}?text={hello}",
        "wa": f"https://wa.me/{s.company_whatsapp}?text={hello}",
        "bot": f"https://t.me/{s.bot_username}?start={start_payload(p, w)}",
        "ig": f"https://ig.me/m/{s.company_instagram}" if s.company_instagram else None,
        "text": f"Я от {w}",
    }
