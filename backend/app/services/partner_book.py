"""«Список партнеров»: дозаполнение пустых ячеек из Kommo и приложения.

На вход — xlsx с листом, где в A1 написано «ПАРТНЕР» (лист «Список партнеров» таблицы производства
или «Список партнеров (чистый)»). Колонки: A ПАРТНЕР, B Комментарий, C Контакт партнера, D Мессенджер,
E КЛЮЧЕВОЕ СЛОВО, F СЧЕТ, G БАНК, H ОТ КОГО. Заполняются только ПУСТЫЕ ячейки — написанное менеджером
не трогаем. Справа добавляются справочные колонки (телефон, Telegram, почта, приложение, ссылка на Kommo,
что проверить). Заполненное программой подсвечено жёлтым. Ничего не записывается ни в Kommo, ни в таблицу.
"""
from __future__ import annotations

import collections
import io
import logging
import re

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..kommo.base import KommoClient, KommoContact
from ..kommo.mapping import LEAD_FIELDS, NO_PARTNER_VALUES
from ..models import Level2Link, Partner, PartnerCodeword, User
from .cabinet import field_value
from .intake import name_matches
from .partner import _TR, find_partner_by_value, norm

log = logging.getLogger(__name__)

EXTRA = ["Телефон", "Telegram", "Email", "В приложении", "Kommo", "Проверить"]
TG_FIELDS = ("Логин", "Профиль", "TG", "Telegram", "Телеграм")
YELLOW = PatternFill("solid", fgColor="FFF2A8")
SKIP_PREFIX = ("источник", "свой", "своя", "наша менеджер", "наша (tia")


def _nick(text: str) -> str:
    m = re.search(r"(?:t\.me/|@)([A-Za-z0-9_]{4,})", text or "")
    return m[1] if m else ""


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def _translit(text: str) -> str:
    return "".join(_TR.get(ch, ch) for ch in (text or "").lower())


def contact_url(contact_id: int) -> str:
    base = get_settings().kommo_base_url.rstrip("/")
    return f"{base}/contacts/detail/{contact_id}" if base else str(contact_id)


def _tg_of(c: KommoContact) -> str:
    for k in TG_FIELDS:
        v = c.fields.get(k)
        if isinstance(v, list):
            v = v[0] if v else ""
        v = str(v or "").strip()
        if v and not v.isdigit():
            return _nick(v) or v.lstrip("@").rstrip("/").split("/")[-1]
    return ""


def _email_of(c: KommoContact) -> str:
    v = c.fields.get("code:EMAIL") or []
    return str(v[0]) if isinstance(v, list) and v else (str(v) if v else "")


def _find_contacts(kommo: KommoClient, name: str, nick: str, phone: str, user: User | None) -> tuple[list[int], str]:
    """ID контактов Kommo и чем нашли."""
    if user and user.kommo_contact_id:
        return [user.kommo_contact_id], "приложение"
    if nick:
        ids = kommo.find_contact_ids_by_telegram(nick)
        if ids:
            return ids, "ник Telegram"
    if len(phone) >= 9:
        ids = kommo.find_contact_ids_by_phone(phone)
        if ids:
            return ids, "телефон"
    words = [w for w in re.split(r"\s+", re.sub(r"\(.*?\)", "", name)) if len(w) >= 3 and w.isalpha()]
    if len(words) >= 2:  # «Фамилия Имя» — по одному слову не ищем, слишком много совпадений
        q = " ".join(words)
        found: dict[int, KommoContact] = {}
        for query in dict.fromkeys([q, _translit(q)]):
            for c in kommo.search_contacts(query, limit=20):
                if name_matches(q, [str(field_value(c.fields, "Имя Фамилия") or ""), c.name]):
                    found[c.id] = c
        if found:
            return list(found), "имя"
    return [], ""


def _came_from(db: Session, kommo: KommoClient, partner: Partner | None, contact: KommoContact | None) -> str:
    """Кто привёл этого партнёра: 2-й уровень из приложения, иначе поле «Партнёр» в его собственных сделках."""
    if partner:
        link = db.scalar(select(Level2Link).where(Level2Link.business_partner_id == partner.id))
        if link:
            lp = db.get(Partner, link.level2_partner_id)
            if lp:
                return lp.display_name.upper()
    if not contact or not contact.lead_ids:
        return ""
    values = collections.Counter()
    for lead in kommo.get_leads(contact.lead_ids[:30]):
        v = field_value(lead.fields, LEAD_FIELDS["partner"])
        if v and norm(str(v)) not in NO_PARTNER_VALUES:
            values[str(v).strip()] += 1
    if not values:
        return ""
    raw = values.most_common(1)[0][0]
    p = find_partner_by_value(db, raw)
    if p and partner and p.id == partner.id:
        return ""
    return (p.display_name if p else raw).upper()


def _app_match(db: Session, name: str, keyword: str, nick: str, phone: str) -> tuple[Partner | None, User | None]:
    partner = None
    for v in (keyword, nick, name):
        if v and not partner:
            partner = find_partner_by_value(db, v)
    if partner:
        return partner, partner.user
    user = None
    if nick:
        user = db.scalar(select(User).where(User.telegram_username.ilike(nick)))
    if not user and len(phone) >= 9:
        for u in db.scalars(select(User).where(User.phone.is_not(None))):
            if _digits(u.phone)[-9:] == phone[-9:]:
                user = u
                break
    return (user.partner if user else None), user


def enrich(db: Session, kommo: KommoClient, data: bytes) -> tuple[bytes, dict]:
    wb = load_workbook(io.BytesIO(data))
    ws = next((s for s in wb.worksheets if str(s.cell(1, 1).value or "").strip().upper() == "ПАРТНЕР"), None)
    if ws is None:
        raise ValueError("Не нашла лист, где в ячейке A1 написано «ПАРТНЕР»")
    headers = {str(ws.cell(1, i).value or "").strip(): i for i in range(1, ws.max_column + 1)}
    last = max(i for h, i in headers.items() if h) if any(headers) else 8
    col = {}
    for h in EXTRA:
        if h not in headers:
            last += 1
            ws.cell(1, last, h).font = Font(bold=True)
            headers[h] = last
        col[h] = headers[h]

    stats = collections.Counter()
    extra_words: dict[int, list[str]] = collections.defaultdict(list)
    for w in db.scalars(select(PartnerCodeword)):
        extra_words[w.partner_id].append(w.word)

    def put(r: int, c: int, value, mark: bool = True) -> None:
        cell = ws.cell(r, c)
        if value and str(cell.value or "").strip() == "":
            cell.value = value
            if mark:
                cell.fill = YELLOW
            stats["filled"] += 1

    for r in range(2, ws.max_row + 1):
        name = str(ws.cell(r, 1).value or "").strip()
        comment = str(ws.cell(r, 2).value or "")
        if not name or comment.strip().lower().startswith(SKIP_PREFIX):
            continue
        stats["rows"] += 1
        contact_cell = str(ws.cell(r, 3).value or "")
        keyword = str(ws.cell(r, 5).value or "").strip()
        nick = _nick(contact_cell) or _nick(name)
        phone = "" if nick else _digits(contact_cell)
        notes: list[str] = []
        try:
            partner, user = _app_match(db, name, keyword, nick, phone)
            ids, how = _find_contacts(kommo, name, nick, phone, user)
            contact = None
            if len(ids) == 1:
                contact = kommo.get_contact(ids[0])
            elif len(ids) > 1:
                notes.append(f"в Kommo {len(ids)} похожих ({how}): " + ", ".join(contact_url(i) for i in ids[:4]))
            elif not partner and not user:
                notes.append("не нашла ни в Kommo, ни в приложении")

            tg = (user.telegram_username if user and user.telegram_username else "") or (_tg_of(contact) if contact else "") or nick
            tel = (contact.phones[0] if contact and contact.phones else "") or (user.phone if user and user.phone else "")
            put(r, col["Телефон"], tel, mark=False)
            put(r, col["Telegram"], f"t.me/{tg}" if tg else "", mark=False)
            put(r, col["Email"], _email_of(contact) if contact else "", mark=False)
            if partner:
                words = [partner.codeword or ""] + extra_words.get(partner.id, [])
                put(r, col["В приложении"], "партнёр: " + ", ".join(w for w in words if w), mark=False)
                stats["in_app"] += 1
            elif user:
                put(r, col["В приложении"], "в боте, не партнёр", mark=False)
            if contact:
                put(r, col["Kommo"], contact_url(contact.id), mark=False)
                stats["in_kommo"] += 1
                if how == "имя":
                    notes.append("найден по имени — сверьте")

            # основные колонки — только пустые
            put(r, 3, f"t.me/{tg}" if tg else (("+" + _digits(tel)) if tel else ""))
            put(r, 4, "TG" if tg else ("WA" if tel else ""))
            if partner and partner.codeword:
                put(r, 5, partner.codeword.upper())
            if partner and partner.payout_details:
                put(r, 6, partner.payout_details)
            put(r, 8, _came_from(db, kommo, partner, contact))
        except Exception as e:  # одна строка не должна ломать весь файл
            log.warning("partner_book row %s: %s", r, e)
            notes.append(f"ошибка: {e}")
        if notes:
            put(r, col["Проверить"], "; ".join(notes), mark=False)
            ws.cell(r, col["Проверить"]).alignment = Alignment(wrap_text=True)
            stats["check"] += 1

    for h in EXTRA:
        ws.column_dimensions[ws.cell(1, col[h]).column_letter].width = 40 if h in ("Kommo", "Проверить") else 20
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), dict(stats)


def main() -> None:  # python -m app.services.partner_book IN.xlsx OUT.xlsx
    import sys

    from ..db import SessionLocal
    from ..kommo import get_kommo

    src, dst = sys.argv[1], sys.argv[2]
    with SessionLocal() as db, open(src, "rb") as f:
        data, stats = enrich(db, get_kommo(), f.read())
    with open(dst, "wb") as f:
        f.write(data)
    print(stats)


if __name__ == "__main__":
    main()
