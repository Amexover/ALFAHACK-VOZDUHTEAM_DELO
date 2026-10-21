"""Фиксированные демонстрационные данные (§2). Идемпотентно: повторный запуск ничего не дублирует."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content_data import NEWS
from app.core.db import Base, engine
from app.core.security import hash_password
from app.enums import LegalForm, ProductId, Role
from app.models import BureauRating, Company, ExistingLoan, News, User

DEMO_PASSWORD = "demo"
RATING_DATE = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)

USERS = [
    ("alexey", "Алексей Морозов", "Алексей", Role.CLIENT),
    ("maria", "Мария Ковалёва", "Мария", Role.CLIENT),
    ("staff", "Ирина Котова", "Ирина", Role.EMPLOYEE),
]

# (владелец, форма, название, номер, рейтинг, кредит)
COMPANIES = [
    ("alexey", LegalForm.IP, "ИП Морозов Алексей Сергеевич", "000000000000001", 820,
     (ProductId.WORKING_CAPITAL, 900_000, 600_000, "25", 36_000)),
    ("alexey", LegalForm.OOO, "ООО «Маяк Трейд»", "0000000000002", 620, None),
    ("alexey", LegalForm.OOO, "ООО «Вектор-Станок»", "0000000000003", 420,
     (ProductId.EQUIPMENT, 3_000_000, 2_000_000, "23", 115_000)),
    ("maria", LegalForm.OOO, "ООО «Северный Склад»", "0000000000004", 700, None),
]
NEXT_PAYMENT_DATE = date(2026, 11, 20)


def seed(db: Session) -> None:
    if db.scalar(select(User).limit(1)) is not None:
        return
    users = {}
    for login, full_name, first_name, role in USERS:
        u = User(login=login, password_hash=hash_password(DEMO_PASSWORD), full_name=full_name, first_name=first_name, role=role)
        db.add(u)
        users[login] = u
    db.flush()
    for owner, form, name, ogrn, score, loan in COMPANIES:
        c = Company(owner_id=users[owner].id, legal_form=form, name=name, ogrn=ogrn)
        db.add(c)
        db.flush()
        db.add(BureauRating(company_id=c.id, score=score, updated_at=RATING_DATE))
        if loan:
            product, original, balance, rate, payment = loan
            db.add(ExistingLoan(company_id=c.id, product_id=product, original_amount=original, balance=balance,
                                rate=Decimal(rate), next_payment_amount=payment, next_payment_date=NEXT_PAYMENT_DATE))
    for i, n in enumerate(NEWS):
        db.add(News(position=i, **n))
    db.commit()


def init_db(reset: bool = False) -> None:
    from app.core.db import SessionLocal

    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
