"""Лимиты и предварительный расчёт условий (инструкция §4, §7). Единственный источник правил."""

from decimal import ROUND_HALF_UP, Decimal

from app.enums import BorrowingMode, LegalForm

MIN_AMOUNT = 100_000
AMOUNT_STEP = 50_000
MAX_AMOUNT = {LegalForm.IP: 3_000_000, LegalForm.OOO: 10_000_000}
MIN_TERM = 6
MAX_TERM = 36
TERM_STEP = 1
DEFAULT_AMOUNT = 1_000_000
DEFAULT_TERM = 12

RATING_MIN = 0
RATING_MAX = 1000
NEW_BUSINESS_RATING = 600
# (от, до, код, подпись, базовая ставка)
RATING_BANDS = [
    (750, 1000, "HIGH", "высокий", Decimal("18")),
    (500, 749, "MEDIUM", "средний", Decimal("22")),
    (0, 499, "LOW", "низкий", Decimal("27")),
]
NO_RATING_RATE = Decimal("24")
LONG_TERM_FROM = 25
LONG_TERM_SURCHARGE = Decimal("2")
REFINANCE_DISCOUNT = Decimal("1")


def rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


def rating_band(score: int) -> tuple[str, str]:
    for lo, hi, code, label, _ in RATING_BANDS:
        if lo <= score <= hi:
            return code, label
    raise ValueError(f"score out of range: {score}")


def preliminary_rate(score: int | None, term_months: int, mode: str) -> Decimal:
    """Без рейтинга базой служит 24 %; надбавка за срок и скидка рефинансирования применяются одинаково."""
    if score is None:
        rate = NO_RATING_RATE
    else:
        rate = next(r for lo, hi, *_, r in RATING_BANDS if lo <= score <= hi)
    if term_months >= LONG_TERM_FROM:
        rate += LONG_TERM_SURCHARGE
    if mode == BorrowingMode.REFINANCE:
        rate -= REFINANCE_DISCOUNT
    return rate


def annuity(amount: int, annual_rate: Decimal, term_months: int) -> int:
    r = Decimal(annual_rate) / Decimal(1200)
    if r == 0:
        payment = Decimal(amount) / term_months
    else:
        payment = Decimal(amount) * r / (1 - (1 + r) ** -term_months)
    return int(payment.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def amount_error(legal_form: str, amount: int) -> str | None:
    max_amount = MAX_AMOUNT[LegalForm(legal_form)]
    if amount < MIN_AMOUNT:
        return f"Минимальная сумма — {rub(MIN_AMOUNT)}"
    if amount > max_amount:
        return f"Максимальная сумма для {'ИП' if legal_form == LegalForm.IP else 'ООО'} — {rub(max_amount)}"
    if amount % AMOUNT_STEP:
        return f"Сумма должна быть кратна {rub(AMOUNT_STEP)}"
    return None


def term_error(term_months: int) -> str | None:
    if not MIN_TERM <= term_months <= MAX_TERM:
        return f"Срок — от {MIN_TERM} до {MAX_TERM} месяцев"
    return None


def refinance_comparison(current_rate: Decimal, current_payment: int, new_rate: Decimal, new_payment: int) -> dict:
    return {
        "current_rate": float(current_rate),
        "current_next_payment": current_payment,
        "new_rate": float(new_rate),
        "new_payment": new_payment,
        "rate_delta": float(new_rate - current_rate),
        "payment_delta": new_payment - current_payment,
        "rate_is_lower": new_rate < current_rate,
        "payment_is_lower": new_payment < current_payment,
        # Экономию не обещаем: «лучше» только если ставка действительно ниже
        "is_better": new_rate < current_rate,
    }


def config() -> dict:
    return {
        "amount": {
            "min": MIN_AMOUNT,
            "step": AMOUNT_STEP,
            "max_by_legal_form": {k.value: v for k, v in MAX_AMOUNT.items()},
            "default": DEFAULT_AMOUNT,
        },
        "term": {"min": MIN_TERM, "max": MAX_TERM, "step": TERM_STEP, "default": DEFAULT_TERM},
        "rating": {
            "min": RATING_MIN,
            "max": RATING_MAX,
            "bands": [{"from": lo, "to": hi, "code": c, "label": lbl, "base_rate": float(r)} for lo, hi, c, lbl, r in RATING_BANDS],
            "new_business_rating": NEW_BUSINESS_RATING,
        },
        "rate_rules": {
            "no_rating_rate": float(NO_RATING_RATE),
            "long_term_from_months": LONG_TERM_FROM,
            "long_term_surcharge": float(LONG_TERM_SURCHARGE),
            "refinance_discount": float(REFINANCE_DISCOUNT),
        },
    }
