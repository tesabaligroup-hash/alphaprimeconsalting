"""Тестовые данные для режима разработки (DEV_MODE=true): партнёр ANNABALI, рекомендации, новости."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .kommo import get_kommo
from .models import News, Partner, Referral, User
from .services.partner import sync_all
from .timeutil import utcnow


def seed_dev(db: Session) -> None:
    user = db.scalar(select(User).where(User.telegram_id == 1))
    if not user:
        user = User(telegram_id=1, first_name="Анна", telegram_username="anna_demo", phone="+6281200000001", kommo_contact_id=501)
        db.add(user)
        db.flush()
    if not user.partner:
        p = Partner(user_id=user.id, kind="private", display_name="Анна", codeword="ANNABALI", kommo_partner_value="ANNABALI",
                    accepted_terms_at=utcnow())
        db.add(p)
        db.flush()
        now = utcnow()
        db.add_all([
            Referral(partner_id=p.id, friend_name="Иван Васильев", channel="tg", contact="@ivan_v", who_writes="us", status="pending",
                     expires_at=now + timedelta(days=90)),
            Referral(partner_id=p.id, friend_name="Света Тихонова", channel="wa", contact="+62 812 555 0101", who_writes="self",
                     status="pending", expires_at=now + timedelta(days=14)),
            Referral(partner_id=p.id, friend_name="Алексей Б.", channel="ig", contact="@alex_b", who_writes="self", status="rejected",
                     reject_reason="Клиент закреплён за другим партнёром"),
        ])
    if not db.scalar(select(News)):
        db.add_all([
            News(kind="company", is_banner=True, title="[Акция или важное объявление]", body="Баннер загружается из админки", sort_order=0),
            News(kind="company", title="График работы офиса в декабрьские праздники", sort_order=1),
            News(kind="company", title="[Заголовок новости: изменения по визам]", sort_order=2),
            News(kind="partner", title="[Спецпредложение для клиентов Alpha Prime]", partner_name="Top Gym", sort_order=0),
            News(kind="partner", title="[Спецпредложение для клиентов Alpha Prime]", partner_name="[Коворкинг-партнёр]", sort_order=1),
        ])
    db.commit()
    sync_all(db, get_kommo(), utcnow() - timedelta(days=400))
