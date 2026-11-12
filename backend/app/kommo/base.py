"""Общие структуры данных Kommo, которые использует приложение."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class KommoContact:
    id: int
    name: str
    phones: list[str] = field(default_factory=list)
    fields: dict[str, object] = field(default_factory=dict)  # название поля → значение
    lead_ids: list[int] = field(default_factory=list)


@dataclass
class KommoLead:
    id: int
    name: str
    price: int
    pipeline_id: int
    status_id: int
    status_name: str
    fields: dict[str, object] = field(default_factory=dict)  # название поля → значение
    contact_ids: list[int] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None


@dataclass
class StatusChange:
    status_id: int
    status_name: str
    at: datetime


@dataclass
class KommoFile:
    uuid: str
    name: str
    created_at: datetime | None
    download_url: str | None = None


class KommoClient(Protocol):
    def find_contact_ids_by_phone(self, phone: str) -> list[int]: ...
    def find_contact_ids_by_telegram(self, username: str) -> list[int]: ...
    def get_contact(self, contact_id: int) -> KommoContact | None: ...
    def get_contacts(self, contact_ids: list[int]) -> list[KommoContact]: ...
    def get_leads(self, lead_ids: list[int]) -> list[KommoLead]: ...
    def get_status_history(self, lead_id: int) -> list[StatusChange]: ...
    def get_lead_files(self, lead_id: int) -> list[KommoFile]: ...
    def get_file_download_url(self, uuid: str) -> str | None: ...
    def get_leads_updated_since(self, since: datetime) -> list[KommoLead]: ...
    def create_lead(self, *, title: str, contact_name: str, phone: str | None = None,
                    telegram: str | None = None, note: str | None = None, tags: list[str] | None = None,
                    contact_id: int | None = None, price: int | None = None) -> int | None: ...
    def set_lead_partner(self, lead_id: int, value: str) -> bool: ...
