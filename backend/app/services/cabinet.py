"""Личный кабинет клиента: собирает данные из Kommo в вид, который показывает приложение."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..config import get_settings

from ..kommo.base import KommoClient, KommoContact, KommoLead
from ..kommo.base import KommoFile
from ..kommo.mapping import (CLIENT_FILE_PREFIXES, CLIENT_FILES_FIELD, CLIENT_PIPELINE_IDS, CLIENT_STEPS, CONTACT_FIELDS, LEAD_FIELDS, STATUS_LOST, STATUS_TO_STEP,
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


def build_card(lead: KommoLead, kommo: KommoClient, default_person: str, with_history: bool = True,
               person_contact: KommoContact | None = None) -> ServiceCard | None:
    """Карточка услуги для клиента. None — сделку клиенту не показываем (продажи, провал, другая воронка).

    person_contact — основной контакт сделки (например, ребёнок или супруг в семейной сделке):
    из него берём имя и даты «Виза до» / «ITK до».
    """
    if lead.pipeline_id not in CLIENT_PIPELINE_IDS or lead.status_id == STATUS_LOST:
        return None
    sname = norm(lead.status_name)
    archived = lead.status_id == STATUS_WON
    if not archived and sname not in STATUS_TO_STEP:
        return None
    step_index, state = (3, "done") if archived else STATUS_TO_STEP[sname]

    f = lead.fields
    raw_code = field_value(f, LEAD_FIELDS["service_type"])
    tariff = find_tariff(str(raw_code) if raw_code else None)
    paid = as_int(field_value(f, LEAD_FIELDS["paid_amount"]))
    debt = as_int(field_value(f, LEAD_FIELDS["debt"]))
    price = lead.price or (tariff.price if tariff else 0)
    if debt is not None:
        remaining = max(debt, 0)
    elif paid is not None and price:
        remaining = max(price - paid, 0)
    else:
        remaining = None
    expected = as_date(field_value(f, LEAD_FIELDS["deadline"]))

    person = default_person
    valid_until = None
    if person_contact:
        person = contact_person(person_contact) or default_person
        if tariff and tariff.category in ("kitas", "visa", "ext") and state in ("done", "renewal"):
            key = "itk_until" if tariff.category == "kitas" or "KITAS" in tariff.name.upper() else "visa_until"
            valid_until = as_date(field_value(person_contact.fields, CONTACT_FIELDS[key])) or \
                as_date(field_value(person_contact.fields, CONTACT_FIELDS["visa_until"]))

    # Завершённая сделка с ещё действующей визой/KITAS — это действующая услуга, а не архив
    if archived and valid_until and valid_until >= date.today():
        archived = False
    # Бейдж
    if archived:
        badge, tone = "Завершено", "muted"
    elif state == "wait_payment":
        badge, tone = ("Ждём доплату", "warn") if paid else ("Ждём оплату", "warn")
    elif state in ("done", "renewal"):
        badge, tone = ("Действует", "ok") if valid_until and valid_until >= date.today() else ("Готово", "ok")
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
    title = tariff.name if tariff else (str(raw_code) if raw_code else lead.name)
    if tariff and tariff.category == "buh":
        title = f"Бухгалтерия: {tariff.name[:1].lower()}{tariff.name[1:]}"
    return ServiceCard(
        lead_id=lead.id, title=title, code=tariff.code if tariff else (str(raw_code) if raw_code else None),
        person=person, badge=badge, badge_tone=tone,
        archived=archived, step_index=step_index, steps=steps, price=price, paid=paid, remaining=remaining,
        started_at=lead.created_at.date().isoformat() if lead.created_at else None,
        expected_at=expected.isoformat() if expected else None,
        issued_at=None,
        valid_until=valid_until.isoformat() if valid_until else None,
    )


def _with_fields(base: KommoContact, others: list[KommoContact]) -> KommoContact:
    """Копия контакта, у которой пустые поля дополнены из других контактов."""
    fields = dict(base.fields)
    for c in others:
        for k, v in c.fields.items():
            fields.setdefault(k, v)
    return KommoContact(id=base.id, name=base.name, phones=base.phones, fields=fields, lead_ids=base.lead_ids)


def _cards(kommo: KommoClient, contact: KommoContact, with_history: bool) -> tuple[list[ServiceCard], dict[int, KommoContact]]:
    """Карточки услуг + люди, чьи даты показываем (только из видимых клиенту сделок).

    В сделке может быть несколько контактов: основной (клиент или член семьи) и служебные без имени,
    в которых менеджеры хранят паспортные данные («ITK до», «Виза до»). Безымянные контакты сделки
    считаем тем же человеком, что и основной контакт.
    """
    default_person = contact_person(contact)
    leads = kommo.get_leads(contact.lead_ids)
    ids = sorted({cid for lead in leads for cid in lead.contact_ids[:6]} | {contact.id})
    fetched = {c.id: c for c in kommo.get_contacts(ids)}
    fetched[contact.id] = contact
    people: dict[int, KommoContact] = {}
    cards = []
    for lead in leads:
        lead_contacts = [fetched[i] for i in lead.contact_ids[:6] if i in fetched] or [contact]
        main = lead_contacts[0]
        name = contact_person(main)
        same_as_client = main.id == contact.id or not name or name == default_person
        person = contact if same_as_client else main
        nameless = [c for c in lead_contacts if c is not main and not contact_person(c)]
        if same_as_client and main.id != contact.id:
            nameless.append(main)
        pc = _with_fields(person, nameless)
        card = build_card(lead, kommo, default_person, with_history, person_contact=pc)
        if card:
            cards.append(card)
            people[pc.id] = _with_fields(people[pc.id], [pc]) if pc.id in people else pc
    return cards, people


def merged_contact(kommo: KommoClient, contact_ids: list[int] | int) -> tuple[KommoContact | None, list[KommoContact]]:
    """Основной контакт + дубли того же человека → один контакт: сделки объединяются, пустые поля дополняются."""
    ids = [contact_ids] if isinstance(contact_ids, int) else list(contact_ids)
    if not ids:
        return None, []
    found = {c.id: c for c in (kommo.get_contacts(ids) if len(ids) > 1 else [x for x in [kommo.get_contact(ids[0])] if x])}
    originals = [found[i] for i in ids if i in found]
    if not originals:
        return None, []
    main = originals[0]
    if len(originals) == 1:
        return main, originals
    fields = dict(main.fields)
    for c in originals[1:]:
        for k, v in c.fields.items():
            fields.setdefault(k, v)
    lead_ids = list(dict.fromkeys(i for c in originals for i in c.lead_ids))
    phones = list(dict.fromkeys(p for c in originals for p in c.phones))
    return KommoContact(id=main.id, name=main.name, phones=phones, fields=fields, lead_ids=lead_ids), originals


def load_client(kommo: KommoClient, contact_id: int | list[int], with_history: bool = True) -> dict:
    contact, originals = merged_contact(kommo, contact_id)
    if not contact:
        return {"services": [], "archive": [], "dates": [], "contact": None}
    cards, people = _cards(kommo, contact, with_history)
    people[contact.id] = _with_fields(people[contact.id], [contact]) if contact.id in people else contact
    active = [c for c in cards if not c.archived]
    archive = [c for c in cards if c.archived]
    return {
        "contact": {"id": contact.id, "name": contact_person(contact),
                    "passport_until": _iso(as_date(field_value(contact.fields, CONTACT_FIELDS["passport_until"])))},
        "services": [asdict(c) for c in active],
        "archive": [asdict(c) for c in archive],
        "dates": important_dates(active, list(people.values())),
    }


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def important_dates(cards: list[ServiceCard], people: list[KommoContact], today: date | None = None) -> list[dict]:
    """Ближайшие важные даты по всем членам семьи: окончание визы / KITAS / паспорта, сроки отчётов."""
    today = today or date.today()
    out = []
    for c in people:
        name = contact_person(c)
        for key, title, horizon in (("itk_until", "Окончание KITAS", 3650), ("visa_until", "Окончание визы", 3650),
                                    ("passport_until", "Окончание паспорта", 270)):
            d = as_date(field_value(c.fields, CONTACT_FIELDS[key]))
            visa_type = field_value(c.fields, CONTACT_FIELDS["current_visa"])
            if visa_type and key != "passport_until":
                title = f"{title} {visa_type}"
            if d and 0 <= (d - today).days <= horizon:
                out.append({"date": d.isoformat(), "title": title, "person": name, "lead_id": None, "kind": "expiry" if key != "passport_until" else "passport"})
    for c in cards:
        if c.expected_at and c.code and c.code.upper().startswith("BUH"):
            out.append({"date": c.expected_at, "title": "Срок отчёта по бухгалтерии", "person": c.person, "lead_id": c.lead_id, "kind": "report"})
    seen, uniq = set(), []
    for x in sorted(out, key=lambda x: x["date"]):
        k = (x["date"], x["person"], x["kind"])
        if k not in seen and not (x["date"] < today.isoformat()):
            seen.add(k)
            x["days_left"] = (date.fromisoformat(x["date"]) - today).days
            uniq.append(x)
    return uniq[:5]


def client_files(kommo: KommoClient, lead: KommoLead) -> list[KommoFile]:
    """Файлы сделки, которые можно показать клиенту (см. CLIENT_FILES_FIELD / CLIENT_FILE_PREFIXES)."""
    marked: dict[str, str] = {}
    for v in field_value(lead.fields, f"raw:{CLIENT_FILES_FIELD}") or []:
        if isinstance(v, dict) and v.get("file_uuid") and not v.get("is_deleted"):
            marked[str(v["file_uuid"])] = str(v.get("file_name") or "Документ")
    out: list[KommoFile] = []
    seen: set[str] = set()
    for f in kommo.get_lead_files(lead.id):
        name = (f.name or "").strip()
        if f.uuid in marked or name.lower().startswith(CLIENT_FILE_PREFIXES):
            for pref in CLIENT_FILE_PREFIXES:  # «КЛИЕНТУ — KITAS.pdf» → «KITAS.pdf»
                if name.lower().startswith(pref):
                    name = name[len(pref):].lstrip(" _-—:") or name
                    break
            out.append(KommoFile(uuid=f.uuid, name=marked.get(f.uuid) or name, created_at=f.created_at))
            seen.add(f.uuid)
    for uuid, name in marked.items():  # файл из поля, которого нет в списке файлов сделки
        if uuid not in seen:
            out.append(KommoFile(uuid=uuid, name=name, created_at=None))
    return out


def load_documents(kommo: KommoClient, contact_id: int | list[int]) -> list[dict]:
    """Готовые файлы по всем сделкам клиента, сгруппированные по людям."""
    contact, _ = merged_contact(kommo, contact_id)
    if not contact:
        return []
    cards, _ = _cards(kommo, contact, with_history=False)
    leads = {lead.id: lead for lead in kommo.get_leads([c.lead_id for c in cards])}
    groups: dict[str, list] = {}
    for card in cards:
        lead = leads.get(card.lead_id)
        for f in (client_files(kommo, lead) if lead else []):
            groups.setdefault(card.person, []).append({
                "uuid": f.uuid, "name": f.name, "created_at": f.created_at.date().isoformat() if f.created_at else None,
                "service": card.title, "lead_id": card.lead_id, "archived": card.archived, "valid_until": card.valid_until,
            })
    return [{"person": p, "files": files} for p, files in groups.items()]
