"""Telegram-бот + фоновая синхронизация начислений из Kommo (отдельный процесс).

Запуск:  python -m app.worker
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, MenuButtonWebApp,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo)
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .kommo import get_kommo
from .models import Partner, Referral, User
from .partner_rules import DEFAULTS, normalize_codeword
from .services.linking import find_contact, link_user, relink_unlinked
from .services.partner import sync_all
from .notify import notify_managers
from .timeutil import utcnow

log = logging.getLogger("worker")
settings = get_settings()
dp = Dispatcher()

SYNC_EVERY_MINUTES = 10


def app_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть личный кабинет",
                                                                       web_app=WebAppInfo(url=settings.public_url))]])


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
                               resize_keyboard=True, one_time_keyboard=True)


def resolve_partner(db, payload: str | None) -> Partner | None:
    if not payload:
        return None
    if re.fullmatch(r"p\d{1,9}", payload):
        return db.get(Partner, int(payload[1:]))
    return db.scalar(select(Partner).where(Partner.codeword == normalize_codeword(payload)))


@dp.message(CommandStart())
async def start(message: Message, command: CommandObject):
    tg = message.from_user
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == tg.id))
        if not user:
            user = User(telegram_id=tg.id, first_name=tg.first_name, telegram_username=tg.username)
            db.add(user)
            db.flush()
        partner = resolve_partner(db, command.args)
        if partner and partner.user_id != user.id and partner.status == "active" and not user.kommo_contact_id:
            already = db.scalar(select(Referral).where(Referral.friend_user_id == user.id))
            if not already:
                user.came_with_codeword = partner.codeword
                db.add(Referral(partner_id=partner.id, friend_name=" ".join(x for x in [tg.first_name, tg.last_name] if x),
                                channel="tg", contact=f"@{tg.username}" if tg.username else f"id {tg.id}", who_writes="us",
                                source="link", status="pending", friend_user_id=user.id,
                                expires_at=utcnow() + timedelta(days=DEFAULTS["referral_days"])))
        db.commit()
        if not user.kommo_contact_id and tg.username:
            await asyncio.to_thread(link_user, db, get_kommo(), user)
        has_phone = bool(user.phone)
    text = (f"Здравствуйте, {tg.first_name or ''}! Это Alpha Prime — визы, KITAS и компании на Бали.\n\n"
            "Здесь ваш личный кабинет: этапы оформления, оплаты, готовые документы и партнёрская программа.")
    if not has_phone:
        await message.answer(text + "\n\nЧтобы мы нашли ваши услуги, поделитесь номером телефона — кнопка ниже.",
                             reply_markup=phone_keyboard())
    await message.answer("Личный кабинет открывается по кнопке:", reply_markup=app_keyboard())


@dp.message(Command("chatid"))
async def chat_id(message: Message):
    """Напишите /chatid в группе менеджеров — бот ответит её номером для MANAGERS_CHAT_ID."""
    await message.answer(f"ID этого чата: {message.chat.id}\nВпишите его в .env как MANAGERS_CHAT_ID и перезапустите сервер.")


@dp.message(F.contact)
async def got_contact(message: Message):
    c = message.contact
    if c.user_id != message.from_user.id:
        await message.answer("Пожалуйста, отправьте свой номер кнопкой «Поделиться номером».", reply_markup=phone_keyboard())
        return
    phone = "+" + re.sub(r"\D", "", c.phone_number)
    kommo = get_kommo()
    try:
        ids = await asyncio.to_thread(kommo.find_contact_ids_by_phone, phone)
    except Exception:
        log.exception("Kommo: поиск по телефону")
        ids = []
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == message.from_user.id))
        if not user:
            user = User(telegram_id=message.from_user.id, first_name=message.from_user.first_name,
                        telegram_username=message.from_user.username)
            db.add(user)
            db.flush()
        user.phone = phone
        if not user.kommo_contact_id:
            user.kommo_contact_id = await asyncio.to_thread(find_contact, kommo, phone, user.telegram_username)
        # Пришёл по ссылке партнёра: нового человека закрепляем сразу, знакомого CRM — оставляем на проверку менеджеру
        ref = db.scalar(select(Referral).where(Referral.friend_user_id == user.id, Referral.status == "pending", Referral.source == "link"))
        if ref:
            ref.contact = f"{ref.contact} · {phone}"
            if not ids:
                ref.status, ref.attached_at = "attached", utcnow()
                partner = db.get(Partner, ref.partner_id)
                try:
                    ref.kommo_lead_id = await asyncio.to_thread(
                        kommo.create_lead, title=f"Рекомендация: {ref.friend_name}", contact_name=ref.friend_name, phone=phone,
                        telegram=ref.contact, tags=["Партнёрка", "Приложение"],
                        note=f"Пришёл по ссылке партнёра {partner.display_name} ({partner.codeword}). "
                             f"В поле «Партнёр» укажите: {partner.kommo_partner_value or partner.codeword}")
                except Exception:
                    log.exception("Kommo: создание сделки по рекомендации")
                await asyncio.to_thread(notify_managers, "🤝 Клиент пришёл по ссылке партнёра", [
                    f"Партнёр: {partner.display_name} ({partner.codeword})",
                    f"Клиент: {ref.friend_name} · {ref.contact}",
                    "Закреплён автоматически — напишите клиенту",
                ], ref.kommo_lead_id)
            else:
                ref.reject_reason = None  # менеджер увидит её в «Рекомендации → На проверке»
        db.commit()
        linked = bool(user.kommo_contact_id)
    if linked:
        await message.answer("Спасибо! Мы нашли ваши услуги — откройте личный кабинет.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("Спасибо! Номер сохранён. Если у вас уже есть услуги в Alpha Prime, менеджер подключит их к кабинету.",
                             reply_markup=ReplyKeyboardRemove())
    await message.answer("Личный кабинет:", reply_markup=app_keyboard())


@dp.message(F.chat.type == "private")
async def fallback(message: Message):
    await message.answer(f"Чтобы написать менеджеру, используйте WhatsApp: https://wa.me/{settings.company_whatsapp}\n"
                         "Личный кабинет — по кнопке ниже.", reply_markup=app_keyboard())


async def sync_loop(bot: Bot):
    kommo = get_kommo()
    last = utcnow() - timedelta(days=400)  # первый запуск — за всё время
    full_at = utcnow()
    while True:
        started = utcnow()
        if started - full_at > timedelta(hours=1):
            # раз в час — все сделки заново: новый партнёр или исправленное поле «Партнёр» подхватят и старые сделки
            last, full_at = started - timedelta(days=400), started
        try:
            with SessionLocal() as db:
                linked = await asyncio.to_thread(relink_unlinked, db, kommo)
                if linked:
                    log.info("Привязано новых клиентов: %s", linked)
                notes = await asyncio.to_thread(sync_all, db, kommo, last - timedelta(minutes=5))
                partners = {p.id: p.user.telegram_id for p in db.scalars(select(Partner))}
            for partner_id, text in notes:
                tg_id = partners.get(partner_id)
                if tg_id:
                    try:
                        await bot.send_message(tg_id, text, reply_markup=app_keyboard())
                    except Exception:
                        log.warning("Не удалось отправить уведомление партнёру %s", partner_id)
            last = started
            log.info("Синхронизация: %s уведомлений", len(notes))
        except Exception:
            log.exception("Синхронизация с Kommo не удалась")
        await asyncio.sleep(SYNC_EVERY_MINUTES * 60)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан")
    bot = Bot(settings.bot_token)
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Кабинет", web_app=WebAppInfo(url=settings.public_url)))
    except Exception:
        log.warning("Не удалось установить кнопку меню (проверьте PUBLIC_URL — нужен https)")
    asyncio.create_task(sync_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
