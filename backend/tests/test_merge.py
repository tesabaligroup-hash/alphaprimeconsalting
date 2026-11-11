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
