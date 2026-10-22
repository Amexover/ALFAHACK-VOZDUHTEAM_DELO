"""Конфигурация, контент и служебные демо-эндпоинты."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import catalog, pricing
from app.content_data import SUPPORT
from app.core.db import get_db
from app.core.errors import ApiError, not_found
from app.core.security import current_user
from app.core.settings import settings
from app.models import Company, News, User
from app.schemas import BureauToggleIn
from app.seed import init_db
from app.services.news import ordered_news
from app.simulators import bureau

router = APIRouter(tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok", "bureau_available": bureau.is_available()}


@router.get("/config")
def config():
    return {
        **pricing.config(),
        "products": list(catalog.PRODUCTS.values()),
        "borrowing_modes": list(catalog.BORROWING_MODES.values()),
        "legal_forms": list(catalog.LEGAL_FORMS.values()),
        "statuses": [{"status": k.value, "label": v} for k, v in catalog.STATUS_LABELS.items()],
        "stages": [{"key": k, "label": v} for k, v in catalog.STAGES],
        "profile_fields": catalog.PROFILE_FIELDS,
        "texts": {
            "rating_source": catalog.RATING_SOURCE_LABEL,
            "rating_hint": catalog.RATING_HINT,
            "rating_unavailable": catalog.RATING_UNAVAILABLE_TEXT,
            "preliminary_note": catalog.PRELIMINARY_NOTE,
            "final_terms_note": catalog.FINAL_TERMS_NOTE,
            "refinance_comparison_note": catalog.REFINANCE_COMPARISON_NOTE,
        },
    }


@router.get("/news", tags=["content"])
def news_list(company_id: int | None = None, product_id: str | None = None,
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    legal_form = None
    if company_id is not None:
        company = db.get(Company, company_id)
        if company is None or company.owner_id != user.id:
            raise not_found("Компания не найдена")
        legal_form = company.legal_form
    return {"items": ordered_news(db, legal_form, product_id)}


@router.get("/news/{news_id}", tags=["content"])
def news_detail(news_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.get(News, news_id)
    if n is None:
        raise not_found("Материал не найден")
    return {"id": n.id, "tag": n.tag, "title": n.title, "summary": n.summary, "body": n.body}


@router.get("/support", tags=["content"])
def support():
    return {"items": SUPPORT}


def _demo_guard():
    if not settings.demo_tools_enabled:
        raise ApiError(404, "NOT_FOUND", "Not Found")


@router.post("/demo/reset", tags=["demo"], dependencies=[Depends(_demo_guard)])
def demo_reset():
    """Сбрасывает базу к исходным демонстрационным данным."""
    from app.staff_pipeline.seed import seed_department_on_startup

    init_db(reset=True)
    seed_department_on_startup()
    bureau.set_available(settings.bureau_available)
    return {"ok": True}


@router.post("/demo/bureau", tags=["demo"], dependencies=[Depends(_demo_guard)])
def demo_bureau(body: BureauToggleIn):
    """Включает/выключает симулятор бюро, чтобы показать «Рейтинг пока недоступен»."""
    bureau.set_available(body.available)
    return {"bureau_available": bureau.is_available()}
