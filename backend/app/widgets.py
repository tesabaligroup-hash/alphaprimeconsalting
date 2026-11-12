"""Виджеты Telegram (Bot API: sendWidget / editMessageWidgetData / answerWidgetQuery).

Три виджета в личном чате с ботом:
  visa    — «Моя виза»: услуги и шаги, сколько дней до конца визы/KITAS;
  events  — «Мероприятия»: новости с кнопкой «Узнать подробнее», кнопка «Хочу пойти» → заявка менеджерам;
  partner — «Партнёрка»: к выплате, ожидается, друзья, кодовое слово (без услуг и цен — правило программы).

HTML отправляется один раз и не меняется; меняется только состояние (chat_data, JSON до 1024 байт).
Виджет не ходит в интернет: всё, что он показывает, лежит в состоянии.
"""
import hashlib
import json
import logging
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .kommo.base import KommoClient
from .models import News, Partner, User, WidgetMessage
from .services import cabinet
from .services import partner as partner_svc
from .services.interest import register_interest

log = logging.getLogger(__name__)
KINDS = ("visa", "events", "partner")
MAX_STATE = 1000

# ---------- HTML ----------

_STYLE = """<style>
*{box-sizing:border-box;margin:0}
body{font:14px/1.35 -apple-system,system-ui,sans-serif;color:var(--tg-theme-text-color);padding:12px}
.k{font-size:11px;letter-spacing:.14em;color:#C9A24B;font-weight:700}
h3{font-size:17px;margin:3px 0 10px}
.c{border:1px solid var(--tg-theme-section-separator-color,#E8DFC9);border-radius:12px;padding:10px;margin-bottom:8px}
.t{font-weight:600}.h{color:var(--tg-theme-hint-color);font-size:12px}
.bar{display:flex;gap:4px;margin:8px 0 5px}.bar i{flex:1;height:6px;border-radius:3px;background:var(--tg-theme-secondary-bg-color,#EEE)}
.bar i.on{background:#C9A24B}
.d{display:flex;justify-content:space-between;align-items:center;gap:8px}
.n{font-size:24px;font-weight:700;color:#C9A24B;white-space:nowrap}
.big{font-size:28px;font-weight:700;color:#C9A24B}
.g{display:flex;gap:8px}.g .c{flex:1}
button{width:100%;margin-top:6px;padding:9px;border:0;border-radius:10px;background:#C9A24B;color:#1C1A16;font-weight:700;font-size:14px}
button.o{background:transparent;border:1px solid #C9A24B;color:var(--tg-theme-text-color)}
button:disabled{opacity:.6}
</style>"""

_JS_BASE = """const W=window.TelegramWidget,o=document.getElementById('o');
function e(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function st(){try{return JSON.parse(W.chatData)}catch(x){return null}}
function m(n){return Number(n||0).toLocaleString('ru-RU').replace(/,/g,' ')}
document.getElementById('app').onclick=()=>W.openTelegramLink('__APP__');"""

VISA_HTML = _STYLE + """<div class=k>ALPHA PRIME</div><h3>Моя виза</h3><div id=o></div>
<button id=app>Открыть кабинет</button><script>""" + _JS_BASE + """
function r(){const s=st();if(!s){o.innerHTML='<p class=h>Загружаем…</p>';return}let h='';
(s.s||[]).forEach(v=>{let b='';for(let i=0;i<v.c;i++)b+='<i class="'+(i<=v.i?'on':'')+'"></i>';
h+='<div class=c><div class=t>'+e(v.t)+'</div>'+(v.p?'<div class=h>'+e(v.p)+'</div>':'')+'<div class=bar>'+b+'</div><div class=h>'+e(v.b)+'</div></div>'});
(s.x||[]).forEach(v=>{h+='<div class="c d"><div><div class=t>'+e(v.t)+'</div><div class=h>'+e(v.p)+' · до '+e(v.d)+'</div></div><div class=n>'+v.l+' <span class=h>дн.</span></div></div>'});
if(!h)h='<div class=c><p class=h>'+e(s.m||'Сейчас нет активных услуг')+'</p></div>';o.innerHTML=h}
W.onEvent('chatDataChanged',r);r();W.ready&&W.ready();</script>"""

EVENTS_HTML = _STYLE + """<div class=k>ALPHA PRIME</div><h3>Мероприятия</h3><div id=o></div>
<button id=app class=o>Все новости в приложении</button><script>""" + _JS_BASE + """
function r(){const s=st();if(!s){o.innerHTML='<p class=h>Загружаем…</p>';return}let h='';const ok=s.ok||[];
(s.e||[]).forEach(v=>{const d=ok.indexOf(v.i)>=0;h+='<div class=c><div class=t>'+e(v.t)+'</div><div class=h>'+e(v.b)+'</div><button data-i="'+v.i+'"'+(d?' disabled':'')+'>'+(d?'Заявка отправлена ✓':'Хочу пойти')+'</button></div>'});
if(!h)h='<div class=c><p class=h>Скоро здесь появятся наши события</p></div>';o.innerHTML=h;
o.querySelectorAll('button[data-i]').forEach(b=>b.onclick=()=>{const i=b.getAttribute('data-i');b.disabled=true;b.textContent='Отправляем…';
W.request('ev:'+i).then(a=>{b.textContent=a.result==='err'?'Ошибка, попробуйте позже':'Заявка отправлена ✓'},x=>{b.disabled=false;b.textContent='Хочу пойти'})})}
W.onEvent('chatDataChanged',r);r();W.ready&&W.ready();</script>"""

PARTNER_HTML = _STYLE + """<div class=k>ALPHA PRIME · ПАРТНЁРКА</div><h3 id=nm>Партнёрка</h3><div id=o></div>
<button id=code class=o>Показать кодовое слово</button><button id=app>Открыть партнёрку</button><script>""" + _JS_BASE + """
let show=false;function r(){const s=st();if(!s){o.innerHTML='<p class=h>Загружаем…</p>';return}
document.getElementById('nm').textContent=s.n||'Партнёрка';
o.innerHTML='<div class=c><div class=h>К выплате, IDR</div><div class=big>'+m(s.p)+'</div><div class=h>Ближайшая выплата — '+e(s.d)+'</div></div>'+
'<div class=g><div class=c><div class=h>Ожидается</div><div class=t>'+m(s.e)+'</div></div><div class=c><div class=h>Выплачено</div><div class=t>'+m(s.t)+'</div></div><div class=c><div class=h>Друзей</div><div class=t>'+(s.f||0)+'</div></div></div>'+
(show&&s.k?'<div class=c><div class=h>Ваше кодовое слово</div><div class=big>'+e(s.k)+'</div></div>':'')}
document.getElementById('code').onclick=()=>{show=!show;document.getElementById('code').textContent=show?'Скрыть кодовое слово':'Показать кодовое слово';r()};
W.onEvent('chatDataChanged',r);r();W.ready&&W.ready();</script>"""

HTML = {"visa": VISA_HTML, "events": EVENTS_HTML, "partner": PARTNER_HTML}


def app_link() -> str:
    return f"https://t.me/{get_settings().bot_username}?startapp=w"


def html_for(kind: str) -> str:
    return HTML[kind].replace("__APP__", app_link())


# ---------- состояние ----------

def _ru_date(iso: str | None) -> str:
    if not iso:
        return "—"
    d = date.fromisoformat(iso[:10])
    return d.strftime("%d.%m.%Y")


def _short(text: str | None, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _join(a: str, b: str) -> str:
    """«В работе» + «В работе» → один раз."""
    if not a or (b and b.lower().startswith(a.lower())):
        return b or a
    return f"{a} · {b}" if b else a


def _fit(state: dict, lists: tuple[str, ...]) -> dict:
    """Ужимает состояние до лимита Telegram (1024 байта): убирает элементы с конца списков."""
    while len(json.dumps(state, ensure_ascii=False).encode()) > MAX_STATE:
        for key in lists:
            if len(state.get(key) or []) > 1:
                state[key] = state[key][:-1]
                break
        else:
            break
    return state


def visa_state(kommo: KommoClient, user: User) -> dict:
    if not user.kommo_contact_id:
        return {"m": "Откройте кабинет и поделитесь номером — и здесь появятся ваши визы и даты."}
    data = cabinet.load_client(kommo, user.contact_ids, with_history=False)
    services = []
    for c in data["services"][:2]:  # виджет не выше 600 px — больше не влезет
        steps = c.get("steps") or []
        idx = c.get("step_index", 0)
        current = steps[idx]["title"] if 0 <= idx < len(steps) else ""
        badge = c.get("badge") or ""
        if c.get("remaining"):
            badge = f"{badge} · осталось оплатить {c['remaining']:,} IDR".replace(",", " ")
        services.append({"t": _short(c["title"], 40), "p": _short(c.get("person"), 30), "i": idx,
                         "c": max(len(steps), 1), "b": _short(_join(current.split(" — ")[0], badge), 80)})
    dates = [{"t": _short(d["title"], 36), "p": _short(d.get("person"), 24), "d": _ru_date(d["date"]), "l": d["days_left"]}
             for d in data["dates"] if d.get("kind") in ("expiry", "passport")][:2]
    return _fit({"s": services, "x": dates}, ("s", "x"))


def events_list(db: Session) -> list[News]:
    return list(db.scalars(select(News).where(News.published.is_(True), News.cta_lead.is_(True))
                           .order_by(News.sort_order, News.created_at.desc()).limit(3)))


def events_state(db: Session, user: User, sent: list[int] | None = None) -> dict:
    items = [{"i": n.id, "t": _short(n.title, 60), "b": _short(n.body, 110)} for n in events_list(db)]
    return _fit({"e": items, "ok": sent or []}, ("e",))


def partner_state(db: Session, user: User) -> dict:
    p = db.scalar(select(Partner).where(Partner.user_id == user.id))
    if not p:
        return {"n": "Партнёрка", "p": 0, "e": 0, "t": 0, "f": 0, "d": "—", "k": None}
    d = partner_svc.dashboard(db, p)
    b = d["balance"]
    friends = len(d.get("friends") or [])
    return {"n": p.display_name, "p": b["to_payout"], "e": b["expected"], "t": b["paid_total"],
            "f": friends, "d": _ru_date(b["next_payout"]), "k": p.codeword}


def build_state(db: Session, kommo: KommoClient, user: User, kind: str, prev: dict | None = None) -> dict:
    if kind == "visa":
        return visa_state(kommo, user)
    if kind == "events":
        return events_state(db, user, (prev or {}).get("ok"))
    return partner_state(db, user)


def caption(kind: str, state: dict) -> str:
    """Текст под виджетом — его видят и те, у кого старая версия Telegram без виджетов."""
    if kind == "visa":
        lines = ["Моя виза — Alpha Prime"]
        lines += [f"• {s['t']}: {s['b']}" for s in state.get("s", [])]
        lines += [f"• {x['t']} — до {x['d']} ({x['l']} дн.)" for x in state.get("x", [])]
        if len(lines) == 1:
            lines.append(state.get("m") or "Сейчас нет активных услуг")
    elif kind == "events":
        lines = ["Мероприятия Alpha Prime"] + [f"• {e['t']}" for e in state.get("e", [])]
    else:
        lines = [f"Партнёрка: к выплате {state.get('p', 0):,} IDR, ожидается {state.get('e', 0):,} IDR".replace(",", " ")]
    return "\n".join(lines)[:1000]


def _hash(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ---------- Bot API ----------

async def tg(method: str, payload: dict) -> dict:
    token = get_settings().bot_token
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"{method}: {data.get('description')}")
    return data.get("result") or {}


async def send(db: Session, kommo: KommoClient, user: User, kind: str) -> WidgetMessage:
    """Отправляет новый виджет; старый того же вида больше не обновляем (новый — внизу чата)."""
    state = build_state(db, kommo, user, kind)
    msg = await tg("sendWidget", {"chat_id": user.telegram_id, "html": html_for(kind), "caption": caption(kind, state),
                                  "chat_data": json.dumps(state, ensure_ascii=False), "allow_queries": kind == "events"})
    for old in db.scalars(select(WidgetMessage).where(WidgetMessage.user_id == user.id, WidgetMessage.kind == kind)):
        db.delete(old)
    wm = WidgetMessage(user_id=user.id, kind=kind, chat_id=user.telegram_id, message_id=msg["message_id"],
                       state_hash=_hash(state))
    db.add(wm)
    db.commit()
    return wm


async def push_state(db: Session, wm: WidgetMessage, state: dict) -> None:
    h = _hash(state)
    if h == wm.state_hash:
        return
    await tg("editMessageWidgetData", {"chat_id": wm.chat_id, "message_id": wm.message_id,
                                       "chat_data": json.dumps(state, ensure_ascii=False)})
    wm.state_hash = h
    db.commit()


async def refresh_all(db: Session, kommo: KommoClient) -> int:
    """Пересобирает состояние всех отправленных виджетов и обновляет те, что изменились."""
    changed = 0
    for wm in list(db.scalars(select(WidgetMessage))):
        user = db.get(User, wm.user_id)
        if not user:
            continue
        try:
            prev_ok = _sent_events(db, user) if wm.kind == "events" else None
            state = build_state(db, kommo, user, wm.kind, {"ok": prev_ok})
            before = wm.state_hash
            await push_state(db, wm, state)
            changed += before != wm.state_hash
        except Exception as exc:  # сообщение удалено пользователем и т.п. — больше не трогаем
            log.warning("Виджет %s (%s): %s", wm.id, wm.kind, exc)
            if "not found" in str(exc).lower() or "blocked" in str(exc).lower():
                db.delete(wm)
                db.commit()
    return changed


def _sent_events(db: Session, user: User) -> list[int]:
    from .models import ServiceOrder
    codes = db.scalars(select(ServiceOrder.service_code).where(ServiceOrder.user_id == user.id,
                                                               ServiceOrder.service_code.like("news:%")))
    return sorted({int(c.split(":", 1)[1]) for c in codes if c.split(":", 1)[1].isdigit()})


async def handle_query(db: Session, kommo: KommoClient, q: dict) -> None:
    """Нажатие в виджете → widget_query. Сейчас одна команда: ev:<id> — «Хочу пойти»."""
    answer = "ok"
    try:
        data = str(q.get("data") or "")
        tg_user = q.get("from") or {}
        user = db.scalar(select(User).where(User.telegram_id == tg_user.get("id")))
        if data.startswith("ev:") and data[3:].isdigit() and user:
            n = db.get(News, int(data[3:]))
            if n and n.published and n.cta_lead:
                register_interest(db, kommo, user, n, where="виджете «Мероприятия» в чате с ботом")
                wm = db.scalar(select(WidgetMessage).where(WidgetMessage.user_id == user.id, WidgetMessage.kind == "events"))
                if wm:
                    await push_state(db, wm, events_state(db, user, _sent_events(db, user)))
            else:
                answer = "err"
        else:
            answer = "err"
    except Exception:
        log.exception("widget_query")
        answer = "err"
    await tg("answerWidgetQuery", {"widget_query_id": q["id"], "data": answer})
