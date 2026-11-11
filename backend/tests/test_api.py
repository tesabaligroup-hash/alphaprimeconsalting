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
    assert "Китас удаленщика E33G" in titles
    assert any(x["person"] == "Миша" for x in d["dates"])
    assert d["banners"] and d["news"] and d["partner_news"]
    e33g = next(s for s in d["services"] if s["code"] == "E33G")
    assert e33g["badge"] == "Ждём доплату" and e33g["remaining"] == 3_900_000


def test_service_detail_steps_order(client):
    d = client.get("/api/services/1001", headers=DEV).json()["service"]
    assert [s["title"] for s in d["steps"]] == ["Документы собраны", "Оплата", "Подача в иммиграцию", "Готово — документы в приложении"]
    assert [s["state"] for s in d["steps"]] == ["done", "current", "todo", "todo"]
    assert d["steps"][0]["at"].startswith("2026-11-04")


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
    assert names["Denis R."]["status"] == "to_payout" and names["Denis R."]["amount"] == 1_275_000
    assert names["Maria K."]["status"] == "in_work" and names["Maria K."]["amount"] == 585_000
    assert names["@olga_bali"]["status"] == "awaiting_payment"
    assert d["balance"]["to_payout"] == 1_275_000
    assert d["links"]["tg"].endswith("start=ANNABALI")
    assert any(r["status"] == "pending" for r in d["referrals"])
    # партнёр не видит услуги и цены
    assert "service_code" not in d["friends"][0] and "price" not in d["friends"][0]


def test_codeword_check(client):
    r = client.post("/api/partner/codeword/check", json={"word": "виза"}, headers=DEV).json()
    assert not r["ok"]
    assert client.post("/api/partner/codeword", json={"word": "NEWWORD1"}, headers=DEV).status_code == 409  # уже закреплено


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


def test_client_sees_only_marked_files(client):
    groups = client.get("/api/documents", headers=DEV).json()["groups"]
    names = sorted(f["name"] for g in groups for f in g["files"])
    assert names == ["Family KITAS — Миша.pdf", "ITK — Миша.pdf", "Виза C1 e-Visa.pdf"]
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
