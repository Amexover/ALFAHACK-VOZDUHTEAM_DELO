from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import News


def news_card(n: News) -> dict:
    return {"id": n.id, "tag": n.tag, "title": n.title, "summary": n.summary}


def ordered_news(db: Session, legal_form: str | None = None, product_id: str | None = None) -> list[dict]:
    """Порядок (§15): новость по цели → по правовой форме → общие → остальные."""
    items = db.scalars(select(News).order_by(News.position)).all()

    def rank(n: News) -> int:
        if product_id and n.tag == product_id:
            return 0
        if legal_form and n.tag == legal_form:
            return 1
        if n.tag == "GENERAL":
            return 2
        return 3

    return [news_card(n) for n in sorted(items, key=lambda n: (rank(n), n.position))]
