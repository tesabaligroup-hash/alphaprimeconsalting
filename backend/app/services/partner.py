"""Партнёрка: синхронизация начислений из Kommo и данные для партнёрского кабинета."""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..kommo.base import KommoClient, KommoLead
from ..kommo.mapping import (CANCEL_STATUSES, CONTACT_FIELDS, FULLY_PAID_STATUSES, LEAD_FIELDS, RESULT_ISSUED_STATUSES,
                             STATUS_LOST, norm)
from ..models import Accrual, Level2Link, Partner, ProgramSetting, Referral, StopWord
from ..partner_rules import (ACCRUAL_LABELS, DEFAULTS, accrual_status, calc_payouts, codeword_problems, next_payout_date,
                             normalize_codeword, payout_date_for, short_name)
from ..tariffs import find_tariff
from .cabinet import as_int, field_value
from ..timeutil import utcnow

log = logging.getLogger(__name__)


def program_settings(db: Session) -> dict:
    s = dict(DEFAULTS)
    for row in db.scalars(select(ProgramSetting)):
        if row.key in s and isinstance(row.value, dict) and "v" in row.value:
            s[row.key] = row.value["v"]
    return s


def stop_words(db: Session) -> set[str]:
    return {w.word.upper() for w in db.scalars(select(StopWord))}


def check_codeword(db: Session, word: str, partner_id: int | None = None) -> dict:
    s = program_settings(db)
    w = normalize_codeword(word)
    problems = codeword_problems(w, stop_words(db), s["codeword_min_len"])
    taken = db.scalar(select(Partner).where(Partner.codeword == w))
    if taken and taken.id != partner_id:
        problems.append("Это слово уже занято другим партнёром")
    return {"word": w, "ok": not problems, "problems": problems}


def find_partner_for_lead(db: Session, lead: KommoLead) -> Partner | None:
    value = field_value(lead.fields, LEAD_FIELDS["partner"])
    if not value:
        return None
    v = str(value).strip()
    p = db.scalar(select(Partner).where(Partner.kommo_partner_value.ilike(v)))
    if not p:
        p = db.scalar(select(Partner).where(Partner.codeword == normalize_codeword(v)))
    return p


def _first_time(kommo: KommoClient, lead_id: int, statuses: set[str]) -> datetime | None:
    for ch in kommo.get_status_history(lead_id):
        if norm(ch.status_name) in statuses:
            return ch.at
    return None


def sync_lead(db: Session, kommo: KommoClient, lead: KommoLead, now: datetime | None = None) -> list[Accrual]:
    """Создаёт/обновляет начисления партнёрам по одной сделке Kommo."""
    now = now or utcnow()
    partner = find_partner_for_lead(db, lead)
    if not partner or partner.status == "blocked":
        return []
    code = field_value(lead.fields, LEAD_FIELDS["service_type"])
    tariff = find_tariff(str(code) if code else None)
    if not tariff or tariff.code == "CONS":
        return []  # без кода услуги считать нечего; консультации в программе не участвуют
    s = program_settings(db)
    pay = calc_payouts(tariff, s, deal_price=lead.price or None)

    sname = norm(lead.status_name)
    paid = as_int(field_value(lead.fields, LEAD_FIELDS["paid_amount"]))
    price = lead.price or tariff.price
    fully_paid = (paid is not None and paid >= price) or (paid is None and sname in FULLY_PAID_STATUSES)
    cancelled = lead.status_id == STATUS_LOST or sname in CANCEL_STATUSES
    fully_paid_at = _first_time(kommo, lead.id, FULLY_PAID_STATUSES) if fully_paid else None
    issued_at = _first_time(kommo, lead.id, RESULT_ISSUED_STATUSES)
    if fully_paid and not fully_paid_at:
        fully_paid_at = lead.updated_at or now

    contacts = kommo.get_contacts(lead.contact_ids[:1])
    raw_name = None
    if contacts:
        raw_name = field_value(contacts[0].fields, CONTACT_FIELDS["full_name"]) or contacts[0].name
    display = short_name(str(raw_name) if raw_name else lead.name)

    targets: list[tuple[Partner, int, int]] = []
    if partner.kind == "private":
        targets.append((partner, 1, pay.plan_a))
    else:
        targets.append((partner, 1, pay.plan_b_l1))
        link = db.scalar(select(Level2Link).where(Level2Link.business_partner_id == partner.id))
        if link and link.contract_date <= now.date() <= link.end_date:
            l2 = db.get(Partner, link.level2_partner_id)
            if l2 and l2.status != "blocked":
                targets.append((l2, 2, pay.plan_b_l2))

    result = []
    for p, level, amount in targets:
        acc = db.scalar(select(Accrual).where(Accrual.kommo_lead_id == lead.id, Accrual.partner_id == p.id,
                                              Accrual.level == level, Accrual.period == ""))
        if acc is None:
            acc = Accrual(partner_id=p.id, level=level, kommo_lead_id=lead.id, period="", client_display=display, amount=amount)
            db.add(acc)
        if acc.status == "paid":
            result.append(acc)
            continue
        status, hold_until = accrual_status(cancelled=cancelled, fully_paid=fully_paid, result_issued_at=issued_at,
                                            now=now, gold=p.is_gold(now.date()), s=s)
        if acc.status != "to_payout" and status == "to_payout":
            acc.to_payout_at = now
        old = acc.status if acc.id else None
        if old != status:
            acc.__dict__.setdefault("_events", []).append((old, status))
        acc.status = status
        acc.cancel_reason = "Сделка отменена" if status == "cancelled" else None
        acc.amount = amount
        acc.client_display = display
        acc.service_code = tariff.code
        acc.fully_paid_at = fully_paid_at
        acc.result_issued_at = issued_at
        acc.hold_until = hold_until
        result.append(acc)
    db.flush()
    return result


NOTIFY_TEXT = {
    "awaiting_payment": "Ваш друг {name} закреплён за вами. Вознаграждение {amount} IDR начислим, когда он оплатит услугу.",
    "in_work": "{name} оплатил услугу полностью 🎉 Вознаграждение {amount} IDR — в работе.",
    "confirmed": "Услуга для {name} выполнена. {amount} IDR станут доступны к выплате после проверки.",
    "to_payout": "{amount} IDR за {name} — к выплате. Деньги придут {date}.",
    "paid": "Выплата {amount} IDR за {name} отправлена.",
    "cancelled": "Начисление за {name} отменено: {reason}.",
}


def sync_all(db: Session, kommo: KommoClient, since: datetime) -> list[tuple[int, str]]:
    """Обновляет начисления. Возвращает уведомления для партнёров: [(partner_id, текст)]."""
    notes: list[tuple[int, str]] = []
    for lead in kommo.get_leads_updated_since(since):
        try:
            for acc in sync_lead(db, kommo, lead):
                for old, new in acc.__dict__.pop("_events", []):
                    if old is None and new not in ("awaiting_payment", "in_work"):
                        continue  # при первой синхронизации старых сделок не засыпаем партнёра сообщениями
                    when = payout_date_for((acc.to_payout_at or utcnow()).date()).strftime("%d.%m")
                    text = NOTIFY_TEXT[new].format(name=acc.client_display, amount=f"{acc.amount:,}".replace(",", " "),
                                                   date=when, reason=acc.cancel_reason or "")
                    notes.append((acc.partner_id, text))
        except Exception:  # одна сломанная сделка не должна останавливать синхронизацию
            log.exception("Не удалось обработать сделку %s", lead.id)
    db.commit()
    return notes


def dashboard(db: Session, partner: Partner, today: date | None = None) -> dict:
    today = today or date.today()
    s = program_settings(db)
    accs = list(db.scalars(select(Accrual).where(Accrual.partner_id == partner.id).order_by(Accrual.updated_at.desc())))
    to_payout = sum(a.amount for a in accs if a.status == "to_payout")
    expected = sum(a.amount for a in accs if a.status in ("awaiting_payment", "in_work", "confirmed"))
    paid_total = sum(a.amount for a in accs if a.status == "paid")

    month_start = today.replace(day=1)
    q_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=q_month, day=1)
    next_q = date(today.year + 1, 1, 1) if q_month == 10 else date(today.year, q_month + 3, 1)
    quarter_end = next_q - timedelta(days=1)

    def clients_since(start: date) -> int:
        return len({a.kommo_lead_id for a in accs if a.level == 1 and a.status != "cancelled"
                    and a.fully_paid_at and a.fully_paid_at.date() >= start})

    month_clients = clients_since(month_start)
    quarter_clients = clients_since(quarter_start)

    def payout_hint(a: Accrual) -> str | None:
        if a.status == "to_payout" and a.to_payout_at:
            return payout_date_for(a.to_payout_at.date()).isoformat()
        if a.status == "confirmed" and a.hold_until:
            return payout_date_for(a.hold_until.date()).isoformat()
        return None

    friends = [{
        "name": a.client_display, "status": a.status, "status_label": ACCRUAL_LABELS[a.status], "amount": a.amount,
        "level": a.level, "payout_date": payout_hint(a), "cancel_reason": a.cancel_reason,
    } for a in accs]
    return {
        "partner": {"name": partner.display_name, "codeword": partner.codeword, "kind": partner.kind, "plan": partner.plan,
                    "gold": partner.is_gold(today), "gold_until": partner.gold_until.isoformat() if partner.gold_until else None},
        "balance": {"to_payout": to_payout, "expected": expected, "paid_total": paid_total,
                    "next_payout": next_payout_date(today).isoformat(), "min_payout": s["min_payout"]},
        "bonuses": {
            "top_month": {"have": month_clients, "need": s["top_month_threshold"], "amount": s["top_month_bonus"]},
            "gold": {"have": quarter_clients, "need": s["gold_threshold"], "amount": s["gold_bonus"],
                     "days_left": (quarter_end - today).days},
        },
        "rules": {"hold_days": s["hold_days"], "hold_days_gold": s["hold_days_gold"], "min_payout": s["min_payout"]},
        "friends": friends,
    }


def referral_view(r: Referral) -> dict:
    labels = {"pending": "На проверке у менеджера", "attached": "Закреплён", "rejected": "Отменено", "expired": "Закрепление истекло"}
    return {"id": r.id, "name": short_name(r.friend_name), "status": r.status, "status_label": labels.get(r.status, r.status),
            "reject_reason": r.reject_reason, "channel": r.channel, "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None}
