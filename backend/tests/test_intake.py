"""Автозаявка в производство и проверка готовой визы (ИИ и таблица — подменены)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.kommo.base import KommoFile
from app.kommo.mock import MockKommo
from app.models import Base, IntakeRecord
from app.services import intake


@pytest.fixture
def env(monkeypatch):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = Session(eng)
    k = MockKommo()
    k.file_bytes = {"p": (b"pdf", "passport.pdf"), "ph": (b"jpg", "photo.jpg"), "v": (b"pdf", "ITK.pdf"), "x": (b"pdf", "ITK other.pdf")}
    sent, notes = [], []
    monkeypatch.setattr(intake, "send_intake", lambda folder, row, files: sent.append((folder, row, files)) or {"ok": True, "folder_url": "https://drive/f"})
    monkeypatch.setattr(intake, "notify_managers", lambda title, lines, lead_id=None: notes.append((title, lines)))
    monkeypatch.setattr(intake, "notify_user", lambda tg, text: True)
    return db, k, sent, notes


def _docs(monkeypatch, mapping):
    monkeypatch.setattr(intake, "read_document", lambda data, name: dict(mapping[name]))


def test_paid_creates_intake_and_fills_contact(env, monkeypatch):
    db, k, sent, notes = env
    exp = (date.today() + timedelta(days=400)).isoformat()
    _docs(monkeypatch, {"passport.pdf": {"doc_type": "passport", "full_name": "ANNA DIKINA", "passport_expiry": exp, "nationality": "RUS"},
                        "photo.jpg": {"doc_type": "photo"}})
    monkeypatch.setattr(k, "get_lead_files", lambda lead_id: [KommoFile("p", "passport.pdf", None), KommoFile("ph", "photo.jpg", None)])
    lead = k.get_leads([1001])[0]
    dry = intake.process_paid(db, k, lead, apply=False)
    assert not sent and "для KITAS проверить срок" in "; ".join(dry["missing"])
    rep = intake.process_paid(db, k, lead)
    assert sent and sent[0][1][2] == "ANNA DIKINA" and len(sent[0][2]) == 2
    assert db.get(IntakeRecord, 1001).folder_url == "https://drive/f"
    assert notes[-1][0] == "📋 Заявка в производство"
    assert intake.process_paid(db, k, lead) is None  # второй раз — не дублируем


def test_paid_reports_missing_passport_and_photo(env, monkeypatch):
    db, k, sent, notes = env
    monkeypatch.setattr(k, "get_lead_files", lambda lead_id: [])
    rep = intake.process_paid(db, k, k.get_leads([1001])[0], apply=False)
    assert "нет паспорта" in rep["missing"] and "нет фото" in rep["missing"]


def test_ready_marks_matching_itk_and_rejects_other_name(env, monkeypatch):
    db, k, sent, notes = env
    _docs(monkeypatch, {"ITK.pdf": {"doc_type": "itk", "full_name": "DIKINA ANNA", "visa_expiry": "2027-11-20", "visa_type": "E33G"},
                        "ITK other.pdf": {"doc_type": "itk", "full_name": "IVAN PETROV", "visa_expiry": "2027-01-01"}})
    monkeypatch.setattr(k, "get_lead_files", lambda lead_id: [KommoFile("v", "ITK.pdf", None), KommoFile("x", "ITK other.pdf", None)])
    rep = intake.process_ready(db, k, k.get_leads([1001])[0])
    assert rep["shown"] == ["ITK.pdf"] and rep["wrong_name"] and rep["dates"]["ITK до"] == date(2027, 11, 20)
    assert any(e == "leads" and "Документы клиенту" in v for e, _, v in k.updated)
    assert notes and "другое имя" in notes[0][0]
    again = intake.process_ready(db, k, k.get_leads([1001])[0])
    assert not again["shown"] and not again["wrong_name"]  # уже проверенные файлы не читаем повторно


def test_name_matches():
    assert intake.name_matches("DIKINA ANNA", ["ANNA DIKINA"])
    assert intake.name_matches("ANNA DIKINA", [None, "Анна Дикина"])
    assert not intake.name_matches("IVAN PETROV", ["ANNA DIKINA"])
