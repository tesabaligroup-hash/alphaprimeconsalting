"""Таблица производства → приложение (17.11.2026).

Сделки в Kommo не закрываются (менеджерам нужна переписка в одной сделке). Что услуга выполнена и партнёру
пора платить — видно по таблице производства (лист «Производство», колонка статуса):
  «Партнерку выплатить» → начисление партнёру «К выплате», услуга клиенту — «Готово»
  «ГОТОВО»              → всем заплатили: начисление «Выплачено»
  «СТОП»                → отменено; остальное — «в работе» («Ждем доплату» — «ожидает оплаты»)
Одна строка таблицы = одна услуга (продление в той же сделке — новая строка).
Даты окончания виз/ITK — с листов «Продления и доступы» и «Новые продления» → в контакт Kommo.
Логины/пароли из таблицы НЕ читаются (их не отдаёт Apps Script).
"""
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..kommo.base import KommoClient, KommoContact
from ..kommo.mapping import CLIENT_PIPELINE_IDS, CONTACT_FIELDS, STATUS_LOST, STATUS_TO_STEP, STATUS_WON, norm
from ..models import Accrual, Level2Link, Partner, User
from ..partner_rules import payout_date_for, short_name
from ..tariffs import BY_CODE
from ..timeutil import utcnow
from .cabinet import as_date, field_value
from .intake import name_matches
from .partner import NOTIFY_TEXT, find_partner_by_value, loose_key

log = logging.getLogger(__name__)

PROGRAM_START = date(2026, 11, 15)  # с этой даты — фиксированные выплаты из таблицы тарифов
READY_STAGE = "услуга готова"

# Как услуги записаны в таблице → код тарифа (для суммы, если в таблице не указана «Доля партнеров»)
SERVICE_CODES = {
    "bank card": "PERSONAL-COUNT", "bridge": "BRIDGE", "voa": "VOA", "voa - ext": "VOA-EXT", "c1": "C1",
    "c1 - ext": "C1-EXT", "e33g": "E33G", "e33g - bridge": "E33G", "e33g - conv": "E33G", "e33g - ext": "E33G-EXT",
    "driver's license": "DRIVER", "family": "E31B/E-1", "family - conv": "E31B/E-1", "family - bridge": "E31B/E-1",
    "family - ext": "E31-EXT-1", "d12 - 1": "D12-1", "d12 - 2": "D12-2", "d12 - ext": "D12-EXT", "pt pma": "PMA-1",
    "e28a": "E28A-1-P", "e28a - conv": "E28A-1-P", "e28a - bridge": "E28A-1-P", "epo": "EPO", "etk": "ETK-OUT", "c18": "C18",
}

STATUS_MAP = {"готово": "paid", "партнерку выплатить": "to_payout", "партнёрку выплатить": "to_payout",
              "стоп": "cancelled", "ждем доплату": "awaiting_payment", "ждём доплату": "awaiting_payment"}
DONE = {"to_payout", "paid"}


def money(v) -> int:
    d = re.sub(r"[^\d-]", "", str(v or ""))
    try:
        return int(d) if d not in ("", "-") else 0
    except ValueError:
        return 0


def parse_date(v) -> date | None:
    s = str(v or "").strip()
    m = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


@dataclass
class Row:
    n: int  # номер строки в таблице
    start: date | None
    manager: str
    partner: str
    service: str
    contacts: str
    status_raw: str
    client: str
    price: int
    paid: int
    debt: int
    partner_share: int
    lead_id: int | None = None  # колонка AA «ID сделки» (ставит автозаявка)

    @property
    def status(self) -> str:
        return STATUS_MAP.get(norm(self.status_raw), "in_work")

    @property
    def key(self) -> str:
        """Строка таблицы без номера (номера строк сдвигаются при вставке): клиент + услуга + дата начала."""
        raw = f"{loose_key(self.client)}|{norm(self.service)}|{self.start}"
        return "t:" + hashlib.sha1(raw.encode()).hexdigest()[:14]


@dataclass
class Renewal:
    visa: str
    client: str
    status: str
    until: date | None


@dataclass
class Table:
    rows: list[Row] = field(default_factory=list)
    renewals: list[Renewal] = field(default_factory=list)
    partner_contacts: dict[str, str] = field(default_factory=dict)  # имя партнёра (как в таблице) → контакт


def fetch_table() -> Table:
    """Читает таблицу через Apps Script (doGet). Пароли/логины скрипт не отдаёт."""
    s = get_settings()
    r = httpx.get(s.intake_script_url, params={"secret": s.intake_script_secret}, timeout=120, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "таблица не ответила")
    return parse_table(data)


def lead_id_of(v) -> int | None:
    """ID сделки Kommo из колонки AA: только целое из 8–10 цифр без пробелов и знаков (суммы вида «2 500 000» не подходят)."""
    s = str(v or "").strip()
    return int(s) if re.fullmatch(r"\d{8,10}", s) else None


def parse_table(data: dict) -> Table:
    t = Table()
    for x in data.get("production") or []:
        n, start, manager, partner, service, contacts, status, client, price, paid, debt, share, lead = (list(x) + [""] * 13)[:13]
        if not str(client).strip() or not str(service).strip():
            continue
        t.rows.append(Row(int(n or 0), parse_date(start), str(manager).strip(), str(partner).strip(), str(service).strip(),
                          str(contacts).strip(), str(status).strip(), str(client).strip(), money(price), money(paid),
                          money(debt), money(share), lead_id_of(lead)))
    for x in data.get("renewals") or []:
        visa, client, status, until = (list(x) + [""] * 4)[:4]
        if str(client).strip():
            t.renewals.append(Renewal(str(visa).strip(), str(client).strip(), str(status).strip(), parse_date(until)))
    for x in data.get("partners") or []:
        name, contact, keyword = (list(x) + ["", "", ""])[:3]
        contact = str(contact).strip()
        for key in (name, keyword):
            if str(key).strip() and contact:
                t.partner_contacts.setdefault(norm(str(key)), contact)
    return t


# ---------- партнёры ----------

def resolve_partner(db: Session, name: str, contacts: dict[str, str]) -> Partner | None:
    """Имя из колонки «ПАРТНЕР» → партнёр приложения: по самому имени (кодовое слово, ник, как в Kommo),
    иначе по контакту из листа «Список партнеров» (t.me/ник или телефон WhatsApp)."""
    if not name:
        return None
    p = find_partner_by_value(db, name)
    if p:
        return p
    contact = contacts.get(norm(name), "")
    m = re.search(r"(?:t\.me/|@)([A-Za-z0-9_]{4,})", contact)
    if m:
        p = db.scalar(select(Partner).join(User, Partner.user_id == User.id).where(User.telegram_username.ilike(m[1])))
        if p:
            return p
    digits = re.sub(r"\D", "", contact.split(".")[0])
    if len(digits) >= 9:
        for u in db.scalars(select(User).where(User.phone.is_not(None))):
            if re.sub(r"\D", "", u.phone or "")[-9:] == digits[-9:] and u.partner:
                return u.partner
    return None


def amount_for(row: Row) -> tuple[int, int]:
    """(1-й уровень, 2-й уровень). Сумма — из колонки «Доля партнеров», иначе — по таблице тарифов."""
    t = BY_CODE.get(SERVICE_CODES.get(norm(row.service), ""))
    l1 = row.partner_share or ((t.l1 or 0) if t else 0)
    l2 = (t.l2 or 0) if t and row.start and row.start >= PROGRAM_START else 0
    return l1, l2


def sync_accruals(db: Session, table: Table, notify: bool = True) -> tuple[list[tuple[int, str]], dict]:
    """Начисления партнёрам по строкам таблицы. Возвращает (уведомления, отчёт)."""
    now = utcnow()
    notes: list[tuple[int, str]] = []
    report = {"rows_with_partner": 0, "unknown_partners": {}, "no_amount": 0, "accruals": 0}
    seen: set[tuple[int, int, str]] = set()
    cache: dict[str, Partner | None] = {}
    for row in table.rows:
        if not row.partner:
            continue
        report["rows_with_partner"] += 1
        if row.partner not in cache:
            cache[row.partner] = resolve_partner(db, row.partner, table.partner_contacts)
        p = cache[row.partner]
        if not p:
            report["unknown_partners"][row.partner] = report["unknown_partners"].get(row.partner, 0) + 1
            continue
        l1, l2 = amount_for(row)
        targets = [(p, 1, l1)]
        link = db.scalar(select(Level2Link).where(Level2Link.business_partner_id == p.id))
        if l2 and link and row.start and link.contract_date <= row.start <= link.end_date:
            p2 = db.get(Partner, link.level2_partner_id)
            if p2 and p2.id != p.id:
                targets.append((p2, 2, l2))
        for partner, level, amount in targets:
            if amount <= 0:
                report["no_amount"] += 1
                continue
            seen.add((partner.id, level, row.key))
            acc = db.scalar(select(Accrual).where(Accrual.kommo_lead_id == 0, Accrual.partner_id == partner.id,
                                                  Accrual.level == level, Accrual.period == row.key))
            new = acc is None
            if new:
                acc = Accrual(partner_id=partner.id, level=level, kommo_lead_id=0, period=row.key,
                              client_display=short_name(row.client), amount=amount, status=row.status)
                db.add(acc)
            old = None if new else acc.status
            acc.amount, acc.service_code = amount, SERVICE_CODES.get(norm(row.service)) or row.service[:32]
            acc.client_display = short_name(row.client)
            if row.start and not acc.fully_paid_at and row.status != "awaiting_payment":
                acc.fully_paid_at = datetime.combine(row.start, datetime.min.time())
            if acc.decision != "paid":  # отметка «Выплачено» в админке важнее таблицы
                acc.status = row.status
            if acc.status == "to_payout" and old != "to_payout":
                acc.to_payout_at = now
            if acc.status == "cancelled":
                acc.cancel_reason = "услуга остановлена"
            report["accruals"] += 1
            if notify and not new and old != acc.status and acc.status in ("to_payout", "paid"):
                when = payout_date_for((acc.to_payout_at or now).date()).strftime("%d.%m")
                text = NOTIFY_TEXT[acc.status].format(name=acc.client_display, amount=f"{amount:,}".replace(",", " "),
                                                      amount_part=f" {amount:,} IDR".replace(",", " "), date=when, reason="")
                notes.append((partner.id, text))
    # строки, которых больше нет в таблице (удалили/переименовали) — убираем невыплаченные начисления
    for acc in db.scalars(select(Accrual).where(Accrual.kommo_lead_id == 0, Accrual.period.like("t:%"))):
        if (acc.partner_id, acc.level, acc.period) not in seen and acc.status != "paid":
            db.delete(acc)
    # Начисления по сделкам Kommo («ожидается» до продажи) убираем, когда эта услуга появилась в таблице:
    # по ID сделки или по тому же другу у того же партнёра
    table_leads = {r.lead_id for r in table.rows if r.lead_id}
    covered: set[tuple[int, str]] = set()
    for row in table.rows:
        p = cache.get(row.partner) if row.partner else None
        if p:
            covered.add((p.id, short_name(row.client).lower()))
    for acc in db.scalars(select(Accrual).where(Accrual.period == "")):
        if acc.kommo_lead_id in table_leads or (acc.partner_id, (acc.client_display or "").lower()) in covered:
            db.delete(acc)
    db.commit()
    return notes, report


# ---------- Kommo: контакты, даты виз, этапы ----------

def contact_names(c: KommoContact) -> list[str]:
    return [str(field_value(c.fields, CONTACT_FIELDS["full_name"]) or ""), c.name]


def match_contacts(name: str, contacts: list[KommoContact], index: dict[str, list[KommoContact]]) -> list[KommoContact]:
    words = [loose_key(w) for w in re.split(r"[\s,]+", name) if len(w) >= 3]
    cands: dict[int, KommoContact] = {}
    for w in words:
        for c in index.get(w, []):
            cands[c.id] = c
    return [c for c in cands.values() if name_matches(name, contact_names(c))]


def build_index(contacts: list[KommoContact]) -> dict[str, list[KommoContact]]:
    idx: dict[str, list[KommoContact]] = {}
    for c in contacts:
        for n in contact_names(c):
            for w in re.split(r"[\s,]+", n or ""):
                if len(w) >= 3:
                    idx.setdefault(loose_key(w), []).append(c)
    return idx


def is_itk(visa: str) -> bool:
    return bool(re.match(r"\s*(E\d|KITAS|ITAS|ITK|FAMILY)", visa or "", re.I))


def visa_updates(table: Table, contacts: list[KommoContact], today: date | None = None) -> tuple[list[dict], dict]:
    """Какие даты «Виза до»/«ITK до» записать в контакты. Берём самую позднюю дату по человеку."""
    today = today or date.today()
    idx = build_index(contacts)
    best: dict[str, Renewal] = {}
    for r in table.renewals:
        if not r.until or r.until < today - timedelta(days=60) or norm(r.status) == "close":
            continue
        k = loose_key(r.client)
        if k not in best or r.until > best[k].until:
            best[k] = r
    plan, report = [], {"rows": len(best), "not_found": [], "same": 0}
    for r in best.values():
        found = match_contacts(r.client, contacts, idx)
        if not found:
            report["not_found"].append(f"{r.client} ({r.visa}, до {r.until:%d.%m.%Y})")
            continue
        fname = CONTACT_FIELDS["itk_until" if is_itk(r.visa) else "visa_until"]
        for c in found:
            if as_date(field_value(c.fields, fname)) == r.until:
                report["same"] += 1
                continue
            plan.append({"contact_id": c.id, "contact": c.name, "client": r.client, "field": fname, "date": r.until,
                         "was": as_date(field_value(c.fields, fname)), "visa": r.visa})
    return plan, report


def stage_moves(kommo: KommoClient, table: Table, contacts: list[KommoContact]) -> tuple[list[dict], list[str]]:
    """Сделки, которые можно перевести в «Услуга готова»: по клиенту в таблице ВСЕ строки выполнены,
    сделка одна, открыта и ещё на этапе до «готово», и попала на этот этап не позже последней строки таблицы."""
    idx = build_index(contacts)
    by_client: dict[str, list[Row]] = {}
    for row in table.rows:
        by_client.setdefault(loose_key(row.client), []).append(row)
    moves, doubts = [], []
    # сначала собираем клиентов, у которых все строки выполнены, и все их сделки — одним пакетом
    done_clients = []
    for rows in by_client.values():
        if any(r.status not in DONE for r in rows):
            continue
        found = match_contacts(rows[0].client, contacts, idx)
        lead_ids = sorted({lid for c in found for lid in c.lead_ids})
        if lead_ids:
            done_clients.append((rows, lead_ids))
    all_ids = sorted({i for _, ids in done_clients for i in ids})
    leads_by_id = {l.id: l for l in kommo.get_leads(all_ids)} if all_ids else {}
    # клиенты, у которых в таблице есть НЕ выполненные строки, — их сделки (семейные тоже) не трогаем
    busy_ids: set[int] = set()
    for rows in by_client.values():
        if any(r.status not in DONE for r in rows):
            for c in match_contacts(rows[0].client, contacts, idx):
                busy_ids.update(c.lead_ids)
    cand: dict[int, dict] = {}
    for rows, lead_ids in done_clients:
        last = max((r.start for r in rows if r.start), default=None)
        leads = [leads_by_id[i] for i in lead_ids if i in leads_by_id]
        leads = [l for l in leads if l.pipeline_id in CLIENT_PIPELINE_IDS and l.status_id not in (STATUS_WON, STATUS_LOST)]
        early = [l for l in leads if STATUS_TO_STEP.get(norm(l.status_name), (2, ""))[0] < 2]
        if not early:
            continue
        if len(early) > 1:
            doubts.append(f"{rows[0].client}: несколько открытых сделок — не трогаем")
            continue
        lead = early[0]
        if STATUS_TO_STEP.get(norm(lead.status_name), (0, ""))[1] == "wait_payment":
            doubts.append(f"{rows[0].client}: в таблице выполнено, а в Kommo «{lead.status_name}» — проверьте оплату, не трогаем")
            continue
        if lead.id in busy_ids:
            doubts.append(f"{rows[0].client}: в этой сделке есть человек с невыполненной услугой — не трогаем")
            continue
        c = cand.setdefault(lead.id, {"lead": lead, "clients": [], "last": last})
        c["clients"].append(rows[0].client)
        if last and (not c["last"] or last > c["last"]):
            c["last"] = last
    for lead_id, c in cand.items():
        lead = c["lead"]
        try:
            hist = [h.at for h in kommo.get_status_history(lead_id) if h.status_id == lead.status_id]
        except Exception:
            doubts.append(f"{', '.join(c['clients'])}: Kommo не отдал историю сделки — пропускаем")
            continue
        entered = max(hist) if hist else lead.created_at
        if c["last"] and entered and entered.date() > c["last"] + timedelta(days=3):
            doubts.append(f"{', '.join(c['clients'])}: сделка встала на «{lead.status_name}» позже последней строки таблицы — "
                          "похоже, новая услуга ещё не внесена")
            continue
        moves.append({"lead_id": lead_id, "client": ", ".join(c["clients"]), "from": lead.status_name,
                      "pipeline_id": lead.pipeline_id})
    return moves, doubts


def apply_kommo(kommo: KommoClient, plan: list[dict], moves: list[dict], move_stages: bool) -> tuple[int, int]:
    by_contact: dict[int, dict] = {}
    for p in plan:
        by_contact.setdefault(p["contact_id"], {})[p["field"]] = p["date"]
    for cid, values in by_contact.items():
        try:
            kommo.update_fields("contacts", cid, values)
        except Exception:
            log.exception("Не записалась дата визы в контакт %s", cid)
    moved = 0
    if move_stages:
        ids: dict[int, int | None] = {}
        for m in moves:
            if m["pipeline_id"] not in ids:
                ids[m["pipeline_id"]] = kommo.status_id(m["pipeline_id"], READY_STAGE)
            sid = ids[m["pipeline_id"]]
            if sid:
                try:
                    kommo.move_lead(m["lead_id"], sid)
                    moved += 1
                except Exception:
                    log.exception("Не удалось перевести сделку %s", m["lead_id"])
    return len(by_contact), moved


def run(db: Session, kommo: KommoClient, apply: bool, move_stages: bool, notify: bool = True,
        partners: bool = True) -> dict:
    """Полный проход: начисления, даты виз, этапы. apply=False — только отчёт."""
    table = fetch_table()
    contacts = kommo.all_contacts()
    plan, vrep = visa_updates(table, contacts)
    moves, doubts = stage_moves(kommo, table, contacts)
    out = {"table_rows": len(table.rows), "renewal_rows": len(table.renewals), "visa": vrep, "visa_plan": plan,
           "moves": moves, "doubts": doubts}
    if apply:
        if partners:
            out["notes"], out["partners"] = sync_accruals(db, table, notify=notify)
        else:
            out["notes"], out["partners"] = [], _dry_partners(db, table)
        out["contacts_updated"], out["moved"] = apply_kommo(kommo, plan, moves, move_stages)
    else:
        out["notes"], out["partners"] = [], _dry_partners(db, table)
    return out


def _dry_partners(db: Session, table: Table) -> dict:
    rep = {"rows_with_partner": 0, "matched": {}, "unknown_partners": {}}
    cache: dict[str, Partner | None] = {}
    for row in table.rows:
        if not row.partner:
            continue
        rep["rows_with_partner"] += 1
        if row.partner not in cache:
            cache[row.partner] = resolve_partner(db, row.partner, table.partner_contacts)
        p = cache[row.partner]
        bucket = rep["matched"] if p else rep["unknown_partners"]
        label = f"{row.partner} → {p.display_name}" if p else row.partner
        bucket[label] = bucket.get(label, 0) + 1
    return rep
