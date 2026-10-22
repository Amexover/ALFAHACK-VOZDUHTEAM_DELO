"""Фикстура полной Postman-приёмки, только на отдельной базе; без reset."""
import argparse

from sqlalchemy import select

from app.main import app  # noqa: F401 — регистрирует модели отдела
from app.core.db import SessionLocal
from app.enums import BorrowingMode, LegalForm, Status
from app.models import Application, BureauRating, Company, User, utcnow
from app.seed import init_db
from app.staff_pipeline.seed import seed_department


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated", required=True, action="store_true")
    parser.parse_args()
    init_db()
    with SessionLocal() as db:
        seed_department(db, with_queue=False)
        if db.scalar(select(Application.id).where(Application.number == "AUTO-T4-FIXTURE")):
            print("Фикстура уже существует")
            return
        owner = db.scalar(select(User).where(User.login == "alexey"))
        company = Company(owner_id=owner.id, legal_form=LegalForm.OOO,
                          name="ООО «Приёмка автоматической политики»", ogrn="3999999999999")
        db.add(company)
        db.flush()
        db.add(BureauRating(company_id=company.id, score=299, updated_at=utcnow()))
        db.add(Application(company_id=company.id, number="AUTO-T4-FIXTURE", borrowing_mode=BorrowingMode.NEW_CREDIT,
                           product_id="WORKING_CAPITAL", amount=900000, term_months=18,
                           preliminary_rate=30, preliminary_payment=62703,
                           status=Status.IN_REVIEW, submitted_at=utcnow(),
                           business_profile={"industry": "Торговля", "months_operating": 36,
                                             "monthly_revenue": 100000, "monthly_debt_payments": 100001,
                                             "purpose_details": "Изолированная приёмка"}))
        db.commit()
        print("AUTO-T4-FIXTURE создана")


if __name__ == "__main__":
    main()
