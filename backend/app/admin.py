"""Админка: новости и баннеры, рекомендации, партнёры, привязка клиентов, стоп-слова, начисления."""
import hmac
import secrets
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .kommo import get_kommo
from .models import Accrual, AuditLog, Level2Link, News, Partner, Referral, StopWord, User
from .partner_rules import ACCRUAL_LABELS, normalize_codeword
from .services import partner as partner_svc
from .timeutil import utcnow

router = APIRouter(prefix="/admin", include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["money"] = lambda v: f"{int(v or 0):,}".replace(",", " ")
templates.env.globals["ACCRUAL_LABELS"] = ACCRUAL_LABELS

ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
REJECT_REASONS = ["Клиент закреплён за другим партнёром", "Клиент уже был в базе Alpha Prime", "Не удалось связаться", "Другое"]


class NotLoggedIn(Exception):
    pass


def require_admin(request: Request) -> str:
    if not request.session.get("admin"):
        raise NotLoggedIn()
    return request.session["admin"]


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(24)
    return request.session["csrf"]


def check_csrf(request: Request, token: str) -> None:
    if not hmac.compare_digest(request.session.get("csrf", ""), token or ""):
        raise HTTPException(400, "Обновите страницу и попробуйте ещё раз")


def render(request: Request, name: str, **ctx):
    ctx.update(request=request, csrf=csrf_token(request), admin=request.session.get("admin"))
    return templates.TemplateResponse(request, name, ctx)


def audit(db: Session, actor: str, action: str, **details):
    db.add(AuditLog(actor=actor, action=action, details=details))


# ---------- Вход ----------

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html", error=None)


@router.post("/login")
def login(request: Request, name: str = Form(...), password: str = Form(...), csrf: str = Form("")):
    check_csrf(request, csrf)
    s = get_settings()
    if s.admin_password in ("", "change-me") and not s.dev_mode:
        return render(request, "login.html", error="Пароль админки не задан на сервере (ADMIN_PASSWORD)")
    if not hmac.compare_digest(password, s.admin_password):
        return render(request, "login.html", error="Неверный пароль")
    request.session["admin"] = name.strip()[:64] or "admin"
    return RedirectResponse("/admin", 303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", 303)


# ---------- Главная ----------

@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    stats = {
        "pending": db.scalar(select(func.count()).select_from(Referral).where(Referral.status == "pending")),
        "unlinked": db.scalar(select(func.count()).select_from(User).where(User.phone.is_not(None), User.kommo_contact_id.is_(None))),
        "partners": db.scalar(select(func.count()).select_from(Partner)),
        "to_payout": db.scalar(select(func.coalesce(func.sum(Accrual.amount), 0)).where(Accrual.status == "to_payout")),
        "news": db.scalar(select(func.count()).select_from(News).where(News.published.is_(True))),
    }
    return render(request, "dashboard.html", stats=stats)


# ---------- Новости и баннеры ----------

@router.get("/news", response_class=HTMLResponse)
def news_list(request: Request, db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    items = list(db.scalars(select(News).order_by(News.kind, News.sort_order, News.created_at.desc())))
    return render(request, "news_list.html", items=items)


@router.get("/news/new", response_class=HTMLResponse)
def news_new(request: Request, admin: str = Depends(require_admin)):
    return render(request, "news_form.html", item=None)


@router.get("/news/{news_id}", response_class=HTMLResponse)
def news_form(request: Request, news_id: int, db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    item = db.get(News, news_id)
    if not item:
        raise HTTPException(404)
    return render(request, "news_form.html", item=item)


def _save_image(upload: UploadFile | None) -> str | None:
    if not upload or not upload.filename:
        return None
    ext = Path(upload.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(400, "Картинка должна быть JPG, PNG или WEBP")
    data = upload.file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Картинка больше 8 МБ")
    name = f"{uuid.uuid4().hex}{ext}"
    folder = Path(get_settings().uploads_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return name


@router.post("/news/save")
def news_save(request: Request, csrf: str = Form(""), news_id: int | None = Form(None), kind: str = Form("company"),
              is_banner: bool = Form(False), title: str = Form(...), body: str = Form(""), partner_name: str = Form(""),
              link_url: str = Form(""), sort_order: int = Form(0), published: bool = Form(False), cta_lead: bool = Form(False),
              image: UploadFile | None = File(None), db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    item = db.get(News, news_id) if news_id else News()
    item.kind = "partner" if kind == "partner" else "company"
    item.is_banner = is_banner
    item.title, item.body = title.strip(), body.strip() or None
    item.partner_name = partner_name.strip() or None
    link = link_url.strip()
    if link and not link.startswith(("https://", "http://", "tg://")):
        link = "https://" + link
    item.link_url = link or None
    item.cta_lead = cta_lead
    item.sort_order, item.published = sort_order, published
    img = _save_image(image)
    if img:
        item.image_path = img
    db.add(item)
    audit(db, admin, "news_save", title=item.title)
    db.commit()
    return RedirectResponse("/admin/news", 303)


@router.post("/news/{news_id}/delete")
def news_delete(news_id: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    item = db.get(News, news_id)
    if item:
        audit(db, admin, "news_delete", title=item.title)
        db.delete(item)
        db.commit()
    return RedirectResponse("/admin/news", 303)


# ---------- Рекомендации ----------

@router.get("/referrals", response_class=HTMLResponse)
def referrals(request: Request, status: str = "pending", db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    q = select(Referral).order_by(Referral.created_at.desc()).limit(200)
    if status != "all":
        q = q.where(Referral.status == status)
    return render(request, "referrals.html", items=list(db.scalars(q)), status=status, reasons=REJECT_REASONS)


@router.post("/referrals/{ref_id}")
def referral_decide(ref_id: int, request: Request, csrf: str = Form(""), action: str = Form(...), reason: str = Form(""),
                    db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    r = db.get(Referral, ref_id)
    if not r or r.status != "pending":
        return RedirectResponse("/admin/referrals", 303)
    if action == "attach":
        r.status, r.attached_at = "attached", utcnow()
        partner = db.get(Partner, r.partner_id)
        channel = {"tg": "Telegram", "wa": "WhatsApp", "ig": "Instagram"}[r.channel]
        who = "Друг напишет сам" if r.who_writes == "self" else "НАПИСАТЬ ДРУГУ ПЕРВЫМИ"
        try:
            r.kommo_lead_id = get_kommo().create_lead(
                title=f"Рекомендация: {r.friend_name}", contact_name=r.friend_name,
                phone=r.contact if r.channel == "wa" else None,
                telegram=r.contact if r.channel == "tg" else None,
                note=f"Рекомендация от партнёра {partner.display_name} ({partner.codeword or 'без кодового слова'}).\n"
                     f"{channel}: {r.contact}\n{who}.\nВ поле «Партнёр» укажите: {partner.kommo_partner_value or partner.codeword}",
                tags=["Партнёрка", "Приложение"], contact_id=r.kommo_contact_id)
        except Exception as exc:  # заявку в CRM можно завести вручную — закрепление всё равно сохраняем
            r.reject_reason = None
            audit(db, admin, "kommo_error", referral=r.id, error=str(exc)[:300])
    else:
        r.status, r.reject_reason = "rejected", reason or REJECT_REASONS[0]
    audit(db, admin, f"referral_{action}", referral=r.id, reason=reason)
    db.commit()
    return RedirectResponse("/admin/referrals", 303)


# ---------- Партнёры ----------

@router.get("/partners", response_class=HTMLResponse)
def partners(request: Request, db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    items = list(db.scalars(select(Partner).order_by(Partner.created_at.desc())))
    links = {l.business_partner_id: l for l in db.scalars(select(Level2Link))}
    return render(request, "partners.html", items=items, links=links)


@router.get("/partners/{pid}", response_class=HTMLResponse)
def partner_form(pid: int, request: Request, db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    p = db.get(Partner, pid)
    if not p:
        raise HTTPException(404)
    link = db.scalar(select(Level2Link).where(Level2Link.business_partner_id == pid))
    others = list(db.scalars(select(Partner).where(Partner.id != pid).order_by(Partner.display_name)))
    accs = list(db.scalars(select(Accrual).where(Accrual.partner_id == pid).order_by(Accrual.updated_at.desc()).limit(100)))
    return render(request, "partner_form.html", p=p, link=link, others=others, accs=accs)


@router.post("/partners/{pid}")
def partner_save(pid: int, request: Request, csrf: str = Form(""), display_name: str = Form(...), kind: str = Form(...),
                 status: str = Form(...), codeword: str = Form(""), kommo_partner_value: str = Form(""),
                 gold_until: str = Form(""), level2_partner_id: str = Form(""), level2_contract_date: str = Form(""),
                 db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    p = db.get(Partner, pid)
    if not p:
        raise HTTPException(404)
    p.display_name = display_name.strip() or p.display_name
    p.kind = kind if kind in ("private", "business", "level2") else p.kind
    p.status = status if status in ("active", "inactive", "blocked") else p.status
    new_word = normalize_codeword(codeword)
    if new_word and new_word != p.codeword:
        res = partner_svc.check_codeword(db, new_word, p.id)
        if not res["ok"]:
            raise HTTPException(400, "Кодовое слово: " + "; ".join(res["problems"]))
        audit(db, admin, "codeword_change", partner=p.id, old=p.codeword, new=new_word)
        p.codeword = new_word
    p.kommo_partner_value = kommo_partner_value.strip() or None
    p.gold_until = date.fromisoformat(gold_until) if gold_until else None
    link = db.scalar(select(Level2Link).where(Level2Link.business_partner_id == pid))
    if level2_partner_id:
        start = date.fromisoformat(level2_contract_date) if level2_contract_date else date.today()
        end = start + timedelta(days=730)
        if link:
            link.level2_partner_id, link.contract_date, link.end_date = int(level2_partner_id), start, end
        else:
            db.add(Level2Link(level2_partner_id=int(level2_partner_id), business_partner_id=pid, contract_date=start, end_date=end))
    elif link:
        db.delete(link)
    audit(db, admin, "partner_save", partner=p.id)
    db.commit()
    return RedirectResponse(f"/admin/partners/{pid}", 303)


# ---------- Клиенты без привязки к Kommo ----------

@router.get("/users", response_class=HTMLResponse)
def users(request: Request, db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    items = list(db.scalars(select(User).order_by(User.kommo_contact_id.is_not(None), User.created_at.desc()).limit(300)))
    return render(request, "users.html", items=items)


@router.post("/users/{uid}")
def user_link(uid: int, request: Request, csrf: str = Form(""), kommo_contact_id: str = Form(""),
              db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    u = db.get(User, uid)
    if u:
        u.kommo_contact_id = int(kommo_contact_id) if kommo_contact_id.strip().isdigit() else None
        audit(db, admin, "user_link", user=uid, contact=u.kommo_contact_id)
        db.commit()
    return RedirectResponse("/admin/users", 303)


# ---------- Стоп-слова ----------

@router.get("/stopwords", response_class=HTMLResponse)
def stopwords(request: Request, db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    from .partner_rules import BASE_STOP_WORDS

    return render(request, "stopwords.html", items=list(db.scalars(select(StopWord).order_by(StopWord.word))), base=sorted(BASE_STOP_WORDS))


@router.post("/stopwords")
def stopwords_add(request: Request, csrf: str = Form(""), words: str = Form(""), db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    existing = {w.word for w in db.scalars(select(StopWord))}
    for raw in words.replace(",", "\n").splitlines():
        w = normalize_codeword(raw)
        if w and w not in existing:
            db.add(StopWord(word=w))
            existing.add(w)
    db.commit()
    return RedirectResponse("/admin/stopwords", 303)


@router.post("/stopwords/{wid}/delete")
def stopwords_delete(wid: int, request: Request, csrf: str = Form(""), db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    w = db.get(StopWord, wid)
    if w:
        db.delete(w)
        db.commit()
    return RedirectResponse("/admin/stopwords", 303)


# ---------- Начисления ----------

@router.get("/accruals", response_class=HTMLResponse)
def accruals(request: Request, status: str = "all", db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    q = select(Accrual).order_by(Accrual.updated_at.desc()).limit(300)
    if status != "all":
        q = q.where(Accrual.status == status)
    partners = {p.id: p for p in db.scalars(select(Partner))}
    return render(request, "accruals.html", items=list(db.scalars(q)), status=status, partners=partners)


@router.post("/accruals/sync")
def accruals_sync(request: Request, csrf: str = Form(""), db: Session = Depends(get_db), admin: str = Depends(require_admin)):
    check_csrf(request, csrf)
    partner_svc.sync_all(db, get_kommo(), utcnow() - timedelta(days=400))
    audit(db, admin, "sync_now")
    db.commit()
    return RedirectResponse("/admin/accruals", 303)
