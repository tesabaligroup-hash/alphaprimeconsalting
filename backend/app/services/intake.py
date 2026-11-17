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
from ..kommo.mapping import CLIENT_FILES_FIELD, CLIENT_PIPELINE_IDS, CONTACT_FIELDS, LEAD_FIELDS, norm
from ..models import IntakeRecord, ProgramSetting, ReminderSent, User
from ..notify import kommo_lead_url, notify_managers, notify_user
from ..sheets import send_intake
from ..timeutil import utcnow
from .cabinet import as_date, field_value
from .partner import loose_key

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


def process_paid(db: Session, kommo: KommoClient, lead: KommoLead, apply: bool = True) -> dict | None:
    """Заявка в производство. Возвращает отчёт (что сделано или было бы сделано при apply=False)."""
    if db.get(IntakeRecord, lead.id):
        return None
    contact = kommo.get_contact(lead.contact_ids[0]) if lead.contact_ids else None
    read = _read_files(kommo, lead.id)
    docs = [info for _, _, info in read]
    passport = next((d for d in docs if d.get("doc_type") == "passport"), {})
    service = service_of(lead)
    today = date.today()
    missing = check_missing(docs, service, today)
    client = passport.get("full_name") or (contact and (field_value(contact.fields, CONTACT_FIELDS["full_name"]) or contact.name)) or lead.name
    paid = field_value(lead.fields, LEAD_FIELDS["paid_amount"])
    phone = contact.phones[0] if contact and contact.phones else ""
    docs_text = "; ".join(f"{DOC_RU.get(d.get('doc_type'), d.get('doc_type'))} — {d.get('file')}" for d in docs) or "в сделке нет файлов"
    row = [lead.id, today.strftime("%d.%m.%Y"), client, passport.get("nationality") or "", passport.get("passport_number") or "",
           _fmt(passport.get("passport_expiry")), _fmt(passport.get("birth_date")), service, kommo.user_name(lead.responsible_user_id),
           lead.price or "", paid or "", phone, "{folder}", docs_text, "; ".join(missing) or "всё на месте",
           kommo_lead_url(lead.id) or "", "Новая — проверить данные ИИ"]
    report = {"lead_id": lead.id, "client": client, "service": service, "docs": docs, "missing": missing, "row": row}
    if not apply:
        return report

    files = [{"name": info["file"], "mime": mime_for(info["file"]) or "application/octet-stream",
              "data": base64.b64encode(data).decode()} for _, data, info in read if data]
    total, upload = 0, []
    for f in files:
        size = len(f["data"]) * 3 // 4
        if total + size <= MAX_UPLOAD:
            upload.append(f)
            total += size
    folder = f"{client} — {service} — {lead.id}"[:150]
    res = send_intake(folder, row, upload)
    if not res.get("ok"):
        key = f"intake-fail:{lead.id}"
        if not db.get(ReminderSent, key):
            notify_managers("⚠️ Заявка в производство не создалась", [f"{client} — {service}", f"Причина: {res.get('error')}"], lead.id)
            db.add(ReminderSent(key=key))
            db.commit()
        report["error"] = res.get("error")
        return report

    if contact and passport:
        values = {}
        for key, val in (("full_name", passport.get("full_name")), ("citizenship", passport.get("nationality")),
                         ("passport_until", _d(passport.get("passport_expiry")))):
            if val and not field_value(contact.fields, CONTACT_FIELDS[key]):
                values[CONTACT_FIELDS[key]] = val
        if values:
            report["kommo_filled"] = kommo.update_fields("contacts", contact.id, values)
    url = res.get("folder_url") or ""
    try:
        kommo.add_note(lead.id, "📋 Заявка в производство создана автоматически.\n"
                                f"Папка: {url}\nНе хватает / проверить: {'; '.join(missing) or 'всё на месте'}")
    except Exception:
        log.warning("Не удалось добавить примечание в сделку %s", lead.id)
    notify_managers("📋 Заявка в производство", [f"{client} — {service}",
                                                   ("❗ " + "; ".join(missing)) if missing else "✅ Документы на месте",
                                                   f"Папка: {url}" if url else ""], lead.id)
    db.add(IntakeRecord(lead_id=lead.id, passport_name=passport.get("full_name"), folder_url=url,
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
    if report["shown"]:
        done = kommo.update_fields("leads", lead.id, {CLIENT_FILES_FIELD: marked})
        if not done:
            report["skipped"].append(f"в Kommo нет поля «{CLIENT_FILES_FIELD}» (тип «Файл») — документ не показан клиенту")
    if contact and report["dates"]:
        kommo.update_fields("contacts", contact.id, report["dates"])
    if report["wrong_name"]:
        notify_managers("⚠️ В сделке документ на другое имя", report["wrong_name"] + ["Клиенту не показан — проверьте."], lead.id)
    if report["skipped"]:
        notify_managers("⚠️ Готовая виза не попала в приложение", report["skipped"], lead.id)
    elif report["shown"]:
        users = db.scalars(select(User).where(User.kommo_contact_id.in_(lead.contact_ids or [0])))
        for u in users:
            notify_user(u.telegram_id, "🎉 Ваш документ готов и уже лежит в приложении Alpha Prime — раздел «Документы». "
                                       "Его можно открыть и показать офицеру.")
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
