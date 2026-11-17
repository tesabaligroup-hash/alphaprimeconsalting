"""Визы/ITK из папок Google Диска: своё имя — в приложение, чужое — нет, повторно не читаем."""
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.kommo.base import KommoContact
from app.kommo.mock import MockKommo
from app.models import Base, ClientDocument
from app.services import drive_docs as dd

FILES = [
    {"id": "f1", "name": "ITK Yoann.pdf", "mime": "application/pdf", "modified": "2026-11-01"},
    {"id": "f2", "name": "ITK Lera.pdf", "mime": "application/pdf", "modified": "2026-11-01"},
    {"id": "f3", "name": "passport.jpg", "mime": "image/jpeg", "modified": "2026-11-01"},
    {"id": "f4", "name": "ITK Yoann scan.jpg", "mime": "image/jpeg", "modified": "2026-11-01"},
    {"id": "f5", "name": "old visa.pdf", "mime": "application/pdf", "modified": "2025-01-01"},
    {"id": "f6", "name": "Анкета", "mime": "application/vnd.google-apps.document", "modified": ""},
]
READ = {
    "f1": {"doc_type": "itk", "full_name": "YOANN PAUL DEFAY", "visa_expiry": "2027-02-12", "visa_type": "D12"},
    "f2": {"doc_type": "itk", "full_name": "VALERIYA ZHUMABAYEVA", "visa_expiry": "2027-05-01"},
    "f3": {"doc_type": "passport", "full_name": "YOANN PAUL DEFAY"},
    "f4": {"doc_type": "itk", "full_name": "YOANN PAUL DEFAY", "visa_expiry": "2027-02-12"},  # тот же ITK, фото
    "f5": {"doc_type": "visa", "full_name": "DEFAY YOANN", "visa_expiry": "2025-03-01", "visa_type": "C1"},
}


@pytest.fixture
def env(monkeypatch, tmp_path):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = Session(eng)
    calls = []
    monkeypatch.setattr(dd, "list_folder", lambda fid: FILES)
    monkeypatch.setattr(dd, "get_file", lambda fid: (calls.append(fid) or b"%PDF", fid, "application/pdf", ""))
    monkeypatch.setattr(dd, "read_document", lambda data, name: dict(READ[name.split(".")[0]]))
    monkeypatch.setattr(dd.get_settings(), "docs_dir", str(tmp_path))
    contact = KommoContact(77, "YOANN PAUL DEFAY", [], {"Имя Фамилия": "YOANN PAUL DEFAY",
                           "raw:Документы": ["https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp?usp=sharing"]}, [])
    return db, MockKommo(), contact, calls


def test_links():
    c = KommoContact(1, "x", [], {"raw:Документы": ["https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp"]}, [])
    assert dd.links_of(c) == (["1AbCdEfGhIjKlMnOp"], [])


def test_sync_contact_own_docs_only(env):
    db, k, contact, calls = env
    rep = dd.sync_contact(db, k, contact)
    docs = list(db.scalars(select(ClientDocument)))
    assert sorted(d.doc_type + str(d.expires_on) for d in docs) == ["itk2027-02-12", "visa2025-03-01"]  # дубль-фото не сохранён
    assert any("VALERIYA" in x for x in rep["skipped"])  # ITK Леры в папке Yoann — не его
    assert rep["files"] == 5  # Google-анкета пропущена
    assert k.updated[-1][2]["ITK до"] == date(2027, 2, 12)
    n = len(calls)
    dd.sync_contact(db, k, contact)  # второй проход — ничего не скачиваем и не читаем заново
    assert len(calls) == n
