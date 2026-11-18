"""Чтение документов клиента ИИ (Claude): паспорт, фото, виза/ITK. Ключ — ANTHROPIC_API_KEY в .env."""
import base64
import json
import logging
import re

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}

PROMPT = """Это документ клиента визового агентства на Бали. Определи, что это, и верни ТОЛЬКО JSON без пояснений:
{"doc_type": "passport" | "photo" | "visa" | "itk" | "other",
 "full_name": "ИМЯ ФАМИЛИЯ латиницей как в документе или null",
 "passport_number": null, "nationality": null, "birth_date": "YYYY-MM-DD или null",
 "passport_expiry": "YYYY-MM-DD или null",
 "visa_type": "код/название визы, например E33G, C1, KITAS Investor, или null",
 "visa_expiry": "YYYY-MM-DD — до какого числа действует виза/ITK, или null",
 "note": "одна короткая фраза по-русски, если что-то не так (плохо видно, обрезано), иначе null"}
doc_type: passport — страница паспорта с фото; photo — фото человека на фоне (для визы); visa — e-Visa/виза;
itk — ITK/ITAS/KITAS/KITAP (разрешение на пребывание, обычно синий документ); visa — e-Visa/виза (обычно белая);
other — всё остальное (чеки, договоры, справки, черновики анкет).
Не выдумывай: чего не видно — null."""


def sniff(data: bytes) -> str | None:
    """Тип файла по содержимому (в Kommo у файлов часто нет расширения: «personal», «file», «Паспорт загран»)."""
    head = data[:16]
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def mime_for(name: str, data: bytes | None = None) -> str | None:
    if data:
        m = sniff(data)
        if m:
            return m
    n = (name or "").lower()
    if n.endswith(".pdf"):
        return "application/pdf"
    return next((m for ext, m in IMAGE_TYPES.items() if n.endswith(ext)), None)


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def read_document(data: bytes, name: str) -> dict:
    """Сначала дешёвая модель; если она не разобрала документ или имя — сильная."""
    s = get_settings()
    out = _read(data, name, s.ai_model)
    weak = out.get("doc_type") == "unknown" or (out.get("doc_type") in ("passport", "visa", "itk") and not out.get("full_name"))
    if weak and s.ai_model_strong and s.ai_model_strong != s.ai_model and not str(out.get("note", "")).startswith(("формат", "файл больше", "нет ключа")):
        better = _read(data, name, s.ai_model_strong)
        if better.get("doc_type") != "unknown":
            return better
    return out


def _read(data: bytes, name: str, model: str) -> dict:
    """{"doc_type": …, …}. Если файл не читается (формат, размер, нет ключа) — {"doc_type": "unknown", "note": …}."""
    s = get_settings()
    mime = mime_for(name, data)
    if not mime:
        return {"doc_type": "unknown", "note": "формат файла не читается (нужен PDF/JPG/PNG; фото HEIC — пересохранить в JPG)"}
    if len(data) > MAX_BYTES:
        return {"doc_type": "unknown", "note": "файл больше 10 МБ"}
    if not s.anthropic_api_key:
        return {"doc_type": "unknown", "note": "нет ключа ИИ (ANTHROPIC_API_KEY)"}
    b64 = base64.b64encode(data).decode()
    block = ({"type": "document", "source": {"type": "base64", "media_type": mime, "data": b64}} if mime == "application/pdf"
             else {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=90,
                       headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01",
                                "content-type": "application/json"},
                       json={"model": model, "max_tokens": 600,
                             "messages": [{"role": "user", "content": [block, {"type": "text", "text": PROMPT}]}]})
        r.raise_for_status()
        text = "".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text")
    except Exception as exc:  # сеть/лимиты — заявка всё равно создастся, просто без распознавания
        log.warning("ИИ не прочитал %s: %s", name, exc)
        return {"doc_type": "unknown", "note": "ИИ не смог прочитать файл"}
    out = _parse(text)
    out.setdefault("doc_type", "unknown")
    return out
