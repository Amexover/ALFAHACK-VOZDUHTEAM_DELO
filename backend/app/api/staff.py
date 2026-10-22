"""Панель сотрудника банка: очередь, карточка, решения."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import catalog, pricing
from app.core.db import get_db
from app.core.errors import ApiError, validation
from app.core.security import staff_user
from app.enums import BorrowingMode, DecisionKind, EventType, Status
from app.models import Application, Company, Decision, InfoRequest, User, utcnow
from app.schemas import ApproveIn, CounterOfferIn, RejectIn, RequestInfoIn
from app.services import applications as svc
from app.staff_pipeline import deps as pipeline_deps

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/applications")
def queue(status: list[Status] | None = Query(None), q: str | None = None,
          _: User = Depends(pipeline_deps.queue_viewer), db: Session = Depends(get_db)):
    """status можно передать несколько раз; без него — все отправленные заявки."""
    stmt = select(Application).join(Company).where(Application.status != Status.DRAFT)
    if status:
        stmt = stmt.where(Application.status.in_(status))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Application.number.ilike(like) | Company.name.ilike(like))
    apps = db.scalars(stmt.order_by(Application.submitted_at.desc())).all()
    counts = dict(db.execute(select(Application.status, func.count()).where(Application.status != Status.DRAFT)
                             .group_by(Application.status)).all())
    items = [{**svc.brief_view(a), "client_name": a.company.owner.full_name,
              "preliminary_rate": float(a.preliminary_rate) if a.preliminary_rate is not None else None}
             for a in apps]
    return {"items": items, "counts": {s.value: counts.get(s.value, 0) for s in Status if s != Status.DRAFT}}


@router.get("/applications/{application_id}")
def card(application_id: int, _: User = Depends(pipeline_deps.card_viewer), db: Session = Depends(get_db)):
    return svc.application_view(db, svc.get_for_staff(db, application_id), for_staff=True)


@router.get("/reject-reasons")
def reject_reasons(_: User = Depends(staff_user)):
    return {"items": [{"code": k, "text": v} for k, v in catalog.REJECT_REASONS.items()]}


def _decide(db: Session, app: Application, staff: User, kind: DecisionKind, event: EventType, **fields) -> dict:
    for d in app.decisions:
        d.is_active = False
    db.add(Decision(application_id=app.id, kind=kind, created_by=staff.full_name, is_active=True, **fields))
    app.status = {DecisionKind.APPROVED: Status.APPROVED, DecisionKind.COUNTER_OFFER: Status.COUNTER_OFFER,
                  DecisionKind.REJECTED: Status.REJECTED}[kind]
    app.decided_at = utcnow()
    text = fields.get("comment")
    if kind == DecisionKind.REJECTED:
        text = catalog.REJECT_REASONS[fields["reject_reason_code"]] + (f" {text}" if text else "")
    svc.add_event(db, app, event, staff, {"text": text})
    db.commit()
    db.refresh(app)
    return svc.application_view(db, app, for_staff=True)


@router.post("/applications/{application_id}/request-info")
def request_info(application_id: int, body: RequestInfoIn, staff: User = Depends(pipeline_deps.info_requester),
                 db: Session = Depends(get_db)):
    app = svc.get_for_staff(db, application_id, lock=True)
    svc.require_status(app, Status.IN_REVIEW)
    message = body.message.strip()
    if not message:
        raise validation({"message": "Напишите, какие сведения нужны"})
    db.add(InfoRequest(application_id=app.id, message=message, requested_fields=list(dict.fromkeys(body.requested_fields)),
                       created_by=staff.full_name))
    app.status = Status.NEED_INFO
    svc.add_event(db, app, EventType.INFO_REQUESTED, staff, {"text": message, "fields": body.requested_fields})
    db.commit()
    db.refresh(app)
    return svc.application_view(db, app, for_staff=True)


@router.post("/applications/{application_id}/approve")
def approve(application_id: int, body: ApproveIn, staff: User = Depends(pipeline_deps.approver), db: Session = Depends(get_db)):
    """Одобрение подтверждает ровно запрошенные параметры. Другие условия — только через counter-offer."""
    app = svc.get_for_staff(db, application_id, lock=True)
    svc.require_status(app, Status.IN_REVIEW)
    return _decide(db, app, staff, DecisionKind.APPROVED, EventType.APPROVED, amount=app.amount,
                   term_months=app.term_months, rate=app.preliminary_rate, monthly_payment=app.preliminary_payment,
                   comment=(body.comment or "").strip() or None)


@router.post("/applications/{application_id}/counter-offer")
def counter_offer(application_id: int, body: CounterOfferIn, staff: User = Depends(pipeline_deps.counter_offer_maker),
                  db: Session = Depends(get_db)):
    app = svc.get_for_staff(db, application_id, lock=True)
    svc.require_status(app, Status.IN_REVIEW)
    errors = {}
    if app.borrowing_mode == BorrowingMode.REFINANCE:
        balance = app.existing_loan.balance
        if not pricing.MIN_AMOUNT <= body.amount <= balance:
            errors["amount"] = f"Для рефинансирования — от {pricing.rub(pricing.MIN_AMOUNT)} до остатка долга ({pricing.rub(balance)})"
    elif err := pricing.amount_error(app.company.legal_form, body.amount):
        errors["amount"] = err
    if err := pricing.term_error(body.term_months):
        errors["term_months"] = err
    if not body.comment.strip():
        errors["comment"] = "Укажите причину изменения условий"
    if errors:
        raise validation(errors)
    if (body.amount, body.term_months, body.rate) == (app.amount, app.term_months, app.preliminary_rate):
        raise ApiError(422, "SAME_AS_REQUESTED", "Условия совпадают с запрошенными — используйте «Одобрить»")
    return _decide(db, app, staff, DecisionKind.COUNTER_OFFER, EventType.COUNTER_OFFERED, amount=body.amount,
                   term_months=body.term_months, rate=body.rate,
                   monthly_payment=pricing.annuity(body.amount, body.rate, body.term_months),
                   comment=body.comment.strip())


@router.post("/applications/{application_id}/reject")
def reject(application_id: int, body: RejectIn, staff: User = Depends(pipeline_deps.rejecter), db: Session = Depends(get_db)):
    app = svc.get_for_staff(db, application_id, lock=True)
    svc.require_status(app, Status.IN_REVIEW)
    if body.reason_code not in catalog.REJECT_REASONS:
        raise validation({"reason_code": "Выберите причину из списка"})
    return _decide(db, app, staff, DecisionKind.REJECTED, EventType.REJECTED, reject_reason_code=body.reason_code,
                   comment=(body.comment or "").strip() or None)
