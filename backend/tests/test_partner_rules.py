import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app.partner_rules import accrual_status, calc_payouts, codeword_problems, next_payout_date, payout_date_for, short_name
from app.tariffs import TARIFFS, find_tariff

EXPECTED = json.loads((Path(__file__).parent / "data" / "tariffs_expected.json").read_text())


def test_all_services_from_table_15_11_loaded():
    codes = {t.code for t in TARIFFS}
    assert {e["code"] for e in EXPECTED} <= codes


@pytest.mark.parametrize("row", EXPECTED, ids=[e["code"] for e in EXPECTED])
def test_prices_and_payouts_match_table(row):
    """Цены и выплаты совпадают с таблицей «Тарифы партнёрской программы» (15.11.2026) по каждой услуге."""
    t = find_tariff(row["sheet_code"])
    assert t.code == row["code"]
    assert (t.price, t.partner_cost, t.market, t.white_label) == (row["price"], row["cost"], row["market"], row["white_label"])
    p = calc_payouts(t)
    assert p.client_price == (row["partner_price"] or row["price"])
    assert (p.level1, p.level2) == (row["l1"], row["l2"])
    assert p.level2 * 5 == p.level1  # 2-й уровень — 20% от 1-го, одинаково для всех услуг


def test_payout_does_not_depend_on_budget_when_standard_discount():
    t = find_tariff("E33G")
    assert calc_payouts(t, deal_price=11_305_000).level1 == 1_000_000
    assert calc_payouts(t, deal_price=None).level1 == 1_000_000


def test_huge_manager_discount_never_pays_more_than_margin():
    t = find_tariff("C1")  # себестоимость 1 000 000, выплаты 200 000 + 40 000
    p = calc_payouts(t, deal_price=1_120_000)  # маржа 120 000
    assert p.level1 + p.level2 <= 120_000 and p.level1 == 100_000 and p.level2 == 20_000


def test_service_without_payouts_goes_to_manager():
    t = find_tariff("ADR")
    assert t.l1 is None and calc_payouts(t).known is False


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
