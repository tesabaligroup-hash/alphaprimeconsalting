"""«Мои визы»: человек сам вписывает визу и дату окончания — бот напоминает о продлении.

Работает и для тех, кто не наш клиент: так мы узнаём, у кого скоро заканчивается виза, и предлагаем продление.
Наши клиенты получают те же напоминания по датам из Kommo («Виза до», «ITK до»).
Напоминания: за 20, 15 и 7 дней (одно сообщение на порог). За 20 дней — сигнал в группу менеджеров.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..kommo.base import KommoClient
from ..models import ReminderSent, User, UserVisa
from . import cabinet

THRESHOLDS = (20, 15, 7)
MANAGERS_AT = 20
VISA_TYPES = [
    "VOA (виза по прилёту)", "C1 (туристическая 60 дней)", "D1 (мультивиза)", "D12 (бизнес мультивиза)",
    "Bridge Visa", "KITAS удалёнщика E33G", "KITAS инвестора E28A", "Family KITAS (E31)",
    "Пенсионный KITAS (E33F)", "Рабочий KITAS", "Другая виза", "Паспорт",
]


@dataclass
class DueDate:
    key: str  # уникально для даты: manual:<id> / kommo:<user>:<title>:<date>
    user: User
    title: str
    person: str
    expires_on: date
    days_left: int
    manual_id: int | None
    is_client: bool


def manual_dates(db: Session, user: User, today: date | None = None) -> list[dict]:
    """Добавленные вручную — в формате важных дат главного экрана."""
    today = today or date.today()
    out = []
    for v in db.scalars(select(UserVisa).where(UserVisa.user_id == user.id).order_by(UserVisa.expires_on)):
        left = (v.expires_on - today).days
        if left < 0:
            continue
        kind = "passport" if v.visa_type == "Паспорт" else "expiry"
        title = "Окончание паспорта" if kind == "passport" else f"Окончание: {v.visa_type}"
        out.append({"date": v.expires_on.isoformat(), "title": title, "person": v.person or (user.first_name or "Вы"),
                    "lead_id": None, "kind": kind, "days_left": left, "manual_id": v.id})
    return out


def merge_dates(kommo_dates: list[dict], manual: list[dict]) -> list[dict]:
    """Kommo-даты важнее: ручную с той же датой и человеком не дублируем."""
    seen = {(d["date"], d["person"].lower()) for d in kommo_dates}
    out = kommo_dates + [m for m in manual if (m["date"], m["person"].lower()) not in seen]
    return sorted(out, key=lambda d: d["date"])[:6]


def upcoming(db: Session, kommo: KommoClient, today: date | None = None) -> list[DueDate]:
    """Все даты в ближайшие 20 дней — и ручные, и из Kommo (для наших клиентов)."""
    today = today or date.today()
    horizon = max(THRESHOLDS)
    out: list[DueDate] = []
    for v in db.scalars(select(UserVisa).where(UserVisa.expires_on >= today)):
        left = (v.expires_on - today).days
        if left <= horizon:
            u = db.get(User, v.user_id)
            if u:
                out.append(DueDate(f"manual:{v.id}", u, v.visa_type, v.person or (u.first_name or ""), v.expires_on, left,
                                   v.id, bool(u.kommo_contact_id)))
    for u in db.scalars(select(User).where(User.kommo_contact_id.is_not(None))):
        try:
            data = cabinet.load_client(kommo, u.contact_ids, with_history=False)
        except Exception:
            continue
        for d in data["dates"]:
            if d.get("kind") in ("expiry", "passport") and d["days_left"] <= horizon:
                out.append(DueDate(f"kommo:{u.id}:{d['title']}:{d['date']}", u, d["title"].replace("Окончание ", ""),
                                   d.get("person") or "", date.fromisoformat(d["date"]), d["days_left"], None, True))
    return out


def threshold_for(days_left: int) -> int | None:
    """Самый «узкий» достигнутый порог: 18 дней → 20, 10 дней → 15, 3 дня → 7."""
    hit = [t for t in THRESHOLDS if days_left <= t]
    return min(hit) if hit and days_left >= 0 else None


def was_sent(db: Session, key: str) -> bool:
    return db.get(ReminderSent, key) is not None


def mark_sent(db: Session, key: str) -> None:
    if not was_sent(db, key):
        db.add(ReminderSent(key=key[:160]))


def reminder_text(d: DueDate) -> str:
    who = f" ({d.person})" if d.person and d.person != (d.user.first_name or "") else ""
    when = d.expires_on.strftime("%d.%m.%Y")
    return (f"⏰ Напоминание Alpha Prime\n\n{d.title}{who} заканчивается {when} — через {d.days_left} дн.\n\n"
            "Продление лучше начать заранее: часть виз нужно подавать до окончания срока. "
            "Нажмите кнопку — менеджер напишет вам и всё расскажет.")
