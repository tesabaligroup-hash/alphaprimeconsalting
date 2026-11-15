"""«Мир Августины» — небольшой сервер.

• /api/state   — iPad присылает своё состояние, мамин кабинет его читает
• /api/cmd     — мамины действия (принять урок, диктант, награду…) → iPad забирает и применяет
• /api/check-room — ИИ смотрит 4 фото комнаты и говорит, чисто ли
• Telegram-бот: уведомления маме + сводка по воскресеньям в 19:00 (Бали)

Настройки (в .env на сервере):
  KIDS_KEY           — семейный код (вводится на iPad и в кабинете мамы)
  KIDS_BOT_TOKEN     — токен бота от @BotFather (можно пусто — тогда без бота)
  ANTHROPIC_API_KEY  — ключ Claude API (можно пусто — тогда без ИИ)
  KIDS_AI_MODEL      — модель Claude, по умолчанию claude-sonnet-5-5
  KIDS_URL           — адрес приложения, по умолчанию https://kids.alpha-prime.group
"""
import hmac
import json
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Request

KEY = os.getenv("KIDS_KEY", "")
BOT = os.getenv("KIDS_BOT_TOKEN", "")
AI_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("KIDS_AI_MODEL", "claude-sonnet-5-5")
URL = os.getenv("KIDS_URL", "https://kids.alpha-prime.group").rstrip("/")
DB = os.getenv("KIDS_DB", "/data/kids.db")

app = FastAPI(title="Мир Августины", docs_url=None, redoc_url=None)
_lock = threading.Lock()


def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.execute("create table if not exists kv(k text primary key, v text)")
    c.execute("create table if not exists cmd(id integer primary key autoincrement, cmd text, ts real)")
    return c


def kv_get(k, default=None):
    with _lock, db() as c:
        r = c.execute("select v from kv where k=?", (k,)).fetchone()
    return json.loads(r[0]) if r else default


def kv_set(k, v):
    with _lock, db() as c:
        c.execute("insert or replace into kv(k,v) values(?,?)", (k, json.dumps(v, ensure_ascii=False)))


def check_key(k):
    if not KEY or not k or not hmac.compare_digest(str(k), KEY):
        raise HTTPException(403, "bad key")


# ---------------- Telegram ----------------
def tg(method, **data):
    if not BOT:
        return None
    try:
        return httpx.post(f"https://api.telegram.org/bot{BOT}/{method}", json=data, timeout=40).json()
    except Exception:
        return None


def notify(text):
    for chat in kv_get("parents", []):
        tg("sendMessage", chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview=True)


SUBJ = {"rus": "Русский", "math": "Математика", "okr": "Окружающий мир", "lit": "Литература", "eng": "Английский"}
REW = {"ps": "🎮 Вечер PlayStation", "cinema": "🍿 Кино", "kids": "🎠 Детский центр", "skate": "⛸️ Каток", "aqua": "🌊 Аквапарк", "padel": "🎾 Падл"}


def lesson_name(k):
    s, _, n = (k or "").partition(":")
    return f"{SUBJ.get(s, s)}, урок {n}"


def diff_notify(old, new):
    """Сообщить маме о новом, что появилось на iPad."""
    if not old:
        return
    link = f'\n<a href="{URL}/#mama">Открыть кабинет мамы</a>'
    ok = {p.get("k") for p in old.get("pendL", [])}
    for p in new.get("pendL", []):
        if p.get("k") not in ok:
            notify(f"📝 Урок сдан на проверку: <b>{lesson_name(p.get('k'))}</b>, тест {p.get('test')}%{link}")
    od = {(p.get("wk"), p.get("tp")) for p in old.get("pendD", [])}
    for p in new.get("pendD", []):
        if (p.get("wk"), p.get("tp")) not in od:
            notify(f"✍️ {'Словарный' if p.get('tp') == 'w' else 'Текстовый'} диктант ждёт проверки{link}")
    orw = {(r.get("id"), r.get("date")) for r in old.get("pendR", [])}
    for r in new.get("pendR", []):
        if r.get("st") == "wait" and (r.get("id"), r.get("date")) not in orw:
            notify(f"🎡 Заявка на награду: <b>{REW.get(r.get('id'), r.get('id'))}</b>{link}")
    orc = old.get("roomChecks", {}) or {}
    for d, rc in (new.get("roomChecks", {}) or {}).items():
        if d in orc and orc[d].get("st") == rc.get("st"):
            continue
        if rc.get("st") == "fail":
            notify("🧹 Сегодня Августина не убрала комнату — штраф −5 💎")
        elif rc.get("st") == "ok" and rc.get("doubt"):
            notify(f"🧹 Комната: ИИ сомневается, что всё чисто. Посмотри фото{link}")


# ---------------- Сводка недели ----------------
def week_start(d=None):
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def summary(st):
    if not st:
        return "Пока нет данных с iPad."
    mon = week_start().isoformat()
    hist = [h for h in st.get("history", []) if h.get("date", "") >= mon]
    day = st.get("day") or {}
    if day.get("date", "") >= mon:
        hist.append({"date": day.get("date"), "sched": 0, "miss": 0, "ontime": len([1 for r in (day.get("r") or {}).values() if not r.get("late")]), "tests": day.get("tests", [])})
    sched = sum(h.get("sched", 0) for h in hist)
    ontime = sum(h.get("ontime", 0) for h in hist)
    miss = sum(h.get("miss", 0) for h in hist)
    tests = [t for h in hist for t in (h.get("tests") or [])]
    log = [e for e in st.get("log", []) if e.get("date", "") >= mon]
    lessons = [e for e in log if e.get("act") == "done"]
    by_subj = {}
    for e in lessons:
        s = (e.get("k") or "").split(":")[0]
        by_subj[SUBJ.get(s, s)] = by_subj.get(SUBJ.get(s, s), 0) + 1
    rev = (st.get("review") or {}).get(mon)
    dicts = (st.get("dict") or {}).get(mon, {})
    pages = sum(p for b in st.get("books", []) for d, p in (b.get("log") or {}).items() if d >= mon)
    neuro = len([d for d in (st.get("neuro") or {}) if d >= mon])
    rooms = [rc.get("st") for d, rc in (st.get("roomChecks") or {}).items() if d >= mon]
    diary = len([d for d in (st.get("diary") or {}) if d >= mon])
    weak = [lesson_name(k) for k in st.get("weak", [])][:5]
    lines = [
        "📊 <b>Неделя Августины</b>",
        f"📚 Уроков сдано: <b>{len(lessons)}</b>" + (f" ({', '.join(f'{k} {v}' for k, v in by_subj.items())})" if by_subj else ""),
        f"✅ Средний тест: <b>{str(round(sum(tests) / len(tests))) + '%' if tests else '—'}</b>" + (f" · тесты: {', '.join(map(str, tests))}" if tests else ""),
        f"🗓️ Режим дня: вовремя <b>{ontime}</b>" + (f" из {sched}, пропущено {miss}" if sched else ""),
        f"🔥 Дней подряд: <b>{st.get('streak', 0)}</b> (рекорд {st.get('best', 0)})",
        f"🧠 Повторение: {str(rev.get('score')) + '/3' if rev else 'не пройдено'}",
        "✍️ Диктанты: " + ", ".join(f"{'словарный' if t == 'w' else 'текстовый'} — {({'done': 'ошибок ' + str(len(v.get('errs', []))), 'review': 'ждёт проверки'}).get(v.get('st'), 'не написан')}" for t, v in (dicts or {"w": {}, "t": {}}).items()),
        f"🧹 Комната: убрана {rooms.count('ok')} раз, не убрана {rooms.count('fail') + rooms.count('rejected')}",
        f"📖 Прочитано страниц: <b>{pages}</b> · 🎾 мячики: <b>{neuro}/5</b> · 📔 дневник: {diary}",
        f"💎 {st.get('crystals', 0)} · ⭐ {st.get('stars', 0)}",
    ]
    if weak:
        lines.append("⚠️ Темы с ошибками: " + "; ".join(weak))
    text = "\n".join(lines)
    comment = ai_comment(text)
    if comment:
        text += "\n\n💬 " + comment
    return text + f'\n\n<a href="{URL}/#mama">Кабинет мамы</a>'


def ai(content, max_tokens=400):
    if not AI_KEY:
        return None
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60, headers={"x-api-key": AI_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       json={"model": AI_MODEL, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()
    except Exception:
        return None


def ai_comment(stats):
    return ai("Ты помогаешь маме 8-летней девочки Августины (3 класс, онлайн-школа, учится по приложению). "
              "Вот её статистика за неделю:\n\n" + stats +
              "\n\nНапиши маме 3–4 короткие строки по-русски: что получилось хорошо, что стоит поправить и одно конкретное предложение на следующую неделю. "
              "Хвали за старание, а не за ум. Без заголовков, без списков, без HTML.")


# ---------------- API ----------------
@app.get("/api/ping")
def ping(key: str):
    check_key(key)
    return {"ok": True, "bot": bool(BOT), "ai": bool(AI_KEY)}


@app.post("/api/state")
async def put_state(req: Request):
    body = await req.json()
    check_key(body.get("key"))
    st = body.get("state") or {}
    old = kv_get("state")
    kv_set("state", st)
    kv_set("updated", int(time.time() * 1000))
    threading.Thread(target=diff_notify, args=(old, st), daemon=True).start()
    return {"ok": True}


@app.get("/api/state")
def get_state(key: str):
    check_key(key)
    return {"state": kv_get("state"), "updated": kv_get("updated")}


@app.post("/api/cmd")
async def add_cmd(req: Request):
    body = await req.json()
    check_key(body.get("key"))
    with _lock, db() as c:
        cur = c.execute("insert into cmd(cmd,ts) values(?,?)", (json.dumps(body.get("cmd"), ensure_ascii=False), time.time()))
    return {"id": cur.lastrowid}


@app.get("/api/cmd")
def list_cmd(key: str, after: int = 0):
    check_key(key)
    with _lock, db() as c:
        rows = c.execute("select id,cmd from cmd where id>? order by id limit 200", (after,)).fetchall()
    return [{"id": i, "cmd": json.loads(x)} for i, x in rows]


@app.post("/api/check-room")
async def check_room(req: Request):
    body = await req.json()
    check_key(body.get("key"))
    if not AI_KEY:
        return {"ok": None, "comment": "ИИ не подключён"}
    names = {"bed": "кровать", "floor": "пол", "toys": "место для игрушек", "closet": "шкаф"}
    content = []
    for k, src in (body.get("photos") or {}).items():
        if not isinstance(src, str) or "," not in src:
            continue
        head, data = src.split(",", 1)
        mt = "image/png" if "png" in head else "image/jpeg"
        content.append({"type": "text", "text": f"Фото: {names.get(k, k)}"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
    if not content:
        return {"ok": None}
    content.append({"type": "text", "text": (
        "Это фото детской комнаты 8-летней девочки перед сном. Проверь по-доброму, но честно: заправлена ли кровать, нет ли на полу одежды, мусора, игрушек, "
        "убраны ли игрушки на место, закрыт и в порядке ли шкаф. Если фото тёмное или не видно — считай, что проверить нельзя (ok=false). "
        'Ответь ТОЛЬКО JSON без пояснений: {"ok": true|false, "comment": "одна короткая фраза для девочки, что именно убрать, или похвала"}')})
    txt = ai(content, 200)
    try:
        j = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
        return {"ok": bool(j.get("ok")), "comment": str(j.get("comment", ""))[:200]}
    except Exception:
        return {"ok": None}


# ---------------- Бот и расписание ----------------
def bot_loop():
    if not BOT:
        return
    offset = kv_get("tg_offset", 0)
    while True:
        r = tg("getUpdates", offset=offset, timeout=30) or {}
        for u in r.get("result", []):
            offset = u["update_id"] + 1
            kv_set("tg_offset", offset)
            m = u.get("message") or {}
            chat, text = (m.get("chat") or {}).get("id"), (m.get("text") or "").strip()
            if not chat:
                continue
            parents = kv_get("parents", [])
            if text.startswith("/start"):
                code = text[6:].strip()
                if code and KEY and hmac.compare_digest(code, KEY):
                    if chat not in parents:
                        parents.append(chat)
                        kv_set("parents", parents)
                    tg("sendMessage", chat_id=chat, text="✅ Готово! Сюда будут приходить уведомления и сводка по воскресеньям в 19:00.\n/svodka — сводка прямо сейчас.")
                else:
                    tg("sendMessage", chat_id=chat, text="Привет! Это бот «Мир Августины». Чтобы получать уведомления, отправь: /start СЕМЕЙНЫЙ_КОД")
            elif chat in parents and text.startswith("/svodka"):
                tg("sendMessage", chat_id=chat, text=summary(kv_get("state")), parse_mode="HTML", disable_web_page_preview=True)
        if not r:
            time.sleep(5)


def scheduler():
    while True:
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 19 and kv_get("last_weekly") != now.date().isoformat():
            kv_set("last_weekly", now.date().isoformat())
            notify(summary(kv_get("state")))
        time.sleep(60)


@app.on_event("startup")
def start_bg():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    db().close()
    threading.Thread(target=bot_loop, daemon=True).start()
    threading.Thread(target=scheduler, daemon=True).start()
