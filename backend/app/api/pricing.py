from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import catalog, pricing
from app.api.companies import owned_company
from app.core.db import get_db
from app.core.errors import validation
from app.core.security import client_user
from app.enums import BorrowingMode
from app.models import User
from app.schemas import QuoteIn
from app.services import applications as svc
from app.simulators import bureau

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.post("/quote")
def quote(body: QuoteIn, user: User = Depends(client_user), db: Session = Depends(get_db)):
    company = owned_company(body.company_id, user, db)
    errors = {}
    loan = None
    if body.borrowing_mode == BorrowingMode.REFINANCE:
        if body.existing_loan_id is None:
            errors["existing_loan_id"] = "Выберите кредит для рефинансирования"
        else:
            loan = svc.owned_loan(db, company.id, body.existing_loan_id)
        amount = loan.balance if loan else None
    else:
        amount = body.amount
        if amount is None:
            errors["amount"] = "Укажите сумму"
        elif err := pricing.amount_error(company.legal_form, amount):
            errors["amount"] = err
    if err := pricing.term_error(body.term_months):
        errors["term_months"] = err
    if errors:
        raise validation(errors)

    rating = bureau.get_rating(db, company.id)
    score = rating.score if rating else None
    rate = pricing.preliminary_rate(score, body.term_months, body.borrowing_mode)
    payment = pricing.annuity(amount, rate, body.term_months)
    result = {
        "amount": amount,
        "term_months": body.term_months,
        "rate": float(rate),
        "monthly_payment": payment,
        "rating_based": score is not None,
        "rating_note": None if score is not None else "расчёт без рейтинга",
        "preliminary_note": catalog.PRELIMINARY_NOTE,
        "comparison": None,
    }
    if loan:
        result["comparison"] = {**pricing.refinance_comparison(loan.rate, loan.next_payment_amount, rate, payment),
                                "note": catalog.REFINANCE_COMPARISON_NOTE}
    return result
