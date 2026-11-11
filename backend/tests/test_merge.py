"""Дубли контакта в Kommo: данные из обоих контактов показываются вместе."""
from datetime import date, datetime, timedelta, timezone

from app.kommo.base import KommoContact
from app.kommo.mock import LEADS, MockKommo
from app.services.cabinet import load_client

BALI = timezone(timedelta(hours=8))


class TwoContacts(MockKommo):
    """Контакт 701 (Telegram, без визы, сделка «Ждем $») + дубль 702 (WhatsApp, с «Виза до», без сделок)."""

    def __init__(self):
        visa = int(datetime(2027, 5, 20, tzinfo=BALI).timestamp())
        self.c = {
            701: KommoContact(701, "Татьяна Лебедева", ["+79119761793"], {"Логин": "souzemlivod"}, [1001]),
            702: KommoContact(702, "Татьяна", ["+7 911 976-17-93"], {"Виза до": visa}, []),
        }

    def get_contact(self, cid):
        return self.c.get(cid)

    def get_contacts(self, ids):
        return [self.c[i] for i in ids if i in self.c]

    def get_leads(self, ids):
        return [LEADS[i] for i in ids if i in LEADS]


def test_visa_date_from_duplicate_contact_is_shown():
    data = load_client(TwoContacts(), [701, 702], with_history=False)
    assert [s["lead_id"] for s in data["services"]] == [1001]
    visa = [d for d in data["dates"] if d["title"] == "Окончание визы"]
    assert visa and visa[0]["date"] == "2027-05-20" and visa[0]["person"] == "Татьяна"
    assert date.fromisoformat(visa[0]["date"]) > date.today()


class NamelessPassportContact(MockKommo):
    """Как у Tesa: сделка «Успешно реализовано» (E33G) с двумя контактами — клиент + безымянный с «ITK до»."""

    def __init__(self):
        itk = int(datetime(2027, 4, 20, tzinfo=BALI).timestamp())
        self.c = {
            801: KommoContact(801, "Татьяна Лебедева", ["+79119761793"], {}, [3001]),
            802: KommoContact(802, "", [], {"ITK до": itk, "Виза до": itk, "Текущая виза": "E33G"}, [3001]),
        }
        from app.kommo.base import KommoLead
        self.leads = {3001: KommoLead(3001, "Сделка", 8_000_000, 13724291, 142, "Успешно реализовано",
                                      {"Тип услуги": "E33G"}, [801, 802])}

    def get_contact(self, cid):
        return self.c.get(cid)

    def get_contacts(self, ids):
        return [self.c[i] for i in ids if i in self.c]

    def get_leads(self, ids):
        return [self.leads[i] for i in ids if i in self.leads]

    def get_lead_files(self, lead_id):
        return []


def test_dates_from_nameless_contact_on_deal():
    data = load_client(NamelessPassportContact(), [801], with_history=False)
    assert data["services"] and data["services"][0]["badge"] == "Действует"
    assert data["services"][0]["valid_until"] == "2027-04-20"
    assert any(d["date"] == "2027-04-20" and d["person"] == "Татьяна" for d in data["dates"])
