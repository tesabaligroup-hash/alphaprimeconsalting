"""«Узнать подробнее» / «Хочу пойти»: сделка в Kommo (Consulting → Распределение) + сообщение менеджерам.

Общее для кнопки в новости (приложение) и в виджете «Мероприятия» (чат с ботом).
"""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..kommo.base import KommoClient
from ..models import News, ServiceOrder, User
from ..notify import notify_managers
from ..timeutil import utcnow

log = logging.getLogger(__name__)


def register_interest(db: Session, kommo: KommoClient, user: User, n: News, where: str = "приложении") -> bool:
    """True — заявка создана; False — такая же уже была в последний час (повторно не шлём)."""
    code = f"news:{n.id}"
    recent = db.scalar(select(ServiceOrder).where(ServiceOrder.user_id == user.id, ServiceOrder.service_code == code,
                                                  ServiceOrder.created_at > utcnow() - timedelta(hours=1)))
    if recent:
        return False
    tg = f"@{user.telegram_username}" if user.telegram_username else f"id {user.telegram_id}"
    lead_id = None
    try:
        lead_id = kommo.create_lead(
            title=f"Интерес из приложения: {n.title}", contact_name=user.first_name or "Клиент из приложения",
            phone=user.phone, telegram=tg, contact_id=user.kommo_contact_id,
            note=f"Клиент нажал «Узнать подробнее» по новости «{n.title}» в {where}.",
            tags=["Приложение", "Новость"],
        )
    except Exception:
        log.exception("Kommo: не удалось создать сделку по новости")
    db.add(ServiceOrder(user_id=user.id, service_code=code, kommo_lead_id=lead_id))
    db.commit()
    notify_managers("📣 Интерес к новости", [
        f"Новость: {n.title}",
        f"Клиент: {user.first_name or '—'} · {tg}" + (f" · {user.phone}" if user.phone else ""),
        f"Откуда: {where}",
        "Уже есть в Kommo" if user.kommo_contact_id else "Новый клиент (в Kommo создан контакт)",
    ], lead_id)
    return True
