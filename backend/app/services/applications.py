"""Заявки: пересчёт условий, проверки, переходы статусов и представления для клиента и сотрудника."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog, pricing
from app.core.errors import conflict, not_found
from app.enums import ACTIVE_STATUSES, BorrowingMode, DecisionKind, EventType, ProductId, Role, Status
from app.models import Application, ApplicationEvent, Company, Decision, ExistingLoan, User
from app.simulators import bureau, registry


# ---------- выборки и блокировки ----------

def get_for_client(db: Session, application_id: int, user: User, lock: bool = False) -> Application:
    q = select(Application).where(Application.id == application_id)
    if lock:
        q = q.with_for_update()
    app = db.scalar(q)
    if app is None or app.company.owner_id != user.id:
        raise not_found("Заявка не найдена")
    return app


def get_for_staff(db: Session, application_id: int, lock: bool = False) -> Application:
    q = select(Application).where(Application.id == application_id, Application.status != Status.DRAFT)
    if lock:
        q = q.with_for_update()
    app = db.scalar(q)
    if app is None:
        raise not_found("Заявка не найдена")
    return app


def active_application(db: Session, company_id: int, mode: str) -> Application | None:
    return db.scalar(
        select(Application)
        .where(Application.company_id == company_id, Application.borrowing_mode == mode,
               Application.status.in_(ACTIVE_STATUSES))
        .order_by(Application.id.desc())
    )


def loan_taken_by_other(db: Session, loan_id: int, exclude_id: int) -> bool:
    return db.scalar(
        select(Application.id).where(Application.existing_loan_id == loan_id, Application.id != exclude_id,
                                     Application.status.in_(ACTIVE_STATUSES))
    ) is not None


def owned_loan(db: Session, company_id: int, loan_id: int) -> ExistingLoan:
    loan = db.get(ExistingLoan, loan_id)
    if loan is None or loan.company_id != company_id:
        raise not_found("Кредит не найден")
    return loan


def require_status(app: Application, *allowed: Status) -> None:
    if app.status not in allowed:
        raise conflict("INVALID_STATUS", f"Действие недоступно: заявка в статусе «{catalog.STATUS_LABELS[Status(app.status)]}»")


def add_event(db: Session, app: Application, type_: EventType, actor: User, payload: dict | None = None) -> None:
    db.add(ApplicationEvent(application_id=app.id, type=type_, actor_role=actor.role, actor_name=actor.full_name,
                            payload=payload or {}))


# ---------- расчёт ----------

def recalc(db: Session, app: Application) -> None:
    if app.borrowing_mode == BorrowingMode.REFINANCE and app.existing_loan is not None:
        app.amount = app.existing_loan.balance
    if app.amount and app.term_months:
        rating = bureau.get_rating(db, app.company_id)
        score = rating.score if rating else None
        app.preliminary_rate = pricing.preliminary_rate(score, app.term_months, app.borrowing_mode)
        app.preliminary_payment = pricing.annuity(app.amount, app.preliminary_rate, app.term_months)
        app.rating_based = score is not None
        app.rating_used = score
    else:
        app.preliminary_rate = app.preliminary_payment = app.rating_based = app.rating_used = None


def comparison(app: Application) -> dict | None:
    loan = app.existing_loan
    if app.borrowing_mode != BorrowingMode.REFINANCE or loan is None or app.preliminary_rate is None:
        return None
    return {**pricing.refinance_comparison(loan.rate, loan.next_payment_amount, app.preliminary_rate,
                                           app.preliminary_payment),
            "note": catalog.REFINANCE_COMPARISON_NOTE}


def missing_for_submit(app: Application) -> dict[str, str]:
    missing: dict[str, str] = {}
    if app.borrowing_mode == BorrowingMode.NEW_CREDIT:
        if not app.product_id:
            missing["product_id"] = "Выберите цель и продукт"
        if not app.amount:
            missing["amount"] = "Укажите сумму"
    elif not app.existing_loan_id:
        missing["existing_loan_id"] = "Выберите кредит для рефинансирования"
    if not app.term_months:
        missing["term_months"] = "Укажите срок"
    profile = app.business_profile or {}
    for f in catalog.PROFILE_FIELDS:
        v = profile.get(f["key"])
        if v is None or (isinstance(v, str) and not v.strip()):
            missing[f"business_profile.{f['key']}"] = "Обязательное поле"
    return missing


def merge_profile(app: Application, patch: dict) -> None:
    profile = dict(app.business_profile or {})
    for k, v in patch.items():
        profile[k] = v.strip() if isinstance(v, str) else v
    app.business_profile = profile


# ---------- представления ----------

def company_view(c: Company) -> dict:
    meta = catalog.LEGAL_FORMS[c.legal_form]
    return {
        "id": c.id,
        "name": c.name,
        "legal_form": c.legal_form,
        "legal_form_label": meta["label"],
        "registration_number": c.ogrn,
        "registration_label": meta["registration_label"],
        "max_amount": pricing.MAX_AMOUNT[c.legal_form],
    }


def loan_view(l: ExistingLoan) -> dict:
    return {
        "id": l.id,
        "product_id": l.product_id,
        "name": catalog.PRODUCTS[ProductId(l.product_id)]["name"],
        "original_amount": l.original_amount,
        "balance": l.balance,
        "rate": float(l.rate),
        "next_payment_amount": l.next_payment_amount,
        "next_payment_date": l.next_payment_date,
    }


def _product_name(app: Application) -> str | None:
    return catalog.PRODUCTS[ProductId(app.product_id)]["name"] if app.product_id else None


def brief_view(app: Application) -> dict:
    return {
        "id": app.id,
        "number": app.number,
        "company_id": app.company_id,
        "company_name": app.company.name,
        "borrowing_mode": app.borrowing_mode,
        "borrowing_mode_label": catalog.BORROWING_MODES[BorrowingMode(app.borrowing_mode)]["name"],
        "product_id": app.product_id,
        "product_name": _product_name(app),
        "existing_loan_name": loan_view(app.existing_loan)["name"] if app.existing_loan else None,
        "amount": app.amount,
        "term_months": app.term_months,
        "status": app.status,
        "status_label": catalog.STATUS_LABELS[Status(app.status)],
        "current_step": app.current_step,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
        "submitted_at": app.submitted_at,
    }


def _stage(app: Application) -> dict:
    idx = catalog.STAGE_INDEX[Status(app.status)]
    steps = []
    for i, (key, label) in enumerate(catalog.STAGES):
        if i < idx or (app.status == Status.COMPLETED and i == idx):
            state = "done"
        elif i == idx:
            state = "active"
        else:
            state = "pending"
        steps.append({"key": key, "label": label, "state": state})
    return {"active": catalog.STAGES[idx][0] if idx >= 0 else None, "steps": steps}


def _event_view(e: ApplicationEvent, for_staff: bool) -> dict:
    if e.actor_role == Role.EMPLOYEE:
        actor = e.actor_name if for_staff else "Банк"
    else:
        actor = e.actor_name
    return {
        "id": e.id,
        "type": e.type,
        "label": catalog.EVENT_LABELS[EventType(e.type)],
        "actor": actor,
        "actor_role": e.actor_role,
        "text": (e.payload or {}).get("text"),
        "fields": (e.payload or {}).get("fields"),
        "created_at": e.created_at,
    }


def active_decision(app: Application) -> Decision | None:
    return next((d for d in reversed(app.decisions) if d.is_active), None)


def decision_view(d: Decision, app: Application) -> dict:
    view = {
        "id": d.id,
        "kind": d.kind,
        "kind_label": catalog.DECISION_LABELS[DecisionKind(d.kind)],
        "amount": d.amount,
        "term_months": d.term_months,
        "rate": float(d.rate) if d.rate is not None else None,
        "monthly_payment": d.monthly_payment,
        "comment": d.comment,
        "reason_text": catalog.REJECT_REASONS.get(d.reject_reason_code) if d.reject_reason_code else None,
        "created_at": d.created_at,
        "requested": {
            "amount": app.amount,
            "term_months": app.term_months,
            "rate": float(app.preliminary_rate) if app.preliminary_rate is not None else None,
            "monthly_payment": app.preliminary_payment,
        },
        "changed_fields": [],
        "refinance_remainder": None,
        "refinance_remainder_text": None,
    }
    if d.kind == DecisionKind.COUNTER_OFFER:
        req = view["requested"]
        view["changed_fields"] = [k for k in ("amount", "term_months", "rate") if req[k] != view[k]]
    if d.kind != DecisionKind.REJECTED and app.existing_loan and d.amount is not None and d.amount < app.existing_loan.balance:
        rest = app.existing_loan.balance - d.amount
        view["refinance_remainder"] = rest
        view["refinance_remainder_text"] = f"Оставшуюся часть долга ({pricing.rub(rest)}) нужно погасить по текущему кредиту."
    return view


def client_actions(app: Application) -> list[str]:
    return {
        Status.DRAFT: ["edit", "submit"],
        Status.NEED_INFO: ["info_response"],
        Status.APPROVED: ["accept"],
        Status.COUNTER_OFFER: ["accept", "supplement"],
    }.get(Status(app.status), [])


def application_view(db: Session, app: Application, for_staff: bool = False) -> dict:
    status = Status(app.status)
    profile = {k: (app.business_profile or {}).get(k) for k in catalog.PROFILE_KEYS}
    open_request = next((r for r in reversed(app.info_requests) if r.answered_at is None), None)
    decision = active_decision(app)
    view = {
        **brief_view(app),
        "company": company_view(app.company),
        "existing_loan": loan_view(app.existing_loan) if app.existing_loan else None,
        "preliminary_rate": float(app.preliminary_rate) if app.preliminary_rate is not None else None,
        "preliminary_payment": app.preliminary_payment,
        "rating_based": app.rating_based,
        "rating_note": None if app.rating_based is not False else "расчёт без рейтинга",
        "preliminary_note": catalog.PRELIMINARY_NOTE if status == Status.DRAFT else catalog.FINAL_TERMS_NOTE,
        "comparison": comparison(app),
        "business_profile": profile,
        "next_steps_text": catalog.NEXT_STEPS[status],
        "stage": _stage(app),
        "decided_at": app.decided_at,
        "completed_at": app.completed_at,
        "info_request": (
            {"id": open_request.id, "message": open_request.message,
             "requested_fields": [{"key": k, "label": catalog.PROFILE_LABELS[k]} for k in open_request.requested_fields],
             "created_at": open_request.created_at}
            if status == Status.NEED_INFO and open_request else None
        ),
        "decision": decision_view(decision, app) if decision and status in
        (Status.APPROVED, Status.COUNTER_OFFER, Status.REJECTED, Status.COMPLETED) else None,
        "events": [_event_view(e, for_staff) for e in app.events],
        "available_actions": client_actions(app),
    }
    if for_staff:
        view.update(staff_extras(db, app))
    return view


# ---------- внутренняя оценка (только сотрудник) ----------

def staff_extras(db: Session, app: Application) -> dict:
    rating = bureau.get_rating(db, app.company_id)
    score = rating.score if rating else None
    profile = app.business_profile or {}
    revenue = profile.get("monthly_revenue")
    debts = profile.get("monthly_debt_payments") or 0
    load = (debts + (app.preliminary_payment or 0)) / revenue if revenue else None

    reasons = []
    if score is None:
        rec = "MANUAL"
        reasons.append("Рейтинг бюро недоступен")
    elif load is None:
        rec = "MANUAL"
        reasons.append("Не указана выручка")
    elif score >= 750 and load < 0.5:
        rec = "APPROVE"
        reasons.append("Высокий рейтинг и комфортная долговая нагрузка")
    elif score < 500 or load > 0.8:
        rec = "REJECT"
        if score < 500:
            reasons.append("Низкий рейтинг бюро")
        if load > 0.8:
            reasons.append("Долговая нагрузка выше 80 % выручки")
    else:
        rec = "MANUAL"
        reasons.append("Средние показатели — решение на усмотрение сотрудника")

    profile_missing = [k for k in catalog.PROFILE_KEYS
                       if profile.get(k) is None or (isinstance(profile.get(k), str) and not profile[k].strip())]
    checks = [
        registry.registration_check(app.company.legal_form, app.company.ogrn),
        {
            "key": "credit_history",
            "label": "Кредитная история (симулятор бюро)",
            "status": "UNAVAILABLE" if score is None else ("OK" if score >= 500 else "WARN"),
            "details": catalog.RATING_UNAVAILABLE_TEXT if score is None
            else f"Рейтинг {score} из {pricing.RATING_MAX} — {pricing.rating_band(score)[1]}",
        },
        {
            "key": "profile",
            "label": "Полнота анкеты",
            "status": "OK" if not profile_missing else "WARN",
            "details": "Все поля заполнены" if not profile_missing
            else "Не заполнено: " + ", ".join(catalog.PROFILE_LABELS[k] for k in profile_missing),
        },
        {
            "key": "debt_load",
            "label": "Долговая нагрузка",
            "status": "UNAVAILABLE" if load is None else ("OK" if load < 0.5 else "WARN"),
            "details": "Нет данных о выручке" if load is None
            else f"{round(load * 100)} % выручки уйдёт на платежи по долгам с учётом нового платежа",
        },
    ]
    return {
        "client": {"full_name": app.company.owner.full_name},
        "rating": bureau.rating_view(rating),
        "scoring": {
            "bureau_score": score,
            "debt_load_pct": round(load * 100, 1) if load is not None else None,
            "recommendation": rec,
            "recommendation_label": {"APPROVE": "Одобрить", "REJECT": "Отказать",
                                     "MANUAL": "На усмотрение сотрудника"}[rec],
            "reasons": reasons,
        },
        "checks": checks,
        "info_requests": [
            {"id": r.id, "message": r.message, "requested_fields": r.requested_fields, "created_by": r.created_by,
             "created_at": r.created_at, "answer_text": r.answer_text, "answer_fields": r.answer_fields,
             "answered_at": r.answered_at}
            for r in app.info_requests
        ],
        "decisions": [{**decision_view(d, app), "is_active": d.is_active, "created_by": d.created_by,
                       "reject_reason_code": d.reject_reason_code} for d in app.decisions],
        "staff_actions": ["request_info", "approve", "counter_offer", "reject"] if app.status == Status.IN_REVIEW else [],
    }
