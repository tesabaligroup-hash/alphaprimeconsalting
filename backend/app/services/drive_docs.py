"""Визы и ITK клиентов с Google Диска → приложение (17.11.2026).

У контакта в Kommo поле «Документы» — ссылка на папку клиента на Диске. Раз в сутки программа смотрит папки
(через Apps Script таблицы производства), новые PDF/фото читает ИИ (сначала дешёвая модель), и если это виза
или ITK на имя ЭТОГО контакта — сохраняет копию у нас и показывает клиенту: «Активные» (срок не прошёл) / «Архив».
Чужие документы, паспорта, черновики — не показываются. Даты «ITK до»/«Виза до» обновляются в Kommo.
"""
import base64
import logging
import re
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai_docs import read_document
from ..config import get_settings
from ..kommo.base import KommoClient, KommoContact
from ..kommo.mapping import CONTACT_FIELDS
from ..models import ClientDocument, DriveFileRead
from .cabinet import as_date, field_value
from .intake import name_matches

log = logging.getLogger(__name__)

DOC_FIELD = "Документы"
EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def links_of(contact: KommoContact) -> tuple[list[str], list[str]]:
    raw = " ".join(str(v) for v in (field_value(contact.fields, f"raw:{DOC_FIELD}") or [field_value(contact.fields, DOC_FIELD) or ""]))
    folders = re.findall(r"/folders/([A-Za-z0-9_-]{10,})", raw)
    files = re.findall(r"/file/d/([A-Za-z0-9_-]{10,})", raw) + re.findall(r"[?&]id=([A-Za-z0-9_-]{10,})", raw)
    return list(dict.fromkeys(folders)), list(dict.fromkeys(files))


def _script(params: dict) -> dict:
    s = get_settings()
    r = httpx.get(s.intake_script_url, params={"secret": s.intake_script_secret, **params}, timeout=120, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def list_folder(folder_id: str) -> list[dict]:
    d = _script({"action": "list", "folder": folder_id})
    if not d.get("ok"):
        raise RuntimeError(d.get("error") or "папка не открылась")
    return d.get("files") or []


def get_file(file_id: str) -> tuple[bytes, str, str, str]:
    d = _script({"action": "file", "id": file_id})
    if not d.get("ok"):
        raise RuntimeError(d.get("error") or "файл не открылся")
    return base64.b64decode(d["data"]), d.get("name") or file_id, d.get("mime") or "", d.get("modified") or ""


def _named(name: str, mime: str) -> str:
    ext = EXT.get(mime, "")
    return name if not ext or name.lower().endswith(ext) or (ext == ".jpg" and name.lower().endswith(".jpeg")) else name + ext


def _d(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def read_cached(db: Session, f: dict) -> tuple[dict, bytes | None]:
    """Результат ИИ по файлу (из кэша, если файл не менялся) + байты, если пришлось скачать."""
    rec = db.get(DriveFileRead, f["id"])
    if rec and rec.modified == f.get("modified", ""):
        return rec.result or {}, None
    data, name, mime, modified = get_file(f["id"])
    res = read_document(data, _named(name, mime))
    if rec is None:
        rec = DriveFileRead(file_id=f["id"])
        db.add(rec)
    rec.modified, rec.name, rec.result = f.get("modified") or modified, name[:255], res
    db.commit()
    return res, data


def _store(doc_id: int, name: str, data: bytes) -> str:
    folder = Path(get_settings().docs_dir)
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\- ]+", "_", name)[:120]
    path = folder / f"{doc_id}_{safe}"
    path.write_bytes(data)
    return str(path)


def sync_contact(db: Session, kommo: KommoClient, contact: KommoContact, apply: bool = True) -> dict:
    rep = {"contact": contact.name, "files": 0, "new_docs": [], "skipped": [], "errors": [], "dates": {}}
    folders, direct = links_of(contact)
    items: list[dict] = []
    for fid in folders:
        try:
            items += list_folder(fid)
        except Exception as exc:
            rep["errors"].append(str(exc)[:200])
    items += [{"id": x, "name": x, "mime": "", "modified": ""} for x in direct]
    names = [str(field_value(contact.fields, CONTACT_FIELDS["full_name"]) or ""), contact.name]
    have = {d.file_id: d for d in db.scalars(select(ClientDocument).where(ClientDocument.contact_id == contact.id))}
    for f in items:
        if f.get("mime") and f["mime"] not in EXT:
            continue  # Google-документы, архивы и т.п.
        rep["files"] += 1
        if f["id"] in have:
            continue
        try:
            res, data = read_cached(db, f)
        except Exception as exc:
            rep["errors"].append(f"{f.get('name')}: {str(exc)[:150]}")
            continue
        kind = res.get("doc_type")
        if kind not in ("visa", "itk"):
            continue
        if not name_matches(res.get("full_name"), names):
            rep["skipped"].append(f"{f.get('name')}: на имя {res.get('full_name') or '—'}")
            continue
        exp = _d(res.get("visa_expiry"))
        dup = next((d for d in have.values() if d.doc_type == kind and d.expires_on == exp and exp), None)
        if dup:
            continue  # тот же документ уже есть (например, PDF и фото)
        rep["new_docs"].append(f"{kind.upper()} {res.get('visa_type') or ''} до {exp:%d.%m.%Y}" if exp else f"{kind.upper()} {f.get('name')}")
        if not apply:
            continue
        if data is None:
            data, _, _, _ = get_file(f["id"])
        doc = ClientDocument(contact_id=contact.id, file_id=f["id"], name=_named(f.get("name") or kind, f.get("mime") or ""),
                             doc_type=kind, visa_type=(res.get("visa_type") or "")[:64] or None,
                             person_name=(res.get("full_name") or "")[:200] or None, expires_on=exp,
                             stored_path="", mime=f.get("mime") or "application/pdf")
        db.add(doc)
        db.flush()
        doc.stored_path = _store(doc.id, doc.name, data)
        have[f["id"]] = doc
        db.commit()
    # самые поздние даты → Kommo (только если позже того, что уже стоит)
    for kind, key in (("itk", "itk_until"), ("visa", "visa_until")):
        latest = max((d.expires_on for d in have.values() if d.doc_type == kind and d.expires_on), default=None)
        current = as_date(field_value(contact.fields, CONTACT_FIELDS[key]))
        if latest and (not current or latest > current):
            rep["dates"][CONTACT_FIELDS[key]] = latest
    if apply and rep["dates"]:
        try:
            kommo.update_fields("contacts", contact.id, rep["dates"])
        except Exception:
            log.exception("Даты из документов не записались в контакт %s", contact.id)
    return rep


def sync_all(db: Session, kommo: KommoClient, apply: bool = True, contact_id: int | None = None,
             limit: int | None = None) -> dict:
    contacts = [kommo.get_contact(contact_id)] if contact_id else kommo.all_contacts()
    contacts = [c for c in contacts if c and any(links_of(c))]
    if limit:
        contacts = contacts[:limit]
    total = {"contacts": len(contacts), "files": 0, "new_docs": 0, "skipped": 0, "errors": 0, "dates": 0, "details": []}
    for c in contacts:
        r = sync_contact(db, kommo, c, apply=apply)
        total["files"] += r["files"]
        total["new_docs"] += len(r["new_docs"])
        total["skipped"] += len(r["skipped"])
        total["errors"] += len(r["errors"])
        total["dates"] += len(r["dates"])
        if r["new_docs"] or r["skipped"] or r["errors"]:
            total["details"].append(r)
    return total


def docs_for(db: Session, contact_ids: list[int]) -> list[ClientDocument]:
    if not contact_ids:
        return []
    return list(db.scalars(select(ClientDocument).where(ClientDocument.contact_id.in_(contact_ids))
                           .order_by(ClientDocument.expires_on.desc().nullslast())))
