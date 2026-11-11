"""Привязка пользователя Telegram к контакту Kommo.

Ищем по номеру телефона, а если не нашли — по нику Telegram (Kommo сохраняет его в полях «Логин» / «Профиль»).
Если найдено несколько контактов (дубли), берём тот, у которого больше сделок.
Пользователей без привязки периодически проверяем снова: клиента могли добавить в CRM позже.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..kommo.base import KommoClient
from ..models import User

log = logging.getLogger(__name__)


def find_contact(kommo: KommoClient, phone: str | None, username: str | None) -> int | None:
    ids: list[int] = []
    try:
        if phone:
            ids = kommo.find_contact_ids_by_phone(phone)
        if not ids and username:
            ids = kommo.find_contact_ids_by_telegram(username)
    except Exception:
        log.exception("Kommo: поиск контакта")
        return None
    if not ids:
        return None
    if len(ids) == 1:
        return ids[0]
    contacts = kommo.get_contacts(ids)
    best = max(contacts, key=lambda c: len(c.lead_ids), default=None)
    return best.id if best else ids[0]


def link_user(db: Session, kommo: KommoClient, user: User) -> bool:
    if user.kommo_contact_id:
        return True
    cid = find_contact(kommo, user.phone, user.telegram_username)
    if cid:
        user.kommo_contact_id = cid
        db.commit()
        log.info("Пользователь %s привязан к контакту %s", user.telegram_id, cid)
        return True
    return False


def relink_unlinked(db: Session, kommo: KommoClient, limit: int = 100) -> int:
    users = db.scalars(select(User).where(User.kommo_contact_id.is_(None)).order_by(User.created_at.desc()).limit(limit))
    return sum(1 for u in list(users) if (u.phone or u.telegram_username) and link_user(db, kommo, u))
