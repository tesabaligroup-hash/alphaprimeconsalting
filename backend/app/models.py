"""Таблицы базы данных приложения.

Сделки, этапы, оплаты и файлы клиентов живут в Kommo — здесь их нет.
Здесь хранится только то, чего в Kommo нет: пользователи Telegram, партнёры,
рекомендации, начисления, выплаты, новости и настройки программы.
"""
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    """Человек, открывший бота / приложение в Telegram."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    kommo_contact_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    # Дубли того же человека в Kommo (тот же телефон / Telegram): данные из них тоже показываем
    kommo_extra_contact_ids: Mapped[list | None] = mapped_column(JSON)
    language: Mapped[str] = mapped_column(String(2), default="ru")
    notify_partner_offers: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_company_offers: Mapped[bool] = mapped_column(Boolean, default=True)
    # Кодовое слово партнёра, по которому человек пришёл (до первой оплаты)
    came_with_codeword: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    partner: Mapped["Partner | None"] = relationship(back_populates="user", uselist=False)

    @property
    def contact_ids(self) -> list[int]:
        if not self.kommo_contact_id:
            return []
        return [self.kommo_contact_id] + [int(x) for x in (self.kommo_extra_contact_ids or []) if int(x) != self.kommo_contact_id]


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    # private — частный (план A), business — бизнес (план B), level2 — партнёр 2-го уровня (план B)
    kind: Mapped[str] = mapped_column(String(16), default="private")
    display_name: Mapped[str] = mapped_column(String(128))
    codeword: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    # Как этот партнёр называется в поле «Партнёр» в Kommo (для связи сделок)
    kommo_partner_value: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / inactive / blocked
    gold_until: Mapped[date | None] = mapped_column(Date)
    payout_details: Mapped[str | None] = mapped_column(Text)  # реквизиты, свободный текст
    accepted_terms_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="partner")

    @property
    def plan(self) -> str:
        return "A" if self.kind == "private" else "B"

    def is_gold(self, today: date) -> bool:
        return bool(self.gold_until and self.gold_until >= today)


class Level2Link(Base):
    """Партнёр 2-го уровня ↔ бизнес-партнёр, с которым он познакомил Alpha Prime (24 мес.)."""

    __tablename__ = "level2_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    level2_partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"))
    business_partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), unique=True)
    contract_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)


class Referral(Base):
    """Рекомендация: друг, которого партнёр внёс вручную или который пришёл по ссылке/слову."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), index=True)
    friend_name: Mapped[str] = mapped_column(String(128))
    channel: Mapped[str] = mapped_column(String(8))  # tg / wa / ig
    contact: Mapped[str] = mapped_column(String(128))
    who_writes: Mapped[str] = mapped_column(String(8), default="self")  # self — друг напишет сам, us — пишет менеджер
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual / link / codeword
    # pending — на проверке, attached — закреплён, rejected — отклонён, expired — истёк
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255))
    kommo_contact_id: Mapped[int | None] = mapped_column(BigInteger)
    kommo_lead_id: Mapped[int | None] = mapped_column(BigInteger)
    friend_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    attached_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)  # +90 дней, если не оплатил
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    partner: Mapped[Partner] = relationship()


class Accrual(Base):
    """Начисление партнёру за конкретную сделку Kommo."""

    __tablename__ = "accruals"
    __table_args__ = (UniqueConstraint("kommo_lead_id", "partner_id", "level", "period", name="uq_accrual"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)  # 1 или 2
    kommo_lead_id: Mapped[int] = mapped_column(BigInteger, index=True)
    period: Mapped[str] = mapped_column(String(16), default="")  # для ежемесячных услуг: 2026-11
    client_display: Mapped[str] = mapped_column(String(128))  # «Мария К.» — без паспортных данных
    service_code: Mapped[str | None] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(BigInteger, default=0)  # IDR
    # awaiting_payment / in_work / confirmed / to_payout / paid / cancelled
    status: Mapped[str] = mapped_column(String(20), default="awaiting_payment", index=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    fully_paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    result_issued_at: Mapped[datetime | None] = mapped_column(DateTime)
    hold_until: Mapped[datetime | None] = mapped_column(DateTime)
    to_payout_at: Mapped[datetime | None] = mapped_column(DateTime)
    payout_id: Mapped[int | None] = mapped_column(ForeignKey("payouts.id"))
    manual_code: Mapped[str | None] = mapped_column(String(32))  # услугу указал менеджер (в Kommo «Другое»/пусто)
    decision: Mapped[str | None] = mapped_column(String(16))  # решение менеджера: approved / paid / rejected
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), index=True)
    payout_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    bonus_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    deduction_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    receipt_path: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="planned")  # planned / sent
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class News(Base):
    """Новость или баннер. kind: company — Alpha Prime, partner — от партнёров."""

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str | None] = mapped_column(String(64), unique=True)  # для новостей из backend/content/news.json
    kind: Mapped[str] = mapped_column(String(16), default="company")
    is_banner: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    partner_name: Mapped[str | None] = mapped_column(String(128))
    image_path: Mapped[str | None] = mapped_column(String(255))
    link_url: Mapped[str | None] = mapped_column(String(512))
    cta_lead: Mapped[bool] = mapped_column(Boolean, default=False)  # кнопка «Узнать подробнее» → заявка менеджерам
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StopWord(Base):
    """Слова, которые нельзя занять как кодовое слово."""

    __tablename__ = "stop_words"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(32), unique=True)


class ServiceOrder(Base):
    """Заявка «Заказать» из каталога услуг."""

    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    service_code: Mapped[str] = mapped_column(String(32))
    kommo_lead_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProgramSetting(Base):
    """Настраиваемые параметры партнёрской программы (значения по умолчанию — в partner_rules.DEFAULTS)."""

    __tablename__ = "program_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WidgetMessage(Base):
    """Виджет, отправленный ботом в личный чат (Telegram Widgets): его обновляем, когда меняются данные."""

    __tablename__ = "widget_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # visa / events / partner
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    state_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
