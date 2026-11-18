"""Автозаявка в производство и проверка готовой визы.

1) Сделка встала на «Оплата получена» → ИИ читает документы из «Файлов» сделки (паспорт, фото…), строка в
   Google-таблицу производства + папка на Диске, пустые поля контакта (ФИО, гражданство, паспорт до) — в Kommo,
   чего не хватает — в группу менеджеров.
2) Сделка встала на «Услуга готова» (менеджер приложил визу/ITK) → ИИ сверяет имя, файл отмечается «для клиента»
   (поле «Документы клиенту» → появляется в приложении), даты «Виза до»/«ITK до» — в контакт, клиенту — сообщение.
"""
import base64
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai_docs import mime_for, read_document
from ..kommo.base import KommoClient, KommoLead
from ..kommo.mapping import CLIENT_FILES_FIELD, CLIENT_PIPELINE_IDS, CONTACT_FIELDS, LEAD_FIELDS, NO_PARTNER_VALUES, norm
from ..models import IntakeRecord, ProgramSetting, ReminderSent, User
from ..tariffs import find_tariffs
from ..notify import kommo_lead_url, notify_managers, notify_user
from ..sheets import send_intake
from ..timeutil import utcnow
from .cabinet import as_date, as_int, field_value
from .partner import find_partner_for_lead, loose_key

log = logging.getLogger(__name__)

PAID_STATUSES = {"оплата получена"}
READY_STATUSES = {"услуга готова"}
MAX_FILES = 15
MAX_UPLOAD = 30 * 1024 * 1024
DOC_RU = {"passport": "паспорт", "photo": "фото", "visa": "виза", "itk": "ITK", "other": "другое", "unknown": "не прочитан"}


def _d(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def service_of(lead: KommoLead) -> str:
    return str(field_value(lead.fields, LEAD_FIELDS["service_type"]) or lead.name or "")


def is_kitas(service: str) -> bool:
    return bool(re.search(r"\b(E\d|KITAS|ITAS|ITK)", service, re.I))


def needs_photo(service: str) -> bool:
    return bool(re.search(r"\b(E\d|C\d|D\d|KITAS|ITAS|VISA|ВИЗ)", service, re.I))


def check_missing(docs: list[dict], service: str, today: date) -> list[str]:
    out = []
    passports = [d for d in docs if d.get("doc_type") == "passport"]
    if not passports:
        out.append("нет паспорта")
    else:
        exp = _d(passports[0].get("passport_expiry"))
        if exp and exp < today + timedelta(days=183):
            out.append(f"паспорт до {exp:%d.%m.%Y} — меньше 6 месяцев")
        elif exp and is_kitas(service) and exp < today + timedelta(days=548):
            out.append(f"паспорт до {exp:%d.%m.%Y} — для KITAS проверить срок (меньше 18 мес.)")
    if needs_photo(service) and not any(d.get("doc_type") == "photo" for d in docs):
        out.append("нет фото")
    for d in docs:
        if d.get("note"):
            out.append(f"{d.get('file')}: {d['note']}")
    return out


def name_matches(doc_name: str | None, known: list[str | None]) -> bool:
    words = {loose_key(w) for w in re.split(r"[\s,]+", doc_name or "") if len(w) >= 3}
    words.discard("")
    if not words:
        return False
    for k in known:
        kw = {loose_key(w) for w in re.split(r"[\s,]+", k or "") if len(w) >= 3}
        common = words & kw
        if len(common) >= 2 or (common and len(words) == 1):
            return True
    return False


def _started_at(db: Session) -> datetime:
    row = db.get(ProgramSetting, "intake_started_at")
    if not row:
        row = ProgramSetting(key="intake_started_at", value={"at": utcnow().isoformat()})
        db.add(row)
        db.commit()
    return datetime.fromisoformat(row.value["at"])


def _entered_at(kommo: KommoClient, lead_id: int, statuses: set[str]) -> datetime | None:
    times = [h.at for h in kommo.get_status_history(lead_id) if norm(h.status_name) in statuses]
    return max(times) if times else None


def _read_files(kommo: KommoClient, lead_id: int, skip: set[str] = frozenset()) -> list[tuple]:
    out = []
    for f in kommo.get_lead_files(lead_id)[:MAX_FILES]:
        if f.uuid in skip:
            continue
        got = kommo.fetch_file(f.uuid)
        if not got:
            out.append((f, None, {"doc_type": "unknown", "file": f.name, "note": "файл не скачался из Kommo"}))
            continue
        data, name = got
        info = read_document(data, name)
        info["file"] = name
        out.append((f, data, info))
    return out


# Как услуги пишутся на листе «Производство» (обратно к table_sync.SERVICE_CODES)
TABLE_LABEL = {"PERSONAL-COUNT": "Bank Card", "BRIDGE": "Bridge", "VOA": "VOA", "VOA-EXT": "VOA - ext", "C1": "C1",
               "C1-EXT": "C1 - ext", "E33G": "E33G", "E33G-EXT": "E33G - ext", "DRIVER": "Driver's license",
               "E31B/E-1": "Family", "E31B/E-2": "Family", "E31-EXT-1": "Family - ext", "E31-EXT-2": "Family - ext",
               "D12-1": "D12 - 1", "D12-2": "D12 - 2", "D12-EXT": "D12 - ext", "PMA-1": "PT PMA", "E28A-1-P": "E28A",
               "E28A-2-P": "E28A", "EPO": "EPO", "ETK-OUT": "ETK", "C18": "C18"}
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def _people(kommo: KommoClient, lead: KommoLead, passports: list[dict]) -> list[tuple]:
    """Люди сделки (семья — каждый своей строкой): (контакт, имя как в паспорте, паспорт)."""
    contacts = kommo.get_contacts(lead.contact_ids[:8]) if lead.contact_ids else []
    out, used = [], set()
    for c in contacts:
        names = [str(field_value(c.fields, CONTACT_FIELDS["full_name"]) or ""), c.name]
        pp = next((p for i, p in enumerate(passports) if i not in used and name_matches(p.get("full_name"), names)), None)
        if pp is None and len(contacts) == 1 and passports:
            pp = passports[0]
        if pp is not None:
            used.add(passports.index(pp))
        out.append((c, (pp or {}).get("full_name") or names[0] or c.name, pp or {}))
    for i, p in enumerate(passports):  # паспорт есть, а контакта в сделке нет — тоже строка, менеджер добавит контакт
        if i not in used and p.get("full_name"):
            out.append((None, p["full_name"], p))
    return out or [(None, lead.name, {})]


AGREED_FIELD = "Закрепили"  # поле сделки (если создадут) — договорённости для производства


def agreed_text(kommo: KommoClient, lead: KommoLead) -> str:
    """Что менеджер «закрепил» с клиентом (должность, компания, детали визы): поле «Закрепили» или
    последнее примечание сделки со словом «закреп…» (менеджер пишет его последним сообщением)."""
    v = field_value(lead.fields, AGREED_FIELD)
    if v:
        return str(v).strip()
    notes = [t for _, t in kommo.get_lead_notes(lead.id) if re.search(r"закреп", t, re.I)]
    return notes[-1].strip()[:1500] if notes else ""


def _contact_extra(c) -> dict:
    if not c:
        return {}
    emails = c.fields.get("code:EMAIL") or []
    folder = re.search(r"https://drive\.google\.com/[^\s,]+", " ".join(str(x) for x in (c.fields.get("raw:Документы") or [])))
    return {"email": str(emails[0]) if emails else "", "address": str(field_value(c.fields, "Адрес в инд.") or ""),
            "instagram": str(field_value(c.fields, "Instagram") or ""), "folder": folder.group(0) if folder else ""}


def process_paid(db: Session, kommo: KommoClient, lead: KommoLead, apply: bool = True) -> dict | None:
    """Заявка в производство: строка на каждого человека и каждую услугу. Возвращает отчёт."""
    if db.get(IntakeRecord, lead.id):
        return None
    read = _read_files(kommo, lead.id)
    docs = [info for _, _, info in read]
    passports = [d for d in docs if d.get("doc_type") == "passport"]
    service = service_of(lead)
    today = date.today()
    missing = check_missing(docs, service, today)
    people = _people(kommo, lead, passports)
    tariffs = find_tariffs(service)
    partner = find_partner_for_lead(db, lead)
    raw_partner = field_value(lead.fields, LEAD_FIELDS["partner"])
    partner_word = (partner.codeword if partner and partner.codeword else
                    (str(raw_partner) if raw_partner and norm(str(raw_partner)) not in NO_PARTNER_VALUES else ""))
    paid = as_int(field_value(lead.fields, LEAD_FIELDS["paid_amount"]))
    debt = as_int(field_value(lead.fields, LEAD_FIELDS["debt"]))
    deadline = as_date(field_value(lead.fields, LEAD_FIELDS["deadline"]))
    manager = kommo.user_name(lead.responsible_user_id)
    docs_text = "; ".join(f"{DOC_RU.get(d.get('doc_type'), d.get('doc_type'))} — {d.get('file')}" for d in docs) or "в сделке нет файлов"
    agreed = agreed_text(kommo, lead)
    services = tariffs or [None]
    n_rows = len(people) * len(services)
    rows, first = [], True
    for c, pname, pp in people:
        phone = c.phones[0] if c and c.phones else ""
        ex = _contact_extra(c)
        contacts_cell = ", ".join(x for x in (phone, ex.get("email"), ex.get("instagram")) if x)
        comment = "; ".join(x for x in ((f"Закрепили: {agreed}" if agreed else ""), (f"Адрес: {ex['address']}" if ex.get("address") else ""),
                                        "; ".join(missing)) if x)
        for t in services:
            price = (t.price if t and n_rows > 1 else lead.price) or ""
            rows.append([today.year, MONTHS[today.month - 1], today.strftime("%d.%m.%Y"), manager, partner_word, "",
                         TABLE_LABEL.get(t.code, t.code) if t else service, "Kommo", contacts_cell, docs_text, ex.get("folder") or "{folder}",
                         deadline.strftime("%d.%m.%Y") if deadline else "", "", "1. Подать документы", pname, "", "",
                         comment, "", price, "", (paid if first and paid is not None else ""),
                         (debt if first and debt is not None else ""), ((t.l1 or "") if t and partner_word else ""), "", "",
                         lead.id, "Новая — проверить данные ИИ", kommo_lead_url(lead.id) or ""])
            first = False
    client = people[0][1]
    report = {"lead_id": lead.id, "client": client, "service": service, "docs": docs, "missing": missing, "rows": rows,
              "people": [p[1] for p in people], "agreed": agreed}
    if not apply:
        return report

    files = [{"name": info["file"], "mime": mime_for(info["file"], data) or "application/octet-stream",
              "data": base64.b64encode(data).decode()} for _, data, info in read if data]
    total, upload = 0, []
    for f in files:
        size = len(f["data"]) * 3 // 4
        if total + size <= MAX_UPLOAD:
            upload.append(f)
            total += size
    folder = f"{client} — {service} — {lead.id}"[:150]
    client_folder = next((_contact_extra(c).get("folder") for c, _, _ in people if _contact_extra(c).get("folder")), "")
    m = re.search(r"/folders/([A-Za-z0-9_-]{10,})", client_folder or "")
    res = send_intake(folder, rows, upload, folder_id=m.group(1) if m else None)
    if not res.get("ok"):
        key = f"intake-fail:{lead.id}"
        if not db.get(ReminderSent, key):
            notify_managers("⚠️ Заявка в производство не создалась", [f"{client} — {service}", f"Причина: {res.get('error')}"], lead.id)
            db.add(ReminderSent(key=key))
            db.commit()
        report["error"] = res.get("error")
        return report

    filled = []
    for c, _, pp in people:  # пустые поля контакта — из паспорта этого человека
        if not c or not pp:
            continue
        values = {}
        for key, val in (("full_name", pp.get("full_name")), ("citizenship", pp.get("nationality")),
                         ("passport_until", _d(pp.get("passport_expiry")))):
            if val and not field_value(c.fields, CONTACT_FIELDS[key]):
                values[CONTACT_FIELDS[key]] = val
        if values:
            filled += kommo.update_fields("contacts", c.id, values)
    report["kommo_filled"] = filled
    url = res.get("folder_url") or ""
    try:
        kommo.add_note(lead.id, "📋 Заявка в производство создана автоматически (лист «Заявки авто»).\n"
                                f"Папка: {url}\nНе хватает / проверить: {'; '.join(missing) or 'всё на месте'}")
    except Exception:
        log.warning("Не удалось добавить примечание в сделку %s", lead.id)
    c0 = people[0][0]
    ex0 = _contact_extra(c0)
    notify_managers("====New Client====", [
        f"ФИО: {', '.join(p[1] for p in people)}",
        f"КОНТАКТ: {', '.join(x for x in ((c0.phones[0] if c0 and c0.phones else ''), ex0.get('email'), ex0.get('instagram')) if x) or '—'}",
        f"УСЛУГА: {service}",
        f"ЦЕНА: {lead.price:,} · ОПЛАТА: {paid if paid is not None else '—'} · ДОЛГ: {debt if debt is not None else '—'}".replace(",", " "),
        f"ДОКУМЕНТЫ: {url or ex0.get('folder') or '—'}",
        f"АДРЕС: {ex0['address']}" if ex0.get("address") else "",
        f"ПАРТНЕР: {partner_word or '—'}",
        f"ЗАКРЕПИЛИ: {agreed}" if agreed else "ЗАКРЕПИЛИ: — (менеджер, допишите примечанием «Закрепляем: …»)",
        ("❗ " + "; ".join(missing)) if missing else "✅ Документы на месте",
    ], lead.id)
    db.add(IntakeRecord(lead_id=lead.id, passport_name=client, folder_url=url,
                        missing="; ".join(missing), checked_files=[]))
    db.commit()
    report["folder_url"] = url
    return report


def _fmt(value) -> str:
    d = _d(value)
    return d.strftime("%d.%m.%Y") if d else ""


def process_ready(db: Session, kommo: KommoClient, lead: KommoLead, apply: bool = True) -> dict:
    """Менеджер приложил готовую визу/ITK и поставил «Услуга готова» → клиенту в приложение + даты в Kommo."""
    rec = db.get(IntakeRecord, lead.id)
    if not rec:
        rec = IntakeRecord(lead_id=lead.id, checked_files=[])
        if apply:
            db.add(rec)
    checked = set(rec.checked_files or [])
    contact = kommo.get_contact(lead.contact_ids[0]) if lead.contact_ids else None
    known = [rec.passport_name]
    if contact:
        known += [str(field_value(contact.fields, CONTACT_FIELDS["full_name"]) or ""), contact.name]
    marked = [v for v in (field_value(lead.fields, f"raw:{CLIENT_FILES_FIELD}") or []) if isinstance(v, dict)]
    marked_ids = {str(v.get("file_uuid")) for v in marked}
    report = {"lead_id": lead.id, "shown": [], "wrong_name": [], "dates": {}, "skipped": []}
    for f, _, info in _read_files(kommo, lead.id, skip=checked):
        checked.add(f.uuid)
        kind = info.get("doc_type")
        if kind not in ("visa", "itk"):
            continue
        if not name_matches(info.get("full_name"), known):
            report["wrong_name"].append(f"{info['file']} (в документе: {info.get('full_name') or 'имя не прочитано'})")
            continue
        if f.uuid not in marked_ids:
            marked.append({"file_uuid": f.uuid, "file_name": info["file"]})
            marked_ids.add(f.uuid)
            report["shown"].append(info["file"])
        exp = _d(info.get("visa_expiry"))
        if exp:
            report["dates"][CONTACT_FIELDS["itk_until" if kind == "itk" else "visa_until"]] = exp
        if info.get("visa_type") and contact and not field_value(contact.fields, CONTACT_FIELDS["current_visa"]):
            report["dates"][CONTACT_FIELDS["current_visa"]] = info["visa_type"]
    if not apply:
        return report
    rec.checked_files = sorted(checked)
    # Клиенту документы показываются из папки на Google Диске (services/drive_docs.py) — здесь только даты
    if contact and report["dates"]:
        kommo.update_fields("contacts", contact.id, report["dates"])
    if report["wrong_name"]:
        notify_managers("⚠️ В сделке документ на другое имя", report["wrong_name"] + ["Клиенту не показан — проверьте."], lead.id)
    db.commit()
    return report


def tick(db: Session, kommo: KommoClient, since: datetime) -> int:
    """Вызывается воркером каждые 10 минут. Только сделки, попавшие на этап после включения автозаявок."""
    started = _started_at(db)
    n = 0
    for lead in kommo.get_leads_updated_since(since):
        if lead.pipeline_id not in CLIENT_PIPELINE_IDS:
            continue
        st = norm(lead.status_name)
        try:
            if st in PAID_STATUSES and not db.get(IntakeRecord, lead.id):
                at = _entered_at(kommo, lead.id, PAID_STATUSES)
                if at and at >= started and process_paid(db, kommo, lead):
                    n += 1
            elif st in READY_STATUSES:
                at = _entered_at(kommo, lead.id, READY_STATUSES)
                if at and at >= started:
                    process_ready(db, kommo, lead)
                    n += 1
        except Exception:
            db.rollback()
            log.exception("Автозаявка: сделка %s", lead.id)
    return n
