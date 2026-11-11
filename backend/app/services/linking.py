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


def find_contacts(kommo: KommoClient, phone: str | None, username: str | None) -> list[int]:
    """Все контакты Kommo этого человека: по телефону и по нику Telegram. Первый — основной (больше сделок)."""
    ids: list[int] = []
    try:
        if phone:
            ids += kommo.find_contact_ids_by_phone(phone)
        if username:
            ids += [i for i in kommo.find_contact_ids_by_telegram(username) if i not in ids]
    except Exception:
        log.exception("Kommo: поиск контакта")
        return []
    if len(ids) <= 1:
        return ids
    contacts = {c.id: c for c in kommo.get_contacts(ids)}
    return sorted(ids, key=lambda i: -len(contacts[i].lead_ids) if i in contacts else 0)


def find_contact(kommo: KommoClient, phone: str | None, username: str | None) -> int | None:
    ids = find_contacts(kommo, phone, username)
    return ids[0] if ids else None


def link_user(db: Session, kommo: KommoClient, user: User, refresh: bool = False) -> bool:
    """Привязывает пользователя к контакту (и его дублям). refresh — пересобрать список дублей."""
    if user.kommo_contact_id and not refresh and user.kommo_extra_contact_ids is not None:
        return True
    ids = find_contacts(kommo, user.phone, user.telegram_username)
    if not ids and not user.kommo_contact_id:
        return False
    if not user.kommo_contact_id:
        user.kommo_contact_id = ids[0]
        log.info("Пользователь %s привязан к контакту %s", user.telegram_id, ids[0])
    user.kommo_extra_contact_ids = [i for i in ids if i != user.kommo_contact_id]
    db.commit()
    return True


def relink_unlinked(db: Session, kommo: KommoClient, limit: int = 100) -> int:
    users = db.scalars(select(User).where(User.kommo_contact_id.is_(None)).order_by(User.created_at.desc()).limit(limit))
    done = sum(1 for u in list(users) if (u.phone or u.telegram_username) and link_user(db, kommo, u))
    # Уже привязанные, у которых ещё не искали дубли
    for u in list(db.scalars(select(User).where(User.kommo_contact_id.is_not(None), User.kommo_extra_contact_ids.is_(None)).limit(limit))):
        link_user(db, kommo, u, refresh=True)
    return done
