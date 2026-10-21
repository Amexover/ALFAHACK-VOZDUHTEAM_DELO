from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog
from app.core.db import get_db
from app.core.errors import conflict, not_found, validation
from app.core.security import client_user
from app.enums import ACTIVE_STATUSES, BorrowingMode
from app.models import Application, Company, ExistingLoan, User
from app.schemas import CompanyIn
from app.services import applications as svc
from app.services.news import ordered_news
from app.simulators import bureau, registry

router = APIRouter(prefix="/companies", tags=["companies"])


def owned_company(company_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)) -> Company:
    company = db.get(Company, company_id)
    if company is None or company.owner_id != user.id:
        raise not_found("Компания не найдена")
    return company


@router.get("")
def list_companies(user: User = Depends(client_user), db: Session = Depends(get_db)):
    items = db.scalars(select(Company).where(Company.owner_id == user.id).order_by(Company.id)).all()
    return {"items": [svc.company_view(c) for c in items]}


@router.post("", status_code=201)
def create_company(body: CompanyIn, user: User = Depends(client_user), db: Session = Depends(get_db)):
    name = body.name.strip()
    number = body.registration_number.strip().replace(" ", "")
    errors = {}
    if not name:
        errors["name"] = "Укажите название"
    if err := registry.format_error(body.legal_form, number):
        errors["registration_number"] = err
    if errors:
        raise validation(errors)
    duplicate = db.scalar(select(Company).where(Company.owner_id == user.id, Company.ogrn == number))
    if duplicate:
        raise conflict("DUPLICATE_COMPANY", "Компания с таким номером уже добавлена")
    company = Company(owner_id=user.id, legal_form=body.legal_form, name=name, ogrn=number)
    db.add(company)
    db.flush()
    bureau.register_new_company(db, company)
    db.commit()
    return svc.company_view(company)


def _loans(db: Session, company_id: int) -> list[ExistingLoan]:
    return db.scalars(select(ExistingLoan).where(ExistingLoan.company_id == company_id).order_by(ExistingLoan.id)).all()


@router.get("/{company_id}/dashboard")
def dashboard(company: Company = Depends(owned_company), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.company_id == company.id)
                      .order_by(Application.id.desc())).all()
    active = [a for a in apps if a.status in ACTIVE_STATUSES]
    new_credit = next((a for a in active if a.borrowing_mode == BorrowingMode.NEW_CREDIT), None)
    rating = bureau.get_rating(db, company.id)
    return {
        "company": svc.company_view(company),
        "client": {"full_name": company.owner.full_name, "first_name": company.owner.first_name},
        "rating": bureau.rating_view(rating),
        "rating_unavailable_text": None if rating else catalog.RATING_UNAVAILABLE_TEXT,
        "loans": [svc.loan_view(l) for l in _loans(db, company.id)],
        "active_applications": [svc.brief_view(a) for a in active],
        "past_applications": [svc.brief_view(a) for a in apps if a.status not in ACTIVE_STATUSES],
        "news": ordered_news(db, company.legal_form, new_credit.product_id if new_credit else None),
    }


@router.get("/{company_id}/loans")
def loans(company: Company = Depends(owned_company), db: Session = Depends(get_db)):
    result = []
    for loan in _loans(db, company.id):
        taken = db.scalar(select(Application.id).where(Application.existing_loan_id == loan.id,
                                                       Application.status.in_(ACTIVE_STATUSES)))
        result.append({**svc.loan_view(loan), "active_application_id": taken})
    return {"items": result}


@router.get("/{company_id}/applications")
def company_applications(company: Company = Depends(owned_company), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.company_id == company.id)
                      .order_by(Application.id.desc())).all()
    return {"items": [svc.brief_view(a) for a in apps]}
