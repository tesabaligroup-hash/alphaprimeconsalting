"""Telegram-бот + фоновая синхронизация начислений из Kommo (отдельный процесс).

Запуск:  python -m app.worker
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, BotCommandScopeAllPrivateChats, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, MenuButtonWebApp,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo)
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .kommo import get_kommo
from .models import ProgramSetting, Partner, Referral, User
from .partner_rules import DEFAULTS, normalize_codeword
from .services.linking import find_contact, link_user, relink_unlinked
from .services import partner as partner_svc
from .services.partner import sync_all
from .services.quality import weekly_report
from .notify import notify_managers
from .timeutil import utcnow
from . import widgets
from .services import intake as intake_svc
from .services import table_sync as table_svc
from .models import UserVisa
from .services import visas as visas_svc
from aiogram.types import CallbackQuery

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
    return partner_svc.partner_by_codeword(db, payload)


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
                word = normalize_codeword(command.args or "")
                user.came_with_codeword = word if getattr(partner_svc.partner_by_codeword(db, word), "id", None) == partner.id else partner.codeword
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


def is_managers_chat(message: Message) -> bool:
    return bool(settings.managers_chat_id) and str(message.chat.id) == str(settings.managers_chat_id)


@dp.message(Command("kod"))
async def check_codeword(message: Message, command: CommandObject):
    """/kod СЛОВО в группе менеджеров — чей это партнёр и что поставить в поле «Партнёр»."""
    if not is_managers_chat(message):
        return
    word = (command.args or "").strip().lstrip("@")
    if not word:
        await message.answer("Напишите так: /kod ANNABALI")
        return
    with SessionLocal() as db:
        code = normalize_codeword(word)
        p = partner_svc.partner_by_codeword(db, code) or \
            db.scalar(select(Partner).where(Partner.kommo_partner_value.ilike(word))) or \
            db.scalar(select(Partner).join(User, Partner.user_id == User.id).where(User.telegram_username.ilike(word)))
        if not p:
            await message.answer(f"❌ «{word}» — такого партнёра нет. Клиенту без скидки, в поле «Партнёр» — «Нет».")
            return
        value = p.kommo_partner_value or p.codeword
        if p.status != "active":
            await message.answer(f"⚠️ {p.display_name} — партнёр не активен ({p.status}). Скидку не даём, в поле «Партнёр» — «Нет».")
            return
        nick = f" · @{p.user.telegram_username}" if p.user and p.user.telegram_username else ""
        await message.answer(f"✅ Партнёр: {p.display_name}{nick}\nВ поле «Партнёр» в Kommo поставьте: {value}\n"
                             "Клиенту — цена со скидкой партнёра.")


@dp.message(Command("proverka"))
async def crm_check(message: Message):
    """/proverka в группе менеджеров — список сделок, где не хватает данных (то же, что по понедельникам)."""
    if not is_managers_chat(message):
        return
    await message.answer("Проверяю сделки, минуту…")
    text = await asyncio.to_thread(weekly_report, get_kommo())
    await message.answer(text or "✅ Всё заполнено.", parse_mode="HTML", disable_web_page_preview=True)


async def visa_reminders(bot: Bot, kommo) -> None:
    """Раз в день после 10:00 (Бали): напоминания о конце визы за 20/15/7 дней + сигнал менеджерам за 20 дней."""
    now = datetime.now(ZoneInfo(settings.timezone))
    if now.hour < 10:
        return
    today = now.date().isoformat()
    with SessionLocal() as db:
        row = db.get(ProgramSetting, "visa_reminders")
        if row and (row.value or {}).get("date") == today:
            return
        due = await asyncio.to_thread(visas_svc.upcoming, db, kommo, now.date())
        sent = 0
        for d in due:
            t = visas_svc.threshold_for(d.days_left)
            key = f"{d.key}:{t}"
            if t is None or visas_svc.was_sent(db, key):
                continue
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Продлить с Alpha Prime", callback_data=f"renew:{d.manual_id or 0}:{d.days_left}")],
                [InlineKeyboardButton(text="Открыть кабинет", web_app=WebAppInfo(url=settings.public_url))],
            ])
            try:
                await bot.send_message(d.user.telegram_id, visas_svc.reminder_text(d), reply_markup=kb)
                sent += 1
            except Exception as exc:
                log.warning("Напоминание %s не отправлено: %s", d.key, exc)
            for th in visas_svc.THRESHOLDS:  # пороги шире текущего тоже считаем пройденными
                if th >= t:
                    visas_svc.mark_sent(db, f"{d.key}:{th}")
            if t == visas_svc.MANAGERS_AT or (t < visas_svc.MANAGERS_AT and not visas_svc.was_sent(db, f"{d.key}:mgr")):
                u = d.user
                tg = f"@{u.telegram_username}" if u.telegram_username else f"id {u.telegram_id}"
                notify_managers("⏰ Скоро заканчивается виза", [
                    f"{d.title}" + (f" · {d.person}" if d.person else "") + f" — до {d.expires_on:%d.%m.%Y} ({d.days_left} дн.)",
                    f"Человек: {u.first_name or '—'} · {tg}" + (f" · {u.phone}" if u.phone else ""),
                    "Наш клиент (есть в Kommo)" if d.is_client else "НЕ наш клиент — вписал визу сам в приложении. Предложите продление!",
                ], 0)
                visas_svc.mark_sent(db, f"{d.key}:mgr")
        if row:
            row.value = {"date": today}
        else:
            db.add(ProgramSetting(key="visa_reminders", value={"date": today}))
        db.commit()
        log.info("Напоминания о визах: отправлено %s", sent)


@dp.callback_query(F.data.startswith("renew:"))
async def renew_click(cb: CallbackQuery):
    """«Продлить с Alpha Prime» в напоминании → сделка в Kommo (Consulting → Распределение) + сообщение менеджерам."""
    _, vid, left = (cb.data.split(":") + ["0", "0"])[:3]
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == cb.from_user.id))
        v = db.get(UserVisa, int(vid)) if vid.isdigit() and int(vid) else None
        what = v.visa_type if v else "виза / KITAS"
        until = f" до {v.expires_on:%d.%m.%Y}" if v else ""
        key = f"renew-click:{cb.from_user.id}:{vid}"
        if visas_svc.was_sent(db, key):
            await cb.answer("Заявка уже у менеджера — он скоро напишет", show_alert=False)
            return
        tg = f"@{cb.from_user.username}" if cb.from_user.username else f"id {cb.from_user.id}"
        lead_id = None
        try:
            lead_id = get_kommo().create_lead(
                title=f"Продление: {what}", contact_name=(user.first_name if user else None) or cb.from_user.first_name or "Клиент",
                phone=user.phone if user else None, telegram=tg, contact_id=user.kommo_contact_id if user else None,
                note=f"Нажал «Продлить с Alpha Prime» в напоминании бота: {what}{until}, осталось {left} дн.",
                tags=["Приложение", "Напоминание о визе"])
        except Exception:
            log.exception("Kommo: сделка на продление не создана")
        notify_managers("🔁 Хочет продлить визу", [
            f"{what}{until} · осталось {left} дн.",
            f"Человек: {cb.from_user.first_name or '—'} · {tg}" + (f" · {user.phone}" if user and user.phone else ""),
        ], lead_id)
        visas_svc.mark_sent(db, key)
        db.commit()
    await cb.answer("Отправили менеджеру ✓")
    await cb.message.answer("Спасибо! Менеджер Alpha Prime напишет вам в ближайшее время и расскажет о продлении.")


async def weekly_check(bot: Bot, kommo) -> None:
    """По понедельникам после 10:00 (Бали) — список недозаполненных сделок в группу менеджеров."""
    now = datetime.now(ZoneInfo(settings.timezone))
    if not settings.managers_chat_id or now.weekday() != 0 or now.hour < 10:
        return
    today = now.date().isoformat()
    with SessionLocal() as db:
        row = db.get(ProgramSetting, "weekly_report")
        if row and (row.value or {}).get("date") == today:
            return
        text = await asyncio.to_thread(weekly_report, kommo)
        if text:
            await bot.send_message(settings.managers_chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
        if row:
            row.value = {"date": today}
        else:
            db.add(ProgramSetting(key="weekly_report", value={"date": today}))
        db.commit()


async def _send_widget(message: Message, kind: str):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == message.from_user.id))
        if not user:
            user = User(telegram_id=message.from_user.id, telegram_username=message.from_user.username,
                        first_name=message.from_user.first_name)
            db.add(user)
            db.commit()
        if kind == "partner" and not db.scalar(select(Partner).where(Partner.user_id == user.id)):
            await message.answer("Вы ещё не в партнёрской программе. Откройте кабинет → «Партнёрка» → «Стать партнёром».")
            return
        try:
            await widgets.send(db, get_kommo(), user, kind)
        except Exception as exc:
            log.warning("Виджет %s не отправлен: %s", kind, exc)
            await message.answer("Не получилось показать карточку. Обновите Telegram до последней версии и попробуйте ещё раз.")


@dp.message(Command("visa"), F.chat.type == "private")
async def cmd_visa(message: Message):
    """Виджет «Моя виза»."""
    await _send_widget(message, "visa")


@dp.message(Command("events"), F.chat.type == "private")
async def cmd_events(message: Message):
    """Виджет «Мероприятия»."""
    await _send_widget(message, "events")


@dp.message(Command("partner"), F.chat.type == "private")
async def cmd_partner(message: Message):
    """Виджет «Партнёрка»."""
    await _send_widget(message, "partner")


async def widget_query_middleware(handler, update, data):
    """widget_query aiogram пока не знает — ловим сырое поле обновления сами."""
    extra = getattr(update, "model_extra", None) or {}
    q = extra.get("widget_query") or extra.get("shared_widget_query")
    if q:
        with SessionLocal() as db:
            await widgets.handle_query(db, get_kommo(), q)
        return None
    return await handler(update, data)


dp.update.outer_middleware(widget_query_middleware)


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
    intake_since = utcnow() - timedelta(days=2)
    last_table_day = ""
    while True:
        started = utcnow()
        full_hour = started - full_at > timedelta(hours=1)
        if full_hour:
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
            if settings.intake_enabled:  # автозаявки в производство и готовые визы
                with SessionLocal() as db:
                    n = await asyncio.to_thread(intake_svc.tick, db, kommo, intake_since - timedelta(minutes=5))
                intake_since = started
                if n:
                    log.info("Автозаявки: обработано сделок %s", n)
            last = started
            log.info("Синхронизация: %s уведомлений", len(notes))
            await weekly_check(bot, kommo)
            await visa_reminders(bot, kommo)
            bali_now = datetime.now(ZoneInfo(settings.timezone))
            table_day = bali_now.date().isoformat()
            if settings.table_sync and bali_now.hour >= 3 and table_day != last_table_day:  # таблица — раз в сутки, ночью
                last_table_day = table_day
                try:
                    with SessionLocal() as db:
                        r = await asyncio.to_thread(table_svc.run, db, kommo, True, settings.table_move_stages, True,
                                                    settings.table_sync_partners)
                        partners = {p.id: p.user.telegram_id for p in db.scalars(select(Partner))}
                    for partner_id, text in r.get("notes", []):
                        if partners.get(partner_id):
                            try:
                                await bot.send_message(partners[partner_id], text, reply_markup=app_keyboard())
                            except Exception:
                                log.warning("Не удалось отправить уведомление партнёру %s", partner_id)
                    log.info("Таблица: начислений %s, контактов с датами %s, сделок переведено %s",
                             r["partners"].get("accruals"), r.get("contacts_updated"), r.get("moved"))
                except Exception:
                    log.exception("Таблица производства не прочиталась")
            if full_hour:  # виджеты — раз в час (визы, мероприятия, партнёрка)
                with SessionLocal() as db:
                    n = await widgets.refresh_all(db, kommo)
                log.info("Виджеты: обновлено %s", n)
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
    try:
        await bot.set_my_commands([
            BotCommand(command="visa", description="Моя виза — сроки и статус"),
            BotCommand(command="events", description="Мероприятия"),
            BotCommand(command="partner", description="Партнёрка — баланс"),
        ], scope=BotCommandScopeAllPrivateChats())
    except Exception:
        log.warning("Не удалось задать команды бота")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types() + ["widget_query", "shared_widget_query"])


if __name__ == "__main__":
    asyncio.run(main())
