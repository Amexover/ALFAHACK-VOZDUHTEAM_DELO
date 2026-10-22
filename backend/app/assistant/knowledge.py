"""Bounded lexical RAG. No embedding service and no fetching user-supplied URLs."""
import json
import math
import re
from datetime import timezone

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog, pricing
from app.assistant.models import KnowledgeDocument
from app.content_data import SUPPORT
from app.models import News


def builtin_documents() -> list[dict]:
    def doc(id_, title, body, audience="client"):
        return {"id": id_, "title": title, "body": body, "audience": audience,
                "kind": "knowledge", "url": f"/api/assistant/knowledge/{id_}",
                "published_at": None, "is_demo": True}

    return [
        doc("products", "Кредитные продукты и цели", json.dumps(list(catalog.PRODUCTS.values()), ensure_ascii=False)),
        doc("pricing", "Лимиты суммы, срока и предварительные ставки",
            json.dumps(pricing.config(), ensure_ascii=False) + "\n" + catalog.PRELIMINARY_NOTE),
        doc("credit-rating", "Кредитный рейтинг компании",
            "Рейтинг бюро — демонстрационная шкала 0–1000: 0–499 низкий, 500–749 средний, "
            "750–1000 высокий. " + catalog.RATING_HINT + " " + catalog.RATING_SOURCE_LABEL +
            ". История изменения балла и причины его изменения в симуляторе отсутствуют. "
            "Рекомендации: проверяйте корректность кредитной истории и своевременность платежей. "
            "Нельзя обещать прирост балла или одобрение от выполнения совета."),
        doc("application-statuses", "Этапы и статусы заявки",
            json.dumps({k.value: {"label": v, "next_step": catalog.NEXT_STEPS[k]}
                        for k, v in catalog.STATUS_LABELS.items()}, ensure_ascii=False)),
        doc("business-profile", "Анкета бизнеса и необходимые сведения",
            json.dumps(catalog.PROFILE_FIELDS, ensure_ascii=False) +
            "\nВ MVP загрузки документов нет. Регистрация и кредитная история проверяются локальными симуляторами."),
        doc("refinancing", "Рефинансирование действующего кредита",
            "Выберите действующий кредит своей компании. Сумма заявки равна остатку долга. "
            "Предварительная ставка рассчитывается сервером с учётом рейтинга, срока и скидки. "
            + catalog.REFINANCE_COMPARISON_NOTE),
        doc("support", "Частые вопросы и поддержка", json.dumps(SUPPORT, ensure_ascii=False)),
        doc("staff-review", "Разбор заявки сотрудником", "Сопоставьте анкету, проверки и текущую оценку "
            "по версионированным правилам. Рейтинг бюро 0–1000 не равен внутреннему баллу 0–100. "
            "Оценка после решения фиксируется снимком. Верификатор проверяет полноту сведений, "
            "андеррайтер принимает решение. Помощник составляет только сводки и черновики, "
            "действия выполняет сотрудник через существующий конвейер.", "staff"),
    ]


def document_view(doc: KnowledgeDocument) -> dict:
    def timestamp(value):
        if value is None:
            return None
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()

    return {"id": doc.id, "title": doc.title, "body": doc.body, "audience": doc.audience,
            "kind": doc.kind, "url": doc.source_url or f"/api/assistant/knowledge/{doc.id}",
            "published_at": timestamp(doc.published_at),
            "is_demo": False, "updated_at": timestamp(doc.updated_at)}


def documents(db: Session, audience: str, kind: str = "knowledge") -> list[dict]:
    allowed = ["client", "staff"] if audience == "staff" else ["client"]
    rows = db.scalars(select(KnowledgeDocument).where(
        KnowledgeDocument.audience.in_(allowed), KnowledgeDocument.kind == kind
    ).order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id).limit(500)).all()
    result = [document_view(row) for row in rows]
    if kind == "knowledge":
        result += [d for d in builtin_documents() if d["audience"] in allowed]
    return result


STOP = {"для", "как", "что", "это", "или", "при", "мне", "мой", "моя", "есть", "про", "какие", "можно", "чтобы"}


def terms(text: str) -> set[str]:
    # Prefixes tolerate common Russian inflections without an extra NLP dependency.
    return {t[:6] if len(t) > 6 else t for t in re.findall(r"[а-яёa-z0-9]+", text.lower())
            if len(t) > 2 and t not in STOP}


def search(db: Session, audience: str, query: str, limit: int = 5) -> list[dict]:
    query_terms = terms(query)
    if not query_terms:
        return []
    candidates = []
    for doc in documents(db, audience):
        for index, start in enumerate(range(0, len(doc["body"]), 900)):
            chunk = doc["body"][start:start + 1100]
            title_overlap = len(query_terms & terms(doc["title"]))
            overlap = len(query_terms & terms(chunk))
            rank = (3 * title_overlap + overlap) / math.sqrt(max(1, len(terms(chunk))))
            if rank > 0:
                candidates.append((rank, doc["id"], index, {
                    "id": f"doc:{doc['id']}:{index}", "title": doc["title"], "kind": "knowledge",
                    "url": doc["url"], "published_at": doc["published_at"],
                    "is_demo": doc["is_demo"], "excerpt": chunk,
                }))
    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [x[3] for x in candidates[:limit]]


def news(db: Session, audience: str, query: str = "", limit: int = 6) -> list[dict]:
    query_terms = terms(query)
    current = documents(db, audience, "news")
    current.sort(key=lambda d: (len(query_terms & terms(d["title"] + " " + d["body"])),
                                d["published_at"] or ""), reverse=True)
    items = [{"id": f"news:{d['id']}", "title": d["title"], "kind": "news", "url": d["url"],
              "published_at": d["published_at"], "is_demo": False, "excerpt": d["body"][:1800]}
             for d in current[:limit]]
    if not items:
        rows = db.scalars(select(News).order_by(News.position, News.id).limit(50)).all()
        rows = sorted(rows, key=lambda n: -len(query_terms & terms(n.title + " " + n.body)))
        items = [{"id": f"demo-news:{n.id}", "title": n.title, "kind": "news",
                  "url": f"/api/news/{n.id}", "published_at": None, "is_demo": True,
                  "excerpt": n.body[:1800]} for n in rows[:limit]]
    return jsonable_encoder(items)
