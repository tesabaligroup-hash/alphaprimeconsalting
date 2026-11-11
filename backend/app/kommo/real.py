"""Клиент Kommo API v4 (долгосрочный токен приватной интеграции).

Документация: https://developers.kommo.com/reference
"""
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from .base import KommoContact, KommoFile, KommoLead, StatusChange

log = logging.getLogger(__name__)


def _ts(value) -> datetime | None:
    if value in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _fields(raw: list | None) -> dict[str, object]:
    """custom_fields_values → {название поля: значение}. Несколько значений склеиваются через запятую."""
    out: dict[str, object] = {}
    for cf in raw or []:
        values = [v.get("value") for v in cf.get("values") or [] if v.get("value") not in (None, "")]
        if not values:
            continue
        name = cf.get("field_name") or str(cf.get("field_id"))
        out[name] = values[0] if len(values) == 1 else ", ".join(str(v) for v in values)
        if cf.get("field_code"):
            out[f"code:{cf['field_code']}"] = values
    return out


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


class RealKommo:
    def __init__(self, base_url: str, token: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url + "/api/v4",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        self._statuses: dict[int, str] = {}
        self._statuses_loaded_at = 0.0
        self._drive_url: str | None = None

    # ---------- низкий уровень ----------
    def _get(self, path: str, params=None) -> dict:
        for attempt in range(3):
            r = self._http.get(path, params=params)
            if r.status_code == 429:  # лимит Kommo — 7 запросов в секунду
                time.sleep(1 + attempt)
                continue
            if r.status_code == 204:
                return {}
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    def _post(self, path: str, payload) -> dict | list:
        r = self._http.post(path, json=payload)
        r.raise_for_status()
        return r.json() if r.content else {}

    # ---------- справочники ----------
    def pipelines(self) -> list[dict]:
        data = self._get("/leads/pipelines")
        return (data.get("_embedded") or {}).get("pipelines", [])

    def status_name(self, status_id: int) -> str:
        if not self._statuses or time.time() - self._statuses_loaded_at > 3600:
            names = {}
            for p in self.pipelines():
                for s in (p.get("_embedded") or {}).get("statuses", []):
                    names[int(s["id"])] = s.get("name", "")
            self._statuses = names
            self._statuses_loaded_at = time.time()
        return self._statuses.get(int(status_id), "")

    def custom_fields(self, entity: str = "leads") -> list[dict]:
        out, page = [], 1
        while True:
            data = self._get(f"/{entity}/custom_fields", params={"limit": 250, "page": page})
            items = (data.get("_embedded") or {}).get("custom_fields", [])
            out += items
            if len(items) < 250:
                return out
            page += 1

    # ---------- преобразование ----------
    def _lead(self, raw: dict) -> KommoLead:
        emb = raw.get("_embedded") or {}
        return KommoLead(
            id=int(raw["id"]),
            name=raw.get("name") or "",
            price=int(raw.get("price") or 0),
            pipeline_id=int(raw.get("pipeline_id") or 0),
            status_id=int(raw.get("status_id") or 0),
            status_name=self.status_name(int(raw.get("status_id") or 0)),
            fields=_fields(raw.get("custom_fields_values")),
            contact_ids=[int(c["id"]) for c in emb.get("contacts", [])],
            created_at=_ts(raw.get("created_at")),
            updated_at=_ts(raw.get("updated_at")),
            closed_at=_ts(raw.get("closed_at")),
        )

    def _contact(self, raw: dict) -> KommoContact:
        fields = _fields(raw.get("custom_fields_values"))
        phones = [str(p) for p in fields.get("code:PHONE", [])]  # type: ignore[union-attr]
        emb = raw.get("_embedded") or {}
        return KommoContact(
            id=int(raw["id"]),
            name=raw.get("name") or "",
            phones=phones,
            fields=fields,
            lead_ids=[int(x["id"]) for x in emb.get("leads", [])],
        )

    # ---------- методы для приложения ----------
    def find_contact_ids_by_phone(self, phone: str) -> list[int]:
        d = digits(phone)
        if len(d) < 7:
            return []
        # Ищем по последним 9–10 цифрам: номер в CRM может быть записан с +62, 0 или пробелами
        tail = d[-10:]
        data = self._get("/contacts", params={"query": tail, "limit": 50})
        result = []
        for c in (data.get("_embedded") or {}).get("contacts", []):
            contact = self._contact(c)
            if any(digits(p).endswith(d[-9:]) for p in contact.phones):
                result.append(contact.id)
        return result

    def get_contacts(self, contact_ids: list[int]) -> list[KommoContact]:
        if not contact_ids:
            return []
        params = [("with", "leads")] + [("filter[id][]", str(i)) for i in contact_ids]
        data = self._get("/contacts", params=params)
        return [self._contact(c) for c in (data.get("_embedded") or {}).get("contacts", [])]

    def get_contact(self, contact_id: int) -> KommoContact | None:
        items = self.get_contacts([contact_id])
        return items[0] if items else None

    def get_leads(self, lead_ids: list[int]) -> list[KommoLead]:
        out: list[KommoLead] = []
        for i in range(0, len(lead_ids), 50):
            chunk = lead_ids[i:i + 50]
            params = [("with", "contacts"), ("limit", "250")] + [("filter[id][]", str(x)) for x in chunk]
            data = self._get("/leads", params=params)
            out += [self._lead(x) for x in (data.get("_embedded") or {}).get("leads", [])]
        return out

    def get_status_history(self, lead_id: int) -> list[StatusChange]:
        params = [("filter[entity][]", "lead"), ("filter[entity_id][]", str(lead_id)),
                  ("filter[type][]", "lead_status_changed"), ("limit", "100")]
        data = self._get("/events", params=params)
        out = []
        for e in (data.get("_embedded") or {}).get("events", []):
            after = (e.get("value_after") or [{}])[0].get("lead_status") or {}
            sid = int(after.get("id") or 0)
            at = _ts(e.get("created_at"))
            if sid and at:
                out.append(StatusChange(status_id=sid, status_name=self.status_name(sid), at=at))
        return sorted(out, key=lambda x: x.at)

    def _drive(self) -> str | None:
        if self._drive_url is None:
            data = self._get("/account", params={"with": "drive_url"})
            self._drive_url = (data.get("drive_url") or "").rstrip("/") or None
        return self._drive_url

    def get_lead_files(self, lead_id: int) -> list[KommoFile]:
        data = self._get(f"/leads/{lead_id}/files")
        uuids = [f.get("file_uuid") for f in (data.get("_embedded") or {}).get("files", []) if f.get("file_uuid")]
        drive = self._drive()
        files = []
        for uuid in uuids:
            name, created = uuid, None
            if drive:
                try:
                    r = self._http.get(f"{drive}/v1.0/files/{uuid}")
                    if r.status_code == 200:
                        info = r.json()
                        name = info.get("name") or uuid
                        created = _ts(info.get("created_at"))
                except httpx.HTTPError as exc:  # файл покажем хотя бы без названия
                    log.warning("Kommo drive: %s", exc)
            files.append(KommoFile(uuid=uuid, name=name, created_at=created))
        return files

    def get_file_download_url(self, uuid: str) -> str | None:
        drive = self._drive()
        if not drive:
            return None
        r = self._http.get(f"{drive}/v1.0/files/{uuid}")
        if r.status_code != 200:
            return None
        links = r.json().get("_links") or {}
        return (links.get("download") or {}).get("href")

    def download_file(self, url: str) -> httpx.Response:
        return self._http.get(url, follow_redirects=True)

    def get_leads_updated_since(self, since: datetime) -> list[KommoLead]:
        ts = int(since.replace(tzinfo=timezone.utc).timestamp())
        out, page = [], 1
        while page <= 40:
            params = {"filter[updated_at][from]": ts, "with": "contacts", "limit": 250, "page": page}
            data = self._get("/leads", params=params)
            items = (data.get("_embedded") or {}).get("leads", [])
            out += [self._lead(x) for x in items]
            if len(items) < 250:
                break
            page += 1
        return out

    def create_lead(self, *, title: str, contact_name: str, phone: str | None = None,
                    telegram: str | None = None, note: str | None = None, tags: list[str] | None = None) -> int | None:
        contact: dict = {"first_name": contact_name}
        if phone:
            contact["custom_fields_values"] = [{"field_code": "PHONE", "values": [{"value": phone, "enum_code": "MOB"}]}]
        lead = {"name": title, "_embedded": {"contacts": [contact], "tags": [{"name": t} for t in (tags or [])]}}
        res = self._post("/leads/complex", [lead])
        lead_id = int(res[0]["id"]) if isinstance(res, list) and res else None
        text = "\n".join(x for x in [note, f"Telegram: {telegram}" if telegram else None] if x)
        if lead_id and text:
            self._post("/leads/notes", [{"entity_id": lead_id, "note_type": "common", "params": {"text": text}}])
        return lead_id
