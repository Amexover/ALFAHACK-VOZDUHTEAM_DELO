"""Локальный симулятор скорингового бюро. Реальные кредитные истории не запрашиваются."""

from sqlalchemy.orm import Session

from app import catalog, pricing
from app.core.settings import settings
from app.models import BureauRating, Company, utcnow

_state = {"available": settings.bureau_available}


def is_available() -> bool:
    return _state["available"]


def set_available(value: bool) -> None:
    _state["available"] = value


def get_rating(db: Session, company_id: int) -> BureauRating | None:
    if not is_available():
        return None
    return db.get(BureauRating, company_id)


def register_new_company(db: Session, company: Company) -> None:
    db.add(BureauRating(company_id=company.id, score=pricing.NEW_BUSINESS_RATING, updated_at=utcnow()))


def rating_view(rating: BureauRating | None) -> dict | None:
    if rating is None:
        return None
    code, label = pricing.rating_band(rating.score)
    return {
        "score": rating.score,
        "max": pricing.RATING_MAX,
        "band": code,
        "band_label": label,
        "source_label": catalog.RATING_SOURCE_LABEL,
        "updated_at": rating.updated_at,
        "hint": catalog.RATING_HINT,
    }
