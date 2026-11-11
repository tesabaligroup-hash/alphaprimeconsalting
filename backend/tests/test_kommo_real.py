"""Проверка разбора ответов Kommo API v4 (без сети — подставные ответы в формате Kommo)."""
import httpx

from app.kommo.real import RealKommo

PIPELINES = {"_embedded": {"pipelines": [{"id": 1, "name": "Consulting", "_embedded": {"statuses": [
    {"id": 10, "name": "ЖДЕМ $"}, {"id": 11, "name": "ОПЛАТА ПОЛУЧЕНА"}, {"id": 12, "name": "УСЛУГА ГОТОВА"}]}}]}}
CONTACTS = {"_embedded": {"contacts": [{"id": 501, "name": "аня молочко", "custom_fields_values": [
    {"field_id": 1, "field_name": "Телефон", "field_code": "PHONE", "values": [{"value": "+62 812-0000-0001"}]},
    {"field_id": 2, "field_name": "Имя Фамилия", "values": [{"value": "ANNA DIKINA"}]}],
    "_embedded": {"leads": [{"id": 1001}]}}]}}
LEADS = {"_embedded": {"leads": [{"id": 1001, "name": "Сделка #1001", "price": 10900000, "pipeline_id": 1, "status_id": 10,
    "created_at": 1793000000, "updated_at": 1793100000, "custom_fields_values": [
        {"field_id": 5, "field_name": "Тип услуги", "values": [{"value": "E33G", "enum_id": 7}]},
        {"field_id": 6, "field_name": "Партнёр", "values": [{"value": "ANNABALI"}]}],
    "_embedded": {"contacts": [{"id": 501, "is_main": True}]}}]}}
EVENTS = {"_embedded": {"events": [{"type": "lead_status_changed", "created_at": 1793200000,
    "value_after": [{"lead_status": {"id": 11, "pipeline_id": 1}}]}]}}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    assert request.headers["Authorization"] == "Bearer TOKEN"
    if path.endswith("/leads/pipelines"):
        return httpx.Response(200, json=PIPELINES)
    if path.endswith("/contacts"):
        return httpx.Response(200, json=CONTACTS)
    if path.endswith("/leads"):
        return httpx.Response(200, json=LEADS)
    if path.endswith("/events"):
        return httpx.Response(200, json=EVENTS)
    if path.endswith("/leads/complex"):
        return httpx.Response(200, json=[{"id": 777, "contact_id": 888}])
    if path.endswith("/leads/notes"):
        return httpx.Response(200, json={"_embedded": {"notes": [{"id": 1}]}})
    return httpx.Response(204)


def make() -> RealKommo:
    k = RealKommo("https://example.kommo.com", "TOKEN")
    k._http = httpx.Client(base_url="https://example.kommo.com/api/v4", transport=httpx.MockTransport(handler),
                           headers={"Authorization": "Bearer TOKEN"})
    return k


def test_find_contact_by_phone_any_format():
    k = make()
    assert k.find_contact_ids_by_phone("+6281200000001") == [501]
    assert k.find_contact_ids_by_phone("081200000001") == [501]
    assert k.find_contact_ids_by_phone("+628129999999") == []


def test_contact_and_lead_parsing():
    k = make()
    c = k.get_contact(501)
    assert c.lead_ids == [1001] and c.fields["Имя Фамилия"] == "ANNA DIKINA"
    lead = k.get_leads([1001])[0]
    assert lead.status_name == "ЖДЕМ $" and lead.fields["Тип услуги"] == "E33G" and lead.contact_ids == [501]
    hist = k.get_status_history(1001)
    assert hist[0].status_name == "ОПЛАТА ПОЛУЧЕНА"


def test_create_lead():
    assert make().create_lead(title="Тест", contact_name="Иван", phone="+62812", note="Заметка") == 777
