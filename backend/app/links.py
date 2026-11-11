"""Персональные ссылки партнёра."""
import re
from urllib.parse import quote

from .config import get_settings
from .models import Partner

START_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def start_payload(p: Partner) -> str:
    """Telegram разрешает в ?start= только латиницу, цифры, _ и -. Кириллическое слово заменяем на id."""
    if p.codeword and START_RE.match(p.codeword):
        return p.codeword
    return f"p{p.id}"


def partner_links(p: Partner) -> dict:
    s = get_settings()
    word = p.codeword or ""
    return {
        "tg": f"https://t.me/{s.bot_username}?start={start_payload(p)}",
        "wa": f"https://wa.me/{s.company_whatsapp}?text={quote('Здравствуйте! Я от ' + word)}",
        "ig": f"https://ig.me/m/{s.company_instagram}" if s.company_instagram else None,
        "text": f"Я от {word}",
    }
