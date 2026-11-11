"""API для Telegram Mini App."""
import base64
import logging
import hashlib
import hmac
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .kommo import get_kommo
from .kommo.base import KommoClient
from .links import partner_links
from .models import News, Partner, Referral, ServiceOrder, User
from .services import cabinet, partner as partner_svc
from .services.linking import link_user
from .notify import notify_managers
from .tariffs import CATEGORY_LABELS, TARIFFS, find_tariff
from .telegram_auth import InvalidInitData, validate_init_data
from .timeutil import utcnow

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)

DEV_TELEGRAM_ID = 1  # тестовый пользователь в режиме разработки
_LINK_TRIES: dict[int, float] = {}


def current_user(
    db: Session = Depends(get_db),
    x_telegram_init_data: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
) -> User:
    s = get_settings()
    if s.dev_mode and x_dev_user and not x_telegram_init_data:
        tg = {"id": DEV_TELEGRAM_ID, "first_name": "Анна", "username": "anna_demo"}
    else:
        try:
            tg = validate_init_data(x_telegram_init_data or "", s.bot_token)["user"]
        except InvalidInitData:
            raise HTTPException(401, "Откройте приложение из Telegram")
    user = db.scalar(select(User).where(User.telegram_id == int(tg["id"])))
    if not user:
        user = User(telegram_id=int(tg["id"]), first_name=tg.get("first_name"), telegram_username=tg.get("username"),
                    language=(tg.get("language_code") or "ru")[:2] if (tg.get("language_code") or "ru")[:2] in ("ru", "en", "id") else "ru")
        db.add(user)
        db.commit()
    elif tg.get("username") and user.telegram_username != tg.get("username"):
        user.telegram_username = tg.get("username")
        db.commit()
    if not user.kommo_contact_id and (user.phone or user.telegram_username) and not s.dev_mode:
        # Клиента могли добавить в CRM позже — пробуем привязать не чаще раза в 2 минуты
        last = _LINK_TRIES.get(user.id, 0)
        if time.time() - last > 120:
            _LINK_TRIES[user.id] = time.time()
            link_user(db, get_kommo(), user)
    if s.dev_mode and user.telegram_id == DEV_TELEGRAM_ID and not user.kommo_contact_id:
        user.kommo_contact_id = 501  # Анна из тестовых данных
        db.commit()
    return user


def kommo_dep() -> KommoClient:
    return get_kommo()


# ---------- Общее ----------

@router.get("/me")
def me(user: User = Depends(current_user)):
    s = get_settings()
    return {
        "first_name": user.first_name,
        "linked": bool(user.kommo_contact_id),
        "has_phone": bool(user.phone),
        "is_partner": bool(user.partner),
        "language": user.language,
        "notify_partner_offers": user.notify_partner_offers,
        "notify_company_offers": user.notify_company_offers,
        "company": {"whatsapp": s.company_whatsapp, "telegram": s.company_telegram, "instagram": s.company_instagram,
                    "address": s.company_address, "maps_query": s.company_maps_query, "bot_username": s.bot_username},
    }


def _news_view(n: News) -> dict:
    return {"id": n.id, "kind": n.kind, "is_banner": n.is_banner, "title": n.title, "body": n.body,
            "partner_name": n.partner_name, "image": f"/uploads/{n.image_path}" if n.image_path else None,
            "link": n.link_url, "date": n.created_at.date().isoformat() if n.created_at else None}


@router.get("/home")
def home(user: User = Depends(current_user), db: Session = Depends(get_db), kommo: KommoClient = Depends(kommo_dep)):
    news = list(db.scalars(select(News).where(News.published.is_(True)).order_by(News.sort_order, News.created_at.desc()).limit(30)))
    data = {"services": [], "dates": [], "contact": None}
    if user.kommo_contact_id:
        data = cabinet.load_client(kommo, user.kommo_contact_id, with_history=False)
    return {
        "dates": data["dates"],
        "services": data["services"],
        "banners": [_news_view(n) for n in news if n.kind == "company" and n.is_banner],
        "news": [_news_view(n) for n in news if n.kind == "company" and not n.is_banner][:10],
        "partner_news": [_news_view(n) for n in news if n.kind == "partner"][:10],
    }


# ---------- Услуги ----------

@router.get("/services")
def my_services(user: User = Depends(current_user), kommo: KommoClient = Depends(kommo_dep)):
    if not user.kommo_contact_id:
        return {"services": [], "archive": []}
    data = cabinet.load_client(kommo, user.kommo_contact_id, with_history=False)
    return {"services": data["services"], "archive": data["archive"]}


def _owned_lead(user: User, kommo: KommoClient, lead_id: int):
    if not user.kommo_contact_id:
        raise HTTPException(404)
    contact = kommo.get_contact(user.kommo_contact_id)
    if not contact or lead_id not in contact.lead_ids:
        raise HTTPException(404)
    leads = kommo.get_leads([lead_id])
    if not leads:
        raise HTTPException(404)
    return contact, leads[0]


@router.get("/services/{lead_id}")
def service_detail(lead_id: int, user: User = Depends(current_user), kommo: KommoClient = Depends(kommo_dep)):
    contact, lead = _owned_lead(user, kommo, lead_id)
    person = cabinet.contact_person(contact)
    main = kommo.get_contact(lead.contact_ids[0]) if lead.contact_ids and lead.contact_ids[0] != contact.id else contact
    card = cabinet.build_card(lead, kommo, person, with_history=True, person_contact=main or contact)
    if not card:
        raise HTTPException(404)
    files = [{"uuid": f.uuid, "name": f.name, "created_at": f.created_at.date().isoformat() if f.created_at else None}
             for f in kommo.get_lead_files(lead_id)]
    return {"service": card.__dict__ | {"steps": [st.__dict__ for st in card.steps]}, "files": files}


@router.get("/catalog")
def catalog():
    cats = []
    for key, label in CATEGORY_LABELS.items():
        items = [{"code": t.code, "name": t.name, "price": t.price} for t in TARIFFS if t.category == key and t.in_catalog]
        if items:
            cats.append({"id": key, "label": label, "items": items})
    return {"categories": cats}


class OrderIn(BaseModel):
    code: str


@router.post("/orders")
def order(body: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db), kommo: KommoClient = Depends(kommo_dep)):
    tariff = find_tariff(body.code)
    if not tariff or not tariff.in_catalog:
        raise HTTPException(404, "Услуга не найдена")
    recent = db.scalar(select(ServiceOrder).where(ServiceOrder.user_id == user.id, ServiceOrder.service_code == tariff.code,
                                                  ServiceOrder.created_at > utcnow() - timedelta(hours=1)))
    if recent:
        return {"ok": True, "duplicate": True}
    tg = f"@{user.telegram_username}" if user.telegram_username else f"id {user.telegram_id}"
    title = f"Заявка из приложения: {tariff.name}"
    lead_id = None
    try:
        lead_id = kommo.create_lead(
            title=title, contact_name=user.first_name or "Клиент из приложения",
            phone=user.phone, telegram=tg, contact_id=user.kommo_contact_id, price=tariff.price,
            note=f"Клиент нажал «Заказать» в Telegram-приложении.\nУслуга: {tariff.name} ({tariff.code})",
            tags=["Приложение"],
        )
    except Exception:  # заявку не теряем: менеджеры получат уведомление и заведут сделку вручную
        log.exception("Kommo: не удалось создать сделку по заявке")
    db.add(ServiceOrder(user_id=user.id, service_code=tariff.code, kommo_lead_id=lead_id))
    db.commit()
    notify_managers("🛎 Новая заявка из приложения", [
        f"Услуга: {tariff.name} ({tariff.code})",
        f"Клиент: {user.first_name or '—'} · {tg}" + (f" · {user.phone}" if user.phone else ""),
        "Уже есть в Kommo" if user.kommo_contact_id else "Новый клиент (в Kommo создан контакт)",
    ], lead_id)
    return {"ok": True}


# ---------- Документы ----------

@router.get("/documents")
def documents(user: User = Depends(current_user), kommo: KommoClient = Depends(kommo_dep)):
    if not user.kommo_contact_id:
        return {"groups": []}
    return {"groups": cabinet.load_documents(kommo, user.kommo_contact_id)}


def _file_token(lead_id: int, uuid: str, exp: int) -> str:
    msg = f"{lead_id}:{uuid}:{exp}"
    sig = hmac.new(get_settings().secret_key.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{msg}:{sig}".encode()).decode().rstrip("=")


@router.post("/documents/{lead_id}/{uuid}/link")
def download_link(lead_id: int, uuid: str, user: User = Depends(current_user), kommo: KommoClient = Depends(kommo_dep)):
    """Одноразовая ссылка на файл (10 минут): Telegram скачивает файл без заголовков авторизации."""
    _owned_lead(user, kommo, lead_id)
    files = {f.uuid: f for f in kommo.get_lead_files(lead_id)}
    if uuid not in files:
        raise HTTPException(404)
    exp = int(time.time()) + 600
    return {"url": f"{get_settings().public_url.rstrip('/')}/api/files/{_file_token(lead_id, uuid, exp)}", "name": files[uuid].name}


@router.get("/files/{token}")
def download_file(token: str, kommo: KommoClient = Depends(kommo_dep)):
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        lead_s, uuid, exp_s, _sig = raw.split(":")
        lead_id, exp = int(lead_s), int(exp_s)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(404)
    if not hmac.compare_digest(_file_token(lead_id, uuid, exp), token) or exp < time.time():
        raise HTTPException(403, "Ссылка устарела — откройте документ в приложении ещё раз")
    url = kommo.get_file_download_url(uuid)
    if not url:
        raise HTTPException(404, "Файл пока недоступен")
    # Файл идёт через наш сервер — ссылка Kommo требует токен CRM и не должна попадать к клиенту
    r = kommo.download_file(url)  # type: ignore[attr-defined]
    return Response(r.content, media_type=r.headers.get("content-type", "application/octet-stream"),
                    headers={"Content-Disposition": r.headers.get("content-disposition", "attachment")})


# ---------- Профиль ----------

class ProfileIn(BaseModel):
    language: str | None = Field(default=None, pattern="^(ru|en|id)$")
    notify_partner_offers: bool | None = None
    notify_company_offers: bool | None = None


@router.patch("/profile")
def profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    db.commit()
    return {"ok": True}


# ---------- Партнёрка ----------

def _partner(user: User) -> Partner:
    if not user.partner:
        raise HTTPException(403, "Вы ещё не партнёр")
    if user.partner.status == "blocked":
        raise HTTPException(403, "Партнёрский кабинет заблокирован")
    return user.partner


class JoinIn(BaseModel):
    accept_terms: bool


@router.post("/partner/join")
def join(body: JoinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.accept_terms:
        raise HTTPException(400, "Нужно принять условия программы")
    if user.partner:
        return {"ok": True}
    db.add(Partner(user_id=user.id, kind="private", display_name=user.first_name or "Партнёр", accepted_terms_at=utcnow()))
    db.commit()
    return {"ok": True}


@router.get("/partner")
def partner_home(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _partner(user)
    data = partner_svc.dashboard(db, p)
    refs = list(db.scalars(select(Referral).where(Referral.partner_id == p.id, Referral.status.in_(("pending", "rejected", "expired")))
                           .order_by(Referral.created_at.desc()).limit(50)))
    data["referrals"] = [partner_svc.referral_view(r) for r in refs]
    data["links"] = partner_links(p) if p.codeword else None
    data["has_payout_details"] = bool(p.payout_details)
    return data


class WordIn(BaseModel):
    word: str = Field(max_length=32)


@router.post("/partner/codeword/check")
def codeword_check(body: WordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _partner(user)
    return partner_svc.check_codeword(db, body.word, p.id)


@router.post("/partner/codeword")
def codeword_set(body: WordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _partner(user)
    if p.codeword:
        raise HTTPException(409, "Кодовое слово уже закреплено. Сменить его можно через менеджера.")
    res = partner_svc.check_codeword(db, body.word, p.id)
    if not res["ok"]:
        raise HTTPException(400, "; ".join(res["problems"]))
    p.codeword = res["word"]
    if not p.kommo_partner_value:
        p.kommo_partner_value = res["word"]
    db.commit()
    return {"ok": True, "codeword": p.codeword, "links": partner_links(p)}


class ReferralIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    channel: str = Field(pattern="^(tg|wa|ig)$")
    contact: str = Field(min_length=3, max_length=128)
    who_writes: str = Field(pattern="^(self|us)$")


@router.post("/partner/referrals")
def add_referral(body: ReferralIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _partner(user)
    s = partner_svc.program_settings(db)
    r = Referral(partner_id=p.id, friend_name=body.name.strip(), channel=body.channel, contact=body.contact.strip(),
                 who_writes=body.who_writes, source="manual", status="pending",
                 expires_at=utcnow() + timedelta(days=s["referral_days"]))
    db.add(r)
    db.commit()
    channel = {"tg": "Telegram", "wa": "WhatsApp", "ig": "Instagram"}[r.channel]
    notify_managers("🤝 Новая рекомендация от партнёра", [
        f"Партнёр: {p.display_name} ({p.codeword or 'без кодового слова'})",
        f"Друг: {r.friend_name} · {channel}: {r.contact}",
        "НАПИСАТЬ ДРУГУ ПЕРВЫМИ" if r.who_writes == "us" else "Друг напишет сам",
        f"Проверить и закрепить: {get_settings().public_url.rstrip('/')}/admin/referrals",
    ], lead_id=0)
    return {"ok": True, "referral": partner_svc.referral_view(r)}


class PayoutDetailsIn(BaseModel):
    details: str = Field(max_length=2000)


@router.put("/partner/payout-details")
def payout_details(body: PayoutDetailsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _partner(user)
    p.payout_details = body.details
    db.commit()
    return {"ok": True}


@router.get("/health", include_in_schema=False)
def health():
    return {"ok": True}
