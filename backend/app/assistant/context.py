import json
from dataclasses import dataclass

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog, pricing
from app.assistant import knowledge
from app.assistant.models import Conversation
from app.core.errors import ApiError, not_found
from app.enums import BorrowingMode, Role, Status
from app.models import Application, Company, ExistingLoan, User, utcnow
from app.services import applications as applications_service
from app.simulators import bureau
from app.staff_pipeline.models import ApplicationPipeline
from app.staff_pipeline.views import scoring_view


def audience_of(user: User) -> str:
    if user.role == Role.CLIENT:
        return "client"
    if user.role == Role.EMPLOYEE:
        return "staff"
    raise ApiError(403, "FORBIDDEN", "Помощник недоступен для этой роли")


@dataclass
class Scope:
    audience: str
    company: Company | None
    application: Application | None


def resolve_scope(db: Session, user: User, company_id: int | None, application_id: int | None) -> Scope:
    audience = audience_of(user)
    application = None
    if application_id is not None:
        application = (applications_service.get_for_client(db, application_id, user) if audience == "client"
                       else applications_service.get_for_staff(db, application_id))
        if company_id is not None and company_id != application.company_id:
            raise not_found("Заявка не найдена в выбранной компании")
        company_id = application.company_id
    company = db.get(Company, company_id) if company_id is not None else None
    if company_id is not None and (company is None or
            (audience == "client" and company.owner_id != user.id)):
        raise not_found("Компания не найдена")
    if audience == "staff" and company is not None and application is None:
        raise ApiError(422, "APPLICATION_REQUIRED", "Для работы с компанией выберите отправленную заявку")
    return Scope(audience, company, application)


def owned_conversation(db: Session, user: User, conversation_id: str) -> tuple[Conversation, Scope]:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.owner_id != user.id or conv.audience != audience_of(user):
        raise not_found("Диалог не найден")
    scope = resolve_scope(db, user, conv.company_id, conv.application_id)
    return conv, scope


def company_context(db: Session, scope: Scope) -> dict:
    if scope.company is None:
        return {"available": False, "reason": "Компания не выбрана"}
    loans = db.scalars(select(ExistingLoan).where(ExistingLoan.company_id == scope.company.id)
                       .order_by(ExistingLoan.id).limit(30)).all()
    return jsonable_encoder({
        "company": applications_service.company_view(scope.company),
        "rating": bureau.rating_view(bureau.get_rating(db, scope.company.id)),
        "rating_history": None, "rating_change_reasons": None,
        "loans": [applications_service.loan_view(loan) for loan in loans],
        "data_source": "Локальные синтетические данные прототипа",
    })


def application_context(db: Session, scope: Scope) -> dict:
    if scope.application is None:
        return {"available": False, "reason": "Заявка не выбрана"}
    view = applications_service.application_view(db, scope.application, for_staff=scope.audience == "staff")
    view["events"] = view.get("events", [])[-15:]
    if scope.audience == "staff":
        # The versioned engine / frozen decision snapshot is the single scoring source.
        view["scoring"] = scoring_view(db, scope.application)
        for key in ("info_requests", "decisions"):
            view[key] = view.get(key, [])[-15:]
        pl = db.get(ApplicationPipeline, scope.application.id)
        view["pipeline"] = {"stage": pl.stage, "assignee_id": pl.assignee_id} if pl else None
    return jsonable_encoder(view)


def source(id_: str, title: str, data: dict, url: str | None = None) -> dict:
    return {"id": id_, "title": title, "kind": "bank_data", "url": url,
            "published_at": utcnow().isoformat(), "is_demo": True,
            "excerpt": json.dumps(jsonable_encoder(data), ensure_ascii=False)[:1200]}


def initial_context(db: Session, scope: Scope, question: str, intent: str) -> tuple[dict, list[dict]]:
    payload = {"products": list(catalog.PRODUCTS.values()), "pricing_rules": pricing.config(),
               "company": company_context(db, scope), "application": application_context(db, scope)}
    sources = [source("products", "Каталог и правила предварительного расчёта", payload["pricing_rules"], "/api/config")]
    if scope.company:
        sources.append(source("rating", "Текущий рейтинг бюро и кредиты компании", payload["company"],
                              f"/api/companies/{scope.company.id}/dashboard" if scope.audience == "client" else None))
    if scope.application:
        prefix = "/api/staff/applications" if scope.audience == "staff" else "/api/applications"
        sources.append(source("application", "Сохранённые данные заявки", payload["application"],
                              f"{prefix}/{scope.application.id}"))
        if scope.audience == "staff":
            sources.append(source("scoring", "Версионированная оценка заявки", payload["application"]["scoring"]))
    matches = knowledge.search(db, scope.audience, question + " " + {
        "rating": "кредитный рейтинг", "advice": "рейтинг анкета сведения", "application_review": "разбор заявки сотрудником",
        "draft_reply": "статусы заявки", "news": "", "chat": "",
    }[intent])
    payload["knowledge"] = matches
    sources += matches
    if intent == "news":
        payload["news"] = knowledge.news(db, scope.audience, question)
        sources += payload["news"]
    return jsonable_encoder(payload), sources


def tool_definitions(scope: Scope) -> list[dict]:
    def tool(name, description, properties=None, required=None):
        return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties or {},
                           "required": required or [], "additionalProperties": False}}}

    tools = [tool("search_knowledge", "Найти правила и ответы в базе знаний для текущей роли.",
                  {"query": {"type": "string", "maxLength": 300}}, ["query"]),
             tool("get_news", "Получить публикации с датами или явно отмеченные демо-материалы.",
                  {"query": {"type": "string", "maxLength": 300}})]
    if scope.company:
        tools += [tool("get_company", "Получить свежие данные только выбранной компании и её рейтинг."),
                  tool("calculate_quote", "Рассчитать предварительную ставку и аннуитетный платёж сервером.",
                       {"amount": {"type": "integer", "minimum": pricing.MIN_AMOUNT, "maximum": 10000000},
                        "term_months": {"type": "integer", "minimum": 6, "maximum": 36},
                        "borrowing_mode": {"type": "string", "enum": ["NEW_CREDIT", "REFINANCE"]}},
                       ["amount", "term_months", "borrowing_mode"])]
    if scope.application:
        tools.append(tool("get_application", "Получить свежие данные выбранной заявки и доступную текущей роли оценку."))
    if scope.audience == "staff" and scope.application is None:
        tools.append(tool("get_queue", "Показать последние 20 отправленных заявок; черновики исключены."))
    return tools


def execute_tool(db: Session, scope: Scope, name: str, arguments: dict) -> tuple[dict, list[dict]]:
    definitions = {t["function"]["name"]: t["function"]["parameters"] for t in tool_definitions(scope)}
    schema = definitions.get(name)
    if schema is None or not isinstance(arguments, dict):
        return {"error": "Инструмент недоступен"}, []
    if set(arguments) - set(schema["properties"]) or set(schema["required"]) - set(arguments):
        return {"error": "Некорректные аргументы инструмента"}, []
    for key, value in arguments.items():
        spec = schema["properties"][key]
        if spec["type"] == "string" and (not isinstance(value, str) or len(value) > spec.get("maxLength", 300)):
            return {"error": "Некорректные аргументы инструмента"}, []
        if spec["type"] == "integer" and (type(value) is not int or not spec["minimum"] <= value <= spec["maximum"]):
            return {"error": "Некорректные аргументы инструмента"}, []
        if "enum" in spec and value not in spec["enum"]:
            return {"error": "Некорректные аргументы инструмента"}, []
    if name in ("search_knowledge", "get_news"):
        items = (knowledge.search(db, scope.audience, arguments["query"]) if name == "search_knowledge"
                 else knowledge.news(db, scope.audience, arguments.get("query", "")))
        return {"items": items}, items
    if name in ("get_company", "get_application"):
        value = company_context(db, scope) if name == "get_company" else application_context(db, scope)
        return value, [source("rating" if name == "get_company" else "application", "Данные банковского сервиса", value)]
    if name == "get_queue":
        rows = db.scalars(select(Application).where(Application.status != Status.DRAFT)
                          .order_by(Application.submitted_at.desc(), Application.id.desc()).limit(20)).all()
        value = jsonable_encoder({"items": [applications_service.brief_view(a) for a in rows], "limit": 20})
        return value, [source("queue", "Последние отправленные заявки", value, "/api/staff/applications")]
    amount, term, mode = arguments["amount"], arguments["term_months"], arguments["borrowing_mode"]
    if err := pricing.term_error(term):
        return {"error": err}, []
    if mode == BorrowingMode.REFINANCE:
        app = scope.application
        if not app or app.borrowing_mode != BorrowingMode.REFINANCE or app.existing_loan is None:
            return {"error": "Сначала выберите заявку на рефинансирование и действующий кредит"}, []
        if amount != app.existing_loan.balance:
            return {"error": "Сумма рефинансирования должна совпадать с остатком выбранного долга"}, []
    elif err := pricing.amount_error(scope.company.legal_form, amount):
        return {"error": err}, []
    rating = bureau.get_rating(db, scope.company.id)
    rate = pricing.preliminary_rate(rating.score if rating else None, term, mode)
    value = {"amount": amount, "term_months": term, "borrowing_mode": mode, "rate": float(rate),
             "monthly_payment": pricing.annuity(amount, rate, term), "rating_based": rating is not None,
             "note": catalog.PRELIMINARY_NOTE}
    return value, [source("quote", "Предварительный расчёт сервером", value)]
