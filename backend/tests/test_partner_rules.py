import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app.partner_rules import accrual_status, calc_payouts, codeword_problems, next_payout_date, payout_date_for, short_name
from app.tariffs import TARIFFS, find_tariff

EXPECTED = json.loads((Path(__file__).parent / "data" / "tariffs_expected.json").read_text())


def test_all_43_services_loaded():
    assert len(TARIFFS) == 43
    assert {t.code for t in TARIFFS} == {e["code"] for e in EXPECTED}


@pytest.mark.parametrize("row", EXPECTED, ids=[e["code"] for e in EXPECTED])
def test_payouts_match_spreadsheet(row):
    """Выплаты по формулам совпадают с таблицей «Тарифы партнёрской программы» по всем услугам."""
    t = find_tariff(row["code"])
    assert t.price == row["price"] and t.partner_cost == row["partner_cost"]
    p = calc_payouts(t)
    assert (p.plan_a, p.plan_b_l1, p.plan_b_l2) == (row["plan_a"], row["plan_b1"], row["plan_b2"])


def test_example_from_spec_kitas_investor_plan_b():
    p = calc_payouts(find_tariff("E28A-2-P"))
    assert p.margin == 8_500_000
    assert p.discount == 425_000 and p.client_price == 17_575_000
    assert p.plan_b_l1 == 850_000 and p.plan_b_l2 == 425_000


def test_bigger_manager_discount_uses_actual_margin():
    t = find_tariff("E33G")  # 10 900 000, себестоимость 7 000 000
    p = calc_payouts(t, deal_price=10_000_000)
    assert p.margin == 3_000_000 and p.plan_a == 450_000


def test_standard_discount_keeps_nominal_margin():
    t = find_tariff("E33G")
    assert calc_payouts(t, deal_price=10_705_000).plan_a == 585_000


@pytest.mark.parametrize("word,ok", [
    ("ANNABALI", True), ("annabali", True), ("ВИКТОРИЯ", True), ("TOPGYM2026", True),
    ("ANNA", False), ("VISA", False), ("виза", False), ("KITAS", False), ("VISA12", False), ("bali", False),
    ("ALPHAPRIME", False), ("ANNA BALI", True),  # пробел убирается → ANNABALI
    ("ANNA-BALI", False),
])
def test_codeword_rules(word, ok):
    assert (codeword_problems(word) == []) is ok


def test_codeword_admin_stop_words():
    assert codeword_problems("CANGGU", {"canggu"})


@pytest.mark.parametrize("day,expected", [
    (date(2026, 11, 3), date(2026, 11, 10)),
    (date(2026, 11, 5), date(2026, 11, 10)),
    (date(2026, 11, 6), date(2026, 11, 25)),
    (date(2026, 11, 20), date(2026, 11, 25)),
    (date(2026, 11, 21), date(2026, 12, 10)),
    (date(2026, 12, 28), date(2027, 1, 11)),  # 10.01.2027 — воскресенье → понедельник
])
def test_payout_dates(day, expected):
    assert payout_date_for(day) == expected


def test_next_payout_date():
    assert next_payout_date(date(2026, 11, 11)) == date(2026, 11, 25)
    assert next_payout_date(date(2026, 11, 26)) == date(2026, 12, 10)


def test_accrual_status_flow():
    now = datetime(2026, 11, 11)
    kw = dict(cancelled=False, now=now, gold=False)
    assert accrual_status(fully_paid=False, result_issued_at=None, **kw)[0] == "awaiting_payment"
    assert accrual_status(fully_paid=True, result_issued_at=None, **kw)[0] == "in_work"
    assert accrual_status(fully_paid=True, result_issued_at=datetime(2026, 11, 8), **kw)[0] == "confirmed"
    assert accrual_status(fully_paid=True, result_issued_at=datetime(2026, 11, 3), **kw)[0] == "to_payout"
    # Gold: удержание 3 дня
    assert accrual_status(fully_paid=True, result_issued_at=datetime(2026, 11, 8), cancelled=False, now=now, gold=True)[0] == "to_payout"
    assert accrual_status(fully_paid=True, result_issued_at=None, cancelled=True, now=now, gold=False)[0] == "cancelled"


def test_short_name_hides_surname():
    assert short_name("MARIA KUZNETSOVA") == "Maria K."
    assert short_name("Мария Кузнецова") == "Мария К."
    assert short_name("@olga_bali") == "@olga_bali"
