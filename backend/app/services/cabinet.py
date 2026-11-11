"""Личный кабинет клиента: собирает данные из Kommo в вид, который показывает приложение."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..config import get_settings

from ..kommo.base import KommoClient, KommoLead
from ..kommo.mapping import (CLIENT_STEPS, CONTACT_FIELDS, HIDDEN_STATUSES, LEAD_FIELDS, STATUS_LOST, STATUS_TO_STEP,
                             STATUS_WON, norm)
from ..tariffs import find_tariff


def field_value(fields: dict, name: str):
    target = norm(name)
    for k, v in fields.items():
        if norm(k) == target:
            return v
    return None


def as_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        # Kommo хранит даты как полночь в часовом поясе аккаунта (Бали, UTC+8)
        return datetime.fromtimestamp(int(value), tz=ZoneInfo(get_settings().timezone)).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    return None


def as_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(" ", "").replace(",", ".")))
    except ValueError:
        return None


def person_title(raw: str | None) -> str:
    """«ANNA DIKINA» → «Anna», «аня молочко» → «Аня»: первое слово с заглавной буквы."""
    if not raw or not str(raw).strip():
        return ""
    first = str(raw).split()[0].strip("@")
    return first[:1].upper() + first[1:].lower() if first.isupper() or first.islower() else first


def contact_person(contact) -> str:
    """Как называть клиента: имя карточки в Kommo, иначе имя из паспорта."""
    return person_title(contact.name) or person_title(field_value(contact.fields, CONTACT_FIELDS["full_name"]))


@dataclass
class Step:
    title: str
    state: str  # done / current / todo
    at: str | None = None  # ISO-время, когда шаг выполнен


@dataclass
class ServiceCard:
    lead_id: int
    title: str
    code: str | None
    person: str
    badge: str
    badge_tone: str  # warn / ok / info / muted
    archived: bool
    step_index: int
    steps: list[Step] = field(default_factory=list)
    price: int = 0
    paid: int | None = None
    remaining: int | None = None
    started_at: str | None = None
    expected_at: str | None = None
    issued_at: str | None = None
    valid_until: str | None = None


def build_card(lead: KommoLead, kommo: KommoClient, default_person: str, with_history: bool = True) -> ServiceCard | None:
    sname = norm(lead.status_name)
    if lead.status_id == STATUS_LOST or sname in HIDDEN_STATUSES:
        return None
    archived = lead.status_id == STATUS_WON
    step_index, state = STATUS_TO_STEP.get(sname, (3, "done") if archived else (2, "active"))
    if archived:
        step_index, state = 3, "done"

    f = lead.fields
    code = field_value(f, LEAD_FIELDS["service_type"])
    tariff = find_tariff(str(code) if code else None)
    paid = as_int(field_value(f, LEAD_FIELDS["paid_amount"]))
    price = lead.price or (tariff.price if tariff else 0)
    remaining = max(price - paid, 0) if paid is not None and price else None
    valid_until = as_date(field_value(f, LEAD_FIELDS["valid_until"]))
    issued = as_date(field_value(f, LEAD_FIELDS["issued_at"]))
    expected = as_date(field_value(f, LEAD_FIELDS["deadline"]))
    person = person_title(field_value(f, LEAD_FIELDS["person_name"])) or default_person

    # Бейдж
    if archived:
        badge, tone = "Завершено", "muted"
    elif state == "wait_payment":
        badge, tone = ("Ждём доплату", "warn") if paid else ("Ждём оплату", "warn")
    elif state in ("done", "renewal"):
        if valid_until and valid_until >= date.today():
            badge, tone = "Действует", "ok"
        else:
            badge, tone = "Готово", "ok"
    else:
        badge, tone = "В работе", "info"

    # Время выполнения шагов — по истории смены этапов
    done_at: dict[int, datetime] = {}
    if with_history:
        for ch in kommo.get_status_history(lead.id):
            idx, st = STATUS_TO_STEP.get(norm(ch.status_name), (None, None))
            if idx is None:
                continue
            reached = idx + (1 if st in ("done", "renewal") else 0)
            for i in range(reached):
                done_at.setdefault(i, ch.at)
    steps = []
    for i, title in enumerate(CLIENT_STEPS):
        if i < step_index or (i == step_index and state in ("done", "renewal")):
            s = "done"
        elif i == step_index:
            s = "current"
        else:
            s = "todo"
        at = done_at.get(i)
        steps.append(Step(title=title, state=s, at=at.isoformat() if at and s == "done" else None))

    # «Подача в иммиграцию» — только для виз и KITAS; у компаний и бухгалтерии этот шаг — «В работе»
    if not tariff or tariff.category not in ("kitas", "visa", "ext"):
        steps[2].title = "В работе"
    title = tariff.name if tariff else lead.name
    if tariff and tariff.category == "buh":
        title = f"Бухгалтерия: {tariff.name[:1].lower()}{tariff.name[1:]}"
    return ServiceCard(
        lead_id=lead.id, title=title, code=str(code) if code else None, person=person, badge=badge, badge_tone=tone,
        archived=archived, step_index=step_index, steps=steps, price=price, paid=paid, remaining=remaining,
        started_at=lead.created_at.date().isoformat() if lead.created_at else None,
        expected_at=expected.isoformat() if expected else None,
        issued_at=issued.isoformat() if issued else None,
        valid_until=valid_until.isoformat() if valid_until else None,
    )


def load_client(kommo: KommoClient, contact_id: int, with_history: bool = True) -> dict:
    contact = kommo.get_contact(contact_id)
    if not contact:
        return {"services": [], "archive": [], "dates": [], "contact": None}
    default_person = contact_person(contact)
    cards = []
    for lead in kommo.get_leads(contact.lead_ids):
        card = build_card(lead, kommo, default_person, with_history)
        if card:
            cards.append(card)
    active = [c for c in cards if not c.archived]
    archive = [c for c in cards if c.archived]
    return {
        "contact": {"id": contact.id, "name": default_person,
                    "passport_until": _iso(as_date(field_value(contact.fields, CONTACT_FIELDS["passport_until"])))},
        "services": [asdict(c) for c in active],
        "archive": [asdict(c) for c in archive],
        "dates": important_dates(active, contact.fields, default_person),
    }


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def important_dates(cards: list[ServiceCard], contact_fields: dict, person: str, today: date | None = None) -> list[dict]:
    """Ближайшие важные даты по всем услугам и членам семьи."""
    today = today or date.today()
    out = []
    for c in cards:
        if c.valid_until:
            d = date.fromisoformat(c.valid_until)
            if d >= today:
                out.append({"date": c.valid_until, "title": f"Окончание: {c.title}", "person": c.person, "lead_id": c.lead_id, "kind": "expiry"})
        if c.expected_at and c.code and c.code.upper().startswith("BUH"):
            out.append({"date": c.expected_at, "title": "Срок отчёта по бухгалтерии", "person": c.person, "lead_id": c.lead_id, "kind": "report"})
    passport = as_date(field_value(contact_fields, CONTACT_FIELDS["passport_until"]))
    if passport and 0 <= (passport - today).days <= 270:
        out.append({"date": passport.isoformat(), "title": "Окончание паспорта", "person": person, "lead_id": None, "kind": "passport"})
    for x in out:
        x["days_left"] = (date.fromisoformat(x["date"]) - today).days
    return sorted(out, key=lambda x: x["date"])[:5]


def load_documents(kommo: KommoClient, contact_id: int) -> list[dict]:
    """Готовые файлы по всем сделкам клиента, сгруппированные по людям."""
    contact = kommo.get_contact(contact_id)
    if not contact:
        return []
    default_person = contact_person(contact)
    groups: dict[str, list] = {}
    for lead in kommo.get_leads(contact.lead_ids):
        card = build_card(lead, kommo, default_person, with_history=False)
        if not card:
            continue
        for f in kommo.get_lead_files(lead.id):
            groups.setdefault(card.person, []).append({
                "uuid": f.uuid, "name": f.name, "created_at": f.created_at.date().isoformat() if f.created_at else None,
                "service": card.title, "lead_id": lead.id, "archived": card.archived, "valid_until": card.valid_until,
            })
    return [{"person": p, "files": files} for p, files in groups.items()]
