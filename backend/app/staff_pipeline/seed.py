"""Демонстрационные данные отдела сотрудников.

Свой сид, независимый от app.seed: он не правит и не перезапускает чужие данные.
Идемпотентен — повторный запуск ничего не дублирует. Работает и на пустой базе,
и на заполненной базе сервера, где чужой сид выходит на первом же пользователе.
"""

import os
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import pricing
from app.core.security import hash_password
from app.enums import BorrowingMode, EventType, LegalForm, ProductId, Role, Status
from app.models import (
    Application,
    ApplicationEvent,
    BureauRating,
    Company,
    ExistingLoan,
    InfoRequest,
    User,
    utcnow,
)
from app.staff_pipeline.enums import StaffRole
from app.staff_pipeline.models import StaffProfile

DEMO_PASSWORD = "demo"

# (логин, ФИО, имя, роль внутри отдела)
DEPARTMENT_STAFF = [
    ("verifier", "Наталья Белова", "Наталья", StaffRole.VERIFIER),
    ("underwriter", "Сергей Гущин", "Сергей", StaffRole.UNDERWRITER),
]

# Владельцы демонстрационных заявок отдела. Клиенты чужого сида не затрагиваются.
DEPARTMENT_CLIENTS = [
    ("pavel", "Павел Сорокин", "Павел"),
    ("olga", "Ольга Нечаева", "Ольга"),
]

# (владелец, форма, название, ОГРН/ОГРНИП, рейтинг бюро)
DEPARTMENT_COMPANIES = [
    ("pavel", LegalForm.IP, "ИП Сорокин Павел Игоревич", "300000000000011", 760),
    ("pavel", LegalForm.OOO, "ООО «Хлебный Двор»", "3000000000012", 690),
    ("olga", LegalForm.OOO, "ООО «ТехноСнаб»", "3000000000013", 540),
    ("olga", LegalForm.OOO, "ООО «Мебель Прайм»", "3000000000014", 470),
    ("olga", LegalForm.OOO, "ООО «Грузовой Экспресс»", "3000000000015", 350),
]

# Действующий кредит — нужен для демонстрационной заявки на рефинансирование.
DEPARTMENT_LOANS = [
    ("3000000000012", ProductId.WORKING_CAPITAL, 1_500_000, 900_000, "26", 52_000),
]

SEED_MARKER_OGRN = DEPARTMENT_COMPANIES[0][3]


def _profile(industry: str, months: int, revenue: int, debts: int, purpose: str) -> dict:
    return {
        "industry": industry,
        "months_operating": months,
        "monthly_revenue": revenue,
        "monthly_debt_payments": debts,
        "purpose_details": purpose,
    }


# (ОГРН компании, режим, продукт, сумма, срок, часов назад, анкета, статус)
DEPARTMENT_APPLICATIONS = [
    ("300000000000011", BorrowingMode.NEW_CREDIT, ProductId.WORKING_CAPITAL, 1_200_000, 18, 30,
     _profile("Оптовая торговля стройматериалами", 48, 2_400_000, 90_000,
              "Закупка материалов под два подряда до конца года"),
     Status.IN_REVIEW),
    ("3000000000012", BorrowingMode.NEW_CREDIT, ProductId.EQUIPMENT, 2_500_000, 24, 6,
     _profile("Производство хлебобулочных изделий", 72, 5_100_000, 180_000,
              "Покупка второй тестомесильной линии"),
     Status.IN_REVIEW),
    ("3000000000013", BorrowingMode.NEW_CREDIT, ProductId.WORKING_CAPITAL, 3_000_000, 30, 3,
     _profile("Поставка промышленных комплектующих", 30, 4_200_000, 640_000,
              "Пополнение склада перед сезоном закупок"),
     Status.IN_REVIEW),
    ("3000000000014", BorrowingMode.NEW_CREDIT, ProductId.EQUIPMENT, 1_500_000, 12, 1,
     _profile("Производство корпусной мебели", 9, 1_900_000, 150_000,
              "Покупка кромкооблицовочного станка"),
     Status.IN_REVIEW),
    ("3000000000015", BorrowingMode.NEW_CREDIT, ProductId.WORKING_CAPITAL, 800_000, 36, 50,
     _profile("Грузовые перевозки", 26, 1_300_000, 420_000,
              "Оборотные средства на топливо и ремонт"),
     Status.NEED_INFO),
    ("3000000000012", BorrowingMode.REFINANCE, None, None, 24, 20,
     _profile("Производство хлебобулочных изделий", 72, 5_100_000, 180_000,
              "Хотим снизить ставку по действующему кредиту"),
     Status.IN_REVIEW),
]

INFO_REQUEST_TEXT = "Подтвердите среднемесячную выручку за последние шесть месяцев."
INFO_REQUEST_FIELDS = ["monthly_revenue"]


# ---------- сотрудники отдела ----------

def promote_existing_staff(db: Session) -> int:
    """Существующие учётные записи сотрудников становятся андеррайтерами.

    Прежние права не меняются: общая роль остаётся EMPLOYEE, и все ручки,
    которые работали раньше, продолжают работать. Правила конвейера к этим
    учётным записям не применяются (pipeline_enforced=False) — по контракту их
    поведение менять нельзя. Из новых правил для них действует только защита от
    гонки: решение по заявке, которую держит другой сотрудник, не пройдёт.
    """
    changed = 0
    for user in db.scalars(select(User).where(User.role == Role.EMPLOYEE)).all():
        if db.get(StaffProfile, user.id) is None:
            db.add(StaffProfile(user_id=user.id, staff_role=StaffRole.UNDERWRITER,
                                pipeline_enforced=False))
            changed += 1
    return changed


def seed_department_staff(db: Session) -> int:
    """Добавляет верификатора и второго андеррайтера. Повторный запуск ничего не дублирует."""
    created = 0
    for login, full_name, first_name, staff_role in DEPARTMENT_STAFF:
        user = db.scalar(select(User).where(User.login == login))
        if user is None:
            user = User(login=login, password_hash=hash_password(DEMO_PASSWORD), full_name=full_name,
                        first_name=first_name, role=Role.EMPLOYEE)
            db.add(user)
            db.flush()
            created += 1
        profile = db.get(StaffProfile, user.id)
        if profile is None:
            db.add(StaffProfile(user_id=user.id, staff_role=staff_role, pipeline_enforced=True))
        else:
            profile.staff_role = staff_role
            profile.pipeline_enforced = True
    return created


# ---------- демонстрационная очередь ----------

def demo_queue_enabled() -> bool:
    """Демо-очередь не создаётся в тестах.

    Тесты второго разработчика считают заявки в очереди, и наши демо-заявки
    изменили бы их baseline. Наши собственные тесты вызывают сид явно.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    flag = os.environ.get("DEPARTMENT_DEMO_QUEUE", "true").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _queue_already_seeded(db: Session) -> bool:
    return db.scalar(select(Company.id).where(Company.ogrn == SEED_MARKER_OGRN)) is not None


def seed_department_queue(db: Session) -> int:
    """Создаёт демонстрационные компании и заявки с разным временем подачи."""
    if _queue_already_seeded(db):
        return 0

    clients: dict[str, User] = {}
    for login, full_name, first_name in DEPARTMENT_CLIENTS:
        user = db.scalar(select(User).where(User.login == login))
        if user is None:
            user = User(login=login, password_hash=hash_password(DEMO_PASSWORD), full_name=full_name,
                        first_name=first_name, role=Role.CLIENT)
            db.add(user)
            db.flush()
        clients[login] = user

    companies: dict[str, Company] = {}
    ratings: dict[str, int] = {}
    for owner, legal_form, name, ogrn, score in DEPARTMENT_COMPANIES:
        company = Company(owner_id=clients[owner].id, legal_form=legal_form, name=name, ogrn=ogrn)
        db.add(company)
        db.flush()
        companies[ogrn] = company
        ratings[ogrn] = score
        db.add(BureauRating(company_id=company.id, score=score, updated_at=utcnow()))

    loans: dict[str, ExistingLoan] = {}
    for ogrn, product, original, balance, rate, payment in DEPARTMENT_LOANS:
        loan = ExistingLoan(company_id=companies[ogrn].id, product_id=product, original_amount=original,
                            balance=balance, rate=Decimal(rate), next_payment_amount=payment,
                            next_payment_date=(utcnow() + timedelta(days=20)).date())
        db.add(loan)
        db.flush()
        loans[ogrn] = loan

    now = utcnow()
    verifier = db.scalar(select(User).where(User.login == "verifier"))
    created = 0
    for ogrn, mode, product, amount, term, hours_ago, profile, status in DEPARTMENT_APPLICATIONS:
        company = companies[ogrn]
        submitted_at = now - timedelta(hours=hours_ago)
        loan = loans.get(ogrn) if mode == BorrowingMode.REFINANCE else None
        if loan is not None:
            amount = loan.balance
        rate = pricing.preliminary_rate(ratings[ogrn], term, mode)
        app = Application(
            company_id=company.id,
            borrowing_mode=mode,
            product_id=product.value if product else None,
            existing_loan_id=loan.id if loan else None,
            amount=amount,
            term_months=term,
            preliminary_rate=rate,
            preliminary_payment=pricing.annuity(amount, rate, term),
            rating_based=True,
            rating_used=ratings[ogrn],
            business_profile=profile,
            status=status,
            created_at=submitted_at - timedelta(minutes=25),
            updated_at=submitted_at,
            submitted_at=submitted_at,
        )
        db.add(app)
        db.flush()
        app.number = f"D-{submitted_at.year}-{app.id:06d}"
        # В общую историю заявки пишем только существующие типы событий:
        # незнакомый тип уронил бы клиентскую страницу заявки.
        owner_user = company.owner
        db.add(ApplicationEvent(application_id=app.id, type=EventType.SUBMITTED, actor_role=Role.CLIENT,
                                actor_name=owner_user.full_name, payload={}, created_at=submitted_at))
        if status == Status.NEED_INFO:
            actor = verifier or owner_user
            requested_at = submitted_at + timedelta(hours=2)
            db.add(InfoRequest(application_id=app.id, message=INFO_REQUEST_TEXT,
                               requested_fields=list(INFO_REQUEST_FIELDS), created_by=actor.full_name,
                               created_at=requested_at))
            db.add(ApplicationEvent(application_id=app.id, type=EventType.INFO_REQUESTED,
                                    actor_role=Role.EMPLOYEE, actor_name=actor.full_name,
                                    payload={"text": INFO_REQUEST_TEXT, "fields": list(INFO_REQUEST_FIELDS)},
                                    created_at=requested_at))
        created += 1
    return created


def seed_department(db: Session, with_queue: bool | None = None) -> dict[str, int]:
    """Единая точка входа сида отдела."""
    result = {
        "promoted_staff": promote_existing_staff(db),
        "created_staff": seed_department_staff(db),
        "created_applications": 0,
    }
    if with_queue is None:
        with_queue = demo_queue_enabled()
    if with_queue:
        result["created_applications"] = seed_department_queue(db)
    db.commit()
    return result


def seed_department_on_startup() -> dict[str, int]:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        return seed_department(db)
