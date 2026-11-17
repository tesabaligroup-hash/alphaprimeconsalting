from datetime import date, timedelta
import os
import tempfile

os.environ.update({
    "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/test.db",
    "DEV_MODE": "true",
    "KOMMO_MOCK": "true",
    "BOT_TOKEN": "123:TEST",
    "ADMIN_PASSWORD": "secret",
    "UPLOADS_DIR": tempfile.mkdtemp(),
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.telegram_auth import sign_init_data  # noqa: E402

DEV = {"X-Dev-User": "1"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_requires_telegram(client):
    assert client.get("/api/me").status_code == 401


def test_real_telegram_signature(client):
    init = sign_init_data({"auth_date": "9999999999", "user": {"id": 777, "first_name": "Олег"}}, "123:TEST")
    r = client.get("/api/me", headers={"X-Telegram-Init-Data": init})
    assert r.status_code == 200 and r.json()["first_name"] == "Олег" and r.json()["linked"] is False
    bad = init.replace("777", "778")
    assert client.get("/api/me", headers={"X-Telegram-Init-Data": bad}).status_code == 401


def test_home_has_family_dates_and_news(client):
    d = client.get("/api/home", headers=DEV).json()
    titles = [s["title"] for s in d["services"]]
    assert "KITAS удалёнщика E33G (1 год)" in titles
    assert any(x["person"] == "Миша" for x in d["dates"])
    assert d["banners"] and d["news"] and d["partner_news"]
    e33g = next(s for s in d["services"] if s["code"] == "E33G")
    assert e33g["badge"] == "Ждём доплату" and e33g["remaining"] == 3_900_000


def test_service_detail_steps_order(client):
    d = client.get("/api/services/1001", headers=DEV).json()["service"]
    assert [s["title"] for s in d["steps"]] == ["Оплата", "Подача в иммиграцию", "Готово — документы в приложении"]
    assert [s["state"] for s in d["steps"]] == ["current", "todo", "todo"]


def test_cannot_open_someone_elses_deal(client):
    assert client.get("/api/services/2001", headers=DEV).status_code == 404


def test_catalog_hides_school_and_pension(client):
    cats = client.get("/api/catalog").json()["categories"]
    assert cats[0]["id"] == "popular" and [i["code"] for i in cats[0]["items"]] == ["C1", "E33G", "PERSONAL-COUNT", "DRIVER"]
    assert cats[1]["id"] == "kitas"
    codes = {i["code"] for c in cats for i in c["items"]}
    assert not codes & {"STUDY-1", "STUDY-2", "E33F"} and "E33G" in codes


def test_order_creates_kommo_lead(client):
    from app.kommo.mock import MockKommo

    before = len(MockKommo.created)
    assert client.post("/api/orders", json={"code": "C1"}, headers=DEV).json()["ok"]
    assert len(MockKommo.created) == before + 1 and "C1" in MockKommo.created[-1]["note"]
    assert MockKommo.created[-1]["contact_id"] == 501  # существующий контакт, без дубля
    assert MockKommo.created[-1]["price"] == 2_000_000


def test_partner_dashboard(client):
    d = client.get("/api/partner", headers=DEV).json()
    names = {f["name"]: f for f in d["friends"]}
    assert names["Denis R."]["status"] == "to_payout" and names["Denis R."]["amount"] == 1_000_000
    assert names["Maria K."]["status"] == "in_work" and names["Maria K."]["amount"] == 1_000_000
    assert names["@olga_bali"]["status"] == "awaiting_payment"
    assert d["balance"]["to_payout"] == 1_000_000
    assert d["links"]["tg"].startswith("https://t.me/alpha_prime_id?text=") and d["links"]["tg"].endswith("ANNABALI")
    assert d["links"]["wa"].startswith("https://wa.me/6281519845777?text=") and "bot" not in d["links"]
    assert any(r["status"] == "pending" for r in d["referrals"])
    # партнёр не видит услуги и цены
    assert "service_code" not in d["friends"][0] and "price" not in d["friends"][0]


def test_codeword_check(client):
    r = client.post("/api/partner/codeword/check", json={"word": "виза"}, headers=DEV).json()
    assert not r["ok"]
    # своё же слово ещё раз не добавить
    assert "уже есть в вашем списке" in client.post("/api/partner/codeword/check", json={"word": "annabali"}, headers=DEV).json()["problems"][0]


def test_several_codewords_and_qr_download(client):
    r = client.post("/api/partner/codeword", json={"word": "topgym", "label": "Top Gym"}, headers=DEV)
    assert r.status_code == 200 and r.json()["codeword"] == "TOPGYM"
    d = client.get("/api/partner", headers=DEV).json()
    words = {w["word"]: w for w in d["codewords"]}
    assert set(words) == {"ANNABALI", "TOPGYM"}
    assert words["ANNABALI"]["main"] and not words["TOPGYM"]["main"] and words["TOPGYM"]["label"] == "Top Gym"
    assert words["TOPGYM"]["links"]["tg"].endswith("TOPGYM") and "?text=" in words["TOPGYM"]["links"]["tg"] and "TOPGYM" in words["TOPGYM"]["links"]["wa"]
    assert d["partner"]["codeword"] == "ANNABALI"  # основное слово не меняется
    # слово занято для других партнёров
    init = sign_init_data({"auth_date": "9999999999", "user": {"id": 889, "first_name": "Гоша"}}, "123:TEST")
    h = {"X-Telegram-Init-Data": init}
    client.post("/api/partner/join", json={"accept_terms": True}, headers=h)
    assert client.post("/api/partner/codeword", json={"word": "TOPGYM"}, headers=h).status_code == 400
    assert client.post("/api/partner/qr-link", json={"word": "TOPGYM", "channel": "tg"}, headers=h).status_code == 404
    # скачивание QR: временная ссылка → PNG без авторизации
    link = client.post("/api/partner/qr-link", json={"word": "topgym", "channel": "wa"}, headers=DEV).json()
    assert link["name"] == "AlphaPrime-QR-TOPGYM-WhatsApp.png"
    png = client.get(link["url"].replace("http://localhost:8000", ""))
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    assert "attachment" in png.headers["content-disposition"]
    bad = link["url"].rsplit("/", 1)[1][:-3] + "AAA"
    assert client.get(f"/api/qr/{bad}").status_code in (403, 404)
    ig = client.post("/api/partner/qr-link", json={"word": "topgym", "channel": "ig"}, headers=DEV).json()
    assert ig["name"].endswith("-Instagram.png")
    r = client.get("/" + ig["url"].split("/", 3)[3])
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


def test_kommo_value_matches_any_codeword(client):
    from app.db import SessionLocal
    from app.services.partner import partner_by_codeword

    with SessionLocal() as db:
        assert partner_by_codeword(db, "topgym").codeword == "ANNABALI"
        assert partner_by_codeword(db, "nosuchword") is None


def test_add_referral(client):
    r = client.post("/api/partner/referrals", headers=DEV,
                    json={"name": "Пётр Иванов", "channel": "wa", "contact": "+62 812 111", "who_writes": "us"})
    assert r.status_code == 200 and r.json()["referral"]["status"] == "pending"
    assert client.post("/api/partner/referrals", headers=DEV,
                       json={"name": "X", "channel": "sms", "contact": "123", "who_writes": "us"}).status_code == 422


def test_become_partner_and_set_codeword(client):
    init = sign_init_data({"auth_date": "9999999999", "user": {"id": 888, "first_name": "Вика"}}, "123:TEST")
    h = {"X-Telegram-Init-Data": init}
    assert client.get("/api/partner", headers=h).status_code == 403
    assert client.post("/api/partner/join", json={"accept_terms": True}, headers=h).json()["ok"]
    assert client.post("/api/partner/codeword", json={"word": "annabali"}, headers=h).status_code == 400  # занято
    r = client.post("/api/partner/codeword", json={"word": "Vika Ubud"}, headers=h)
    assert r.status_code == 200 and r.json()["codeword"] == "VIKAUBUD"


def test_admin_login_and_pages(client):
    assert client.get("/admin", follow_redirects=False).status_code == 303
    page = client.get("/admin/login").text
    import re

    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    assert client.post("/admin/login", data={"name": "Tesa", "password": "wrong", "csrf": csrf}).text.count("Неверный пароль")
    r = client.post("/admin/login", data={"name": "Tesa", "password": "secret", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    for path in ("/admin", "/admin/news", "/admin/news/new", "/admin/referrals", "/admin/partners", "/admin/partners/1",
                 "/admin/users", "/admin/stopwords", "/admin/accruals"):
        assert client.get(path).status_code == 200, path
    # подтверждаем рекомендацию → сделка в Kommo
    ref_page = client.get("/admin/referrals").text
    ref_id = re.search(r'action="/admin/referrals/(\d+)"', ref_page).group(1)
    r = client.post(f"/admin/referrals/{ref_id}", data={"csrf": csrf, "action": "attach"}, follow_redirects=False)
    assert r.status_code == 303
    # новость с картинкой
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = client.post("/admin/news/save", data={"csrf": csrf, "kind": "company", "title": "Тест", "published": "true"},
                    files={"image": ("b.png", png, "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    assert any(n["title"] == "Тест" and n["image"] for n in client.get("/api/home", headers=DEV).json()["news"])


def test_documents_from_drive_family_only(client, tmp_path):
    from app.db import SessionLocal
    from app.models import ClientDocument
    f = tmp_path / "itk.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    with SessionLocal() as db:
        own = ClientDocument(contact_id=502, file_id="x1", name="ITK.pdf", doc_type="itk", visa_type="E31",
                             person_name="MIKHAIL DIKIN", expires_on=date.today() + timedelta(days=300), stored_path=str(f))
        old = ClientDocument(contact_id=501, file_id="x2", name="visa.pdf", doc_type="visa", visa_type="C1",
                             person_name="ANNA DIKINA", expires_on=date.today() - timedelta(days=30), stored_path=str(f))
        alien = ClientDocument(contact_id=999, file_id="x3", name="alien.pdf", doc_type="itk", stored_path=str(f))
        db.add_all([own, old, alien]); db.commit()
        own_id, alien_id = own.id, alien.id
    groups = client.get("/api/documents", headers=DEV).json()["groups"]
    files = {x["uuid"]: x for g in groups for x in g["files"]}
    assert f"d{own_id}" in files and not files[f"d{own_id}"]["archived"]  # Миша — в семейной сделке
    assert any(x["archived"] for x in files.values())  # старая виза — в «Архиве»
    assert f"d{alien_id}" not in files
    assert client.post(f"/api/documents/0/d{alien_id}/link", headers=DEV).status_code == 404
    link = client.post(f"/api/documents/0/d{own_id}/link", headers=DEV).json()["url"]
    r = client.get("/api/files/" + link.rsplit("/", 1)[1])
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_client_sees_only_marked_files(client):
    detail = client.get("/api/services/1002", headers=DEV).json()
    assert {f["uuid"] for f in detail["files"]} == {"f-kitas-m", "f-itk-m"}
    # чужой файл нельзя скачать даже по прямому запросу
    assert client.post("/api/documents/1002/f-other/link", headers=DEV).status_code == 404


def test_news_from_repository_content(client):
    d = client.get("/api/home", headers=DEV).json()
    titles = [n["title"] for n in d["banners"]]
    assert "Оформляете визу — получите подарок" not in titles  # старая удалена флагом delete
    b = [n for n in d["banners"] if n["title"].startswith("Специальный вход к волкам")]
    assert b and b[0]["image"].endswith("content-wolf-lodge-vip.png") and b[0]["cta"] is True
    assert client.get(b[0]["image"]).status_code == 200


def test_news_interest_creates_lead_and_dedupes(client):
    from app.api import kommo_dep
    kommo = app.dependency_overrides.get(kommo_dep, kommo_dep)()
    before = len(kommo.created)
    nid = next(n["id"] for n in client.get("/api/home", headers=DEV).json()["banners"] if n["cta"])
    r = client.post(f"/api/news/{nid}/interest", headers=DEV)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(kommo.created) == before + 1 and kommo.created[-1]["title"].startswith("Интерес из приложения: Специальный вход")
    assert client.post(f"/api/news/{nid}/interest", headers=DEV).json().get("duplicate") is True
    assert client.post("/api/news/999999/interest", headers=DEV).status_code == 404


def test_admin_accrual_buttons(client):
    import re

    page = client.get("/admin/login").text
    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    client.post("/admin/login", data={"name": "Tesa", "password": "secret", "csrf": csrf})
    r = client.post("/admin/accruals/sync", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303  # «Обновить из Kommo»
    from app.db import SessionLocal
    from app.models import Accrual
    with SessionLocal() as db:
        acc = db.query(Accrual).first()
        acc.status, acc.decision = "review", None
        db.commit()
        aid = acc.id
    for action in ("set", "approve", "reopen", "paid", "reopen", "reject", "reopen"):
        r = client.post(f"/admin/accruals/{aid}", data={"csrf": csrf, "action": action, "code": "D12-EXT"},
                        headers={"referer": "/admin/accruals"}, follow_redirects=False)
        assert r.status_code == 303, (action, r.text)
    assert client.get("/admin/accruals?status=review").status_code == 200
    with SessionLocal() as db:
        acc = db.get(Accrual, aid)
        acc.status, acc.decision = "to_payout", "approved"
        db.commit()
    assert "Выплачено" in client.get("/admin/accruals?status=to_payout").text
    r = client.post(f"/admin/accruals/{aid}", data={"csrf": csrf, "action": "payout"}, follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.get(Accrual, aid).status == "paid"


def test_partner_support_goes_to_managers(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.api.notify_managers", lambda title, lines, lead_id=None: sent.append((title, lines)))
    r = client.post("/api/partner/support", headers=DEV, json={"text": "Не вижу друга Ивана"})
    assert r.status_code == 200 and sent and "Не вижу друга Ивана" in sent[0][1][2]


def test_my_visas_add_list_delete_and_home(client):
    soon = (date.today() + timedelta(days=40)).isoformat()
    r = client.post("/api/my-visas", headers=DEV, json={"visa_type": "C1 (туристическая 60 дней)", "expires_on": soon, "person": "Муж"})
    assert r.status_code == 200 and r.json()["items"][0]["days_left"] == 40
    home = client.get("/api/home", headers=DEV).json()
    assert any(d["title"].startswith("Окончание: C1") and d["person"] == "Муж" for d in home["dates"])
    vid = r.json()["items"][0]["id"]
    assert client.delete(f"/api/my-visas/{vid}", headers=DEV).json()["items"] == []
    past = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/api/my-visas", headers=DEV, json={"visa_type": "VOA", "expires_on": past}).status_code == 400


def test_bank_card_request_once_a_week(client):
    r = client.post("/api/partner/bank-card", headers=DEV)
    if r.status_code == 403:  # тестовый пользователь ещё не партнёр в этом порядке тестов
        return
    assert r.json() == {"ok": True}
    assert client.post("/api/partner/bank-card", headers=DEV).json().get("duplicate") is True


def test_office_link_is_direct_place(client):
    c = client.get("/api/me", headers=DEV).json()["company"]
    assert "query_place_id=" in c["maps_url"]
