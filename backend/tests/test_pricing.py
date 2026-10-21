from decimal import Decimal

import pytest

from app import pricing


@pytest.mark.parametrize("score,term,mode,expected", [
    (1000, 12, "NEW_CREDIT", "18"),
    (750, 12, "NEW_CREDIT", "18"),
    (749, 12, "NEW_CREDIT", "22"),
    (500, 12, "NEW_CREDIT", "22"),
    (499, 12, "NEW_CREDIT", "27"),
    (0, 12, "NEW_CREDIT", "27"),
    (820, 24, "NEW_CREDIT", "18"),
    (820, 25, "NEW_CREDIT", "20"),
    (420, 36, "NEW_CREDIT", "29"),
    (None, 12, "NEW_CREDIT", "24"),
    (820, 12, "REFINANCE", "17"),
    (420, 30, "REFINANCE", "28"),
])
def test_rate(score, term, mode, expected):
    assert pricing.preliminary_rate(score, term, mode) == Decimal(expected)


def test_annuity():
    # 1 000 000 ₽, 18 % годовых, 12 мес. → 91 680 ₽
    assert pricing.annuity(1_000_000, Decimal("18"), 12) == 91_680
    assert pricing.annuity(600_000, Decimal("0"), 6) == 100_000


def test_amount_limits():
    assert pricing.amount_error("IP", 3_000_000) is None
    assert pricing.amount_error("IP", 3_050_000)
    assert pricing.amount_error("OOO", 10_000_000) is None
    assert pricing.amount_error("OOO", 50_000)
    assert pricing.amount_error("OOO", 120_000)  # не кратно шагу
    assert pricing.term_error(5) and pricing.term_error(37)
    assert pricing.term_error(6) is None and pricing.term_error(36) is None


def test_quote_endpoint(alexey):
    from tests.conftest import company_id
    ip = company_id(alexey, "ИП")
    r = alexey.post("/pricing/quote", {"company_id": ip, "borrowing_mode": "NEW_CREDIT", "amount": 1_000_000, "term_months": 12})
    assert r.json()["rate"] == 18.0 and r.json()["monthly_payment"] == 91_680
    r = alexey.post("/pricing/quote", {"company_id": ip, "borrowing_mode": "NEW_CREDIT", "amount": 3_500_000, "term_months": 12})
    assert r.status_code == 422 and "amount" in r.json()["error"]["fields"]


def test_quote_refinance_comparison(alexey):
    from tests.conftest import company_id
    ip = company_id(alexey, "ИП")
    loan = alexey.get(f"/companies/{ip}/loans").json()["items"][0]
    r = alexey.post("/pricing/quote", {"company_id": ip, "borrowing_mode": "REFINANCE", "existing_loan_id": loan["id"], "term_months": 12}).json()
    assert r["amount"] == 600_000 and r["rate"] == 17.0
    assert r["comparison"]["current_rate"] == 25.0 and r["comparison"]["is_better"] is True


def test_quote_without_rating(alexey):
    from app.simulators import bureau
    from tests.conftest import company_id
    bureau.set_available(False)
    ip = company_id(alexey, "ИП")
    r = alexey.post("/pricing/quote", {"company_id": ip, "borrowing_mode": "NEW_CREDIT", "amount": 1_000_000, "term_months": 12}).json()
    assert r["rate"] == 24.0 and r["rating_based"] is False
