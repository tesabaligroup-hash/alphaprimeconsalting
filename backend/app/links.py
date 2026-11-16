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


# Менеджеры Alpha Prime: WhatsApp +62 815-1984-5777 (COMPANY_WHATSAPP) и Telegram @alpha_prime_id.
# Партнёрские ссылки и QR ведут только сюда — не в бота и не на настройки из .env.
MANAGERS_TELEGRAM = "alpha_prime_id"
MANAGERS_WHATSAPP = "6281519845777"


def partner_links(p: Partner, word: str | None = None) -> dict:
    """Ссылки и QR ведут прямо в чат с менеджерами (WhatsApp / Telegram) с готовым сообщением «Я от СЛОВО».
    Менеджер видит слово и ставит партнёра в поле «Партнёр» в Kommo (или бот подскажет: /kod СЛОВО)."""
    s = get_settings()
    w = word or p.codeword or ""
    hello = quote("Здравствуйте! Я от " + w)
    return {
        "tg": f"https://t.me/{MANAGERS_TELEGRAM}?text={hello}",
        "wa": f"https://wa.me/{MANAGERS_WHATSAPP}?text={hello}",
        "ig": f"https://ig.me/m/{s.company_instagram}" if s.company_instagram else None,
        "text": f"Я от {w}",
    }
