"""Клиентская часть заявки: черновик → отправка → ответ на запрос → принятие или дополнение."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import pricing
from app.api.companies import owned_company
from app.core.db import get_db
from app.core.errors import conflict, validation
from app.core.security import client_user
from app.enums import BorrowingMode, EventType, Status
from app.models import Application, Company, ExistingLoan, InfoRequest, User, utcnow
from app.schemas import ClientAnswerIn, DraftCreateIn, DraftPatchIn, SubmitIn
from app.services import applications as svc

router = APIRouter(tags=["applications"])


@router.post("/companies/{company_id}/applications")
def create_or_resume(body: DraftCreateIn, response: Response, company: Company = Depends(owned_company),
                     db: Session = Depends(get_db)):
    """Возвращает активную заявку этого способа займа (200) или создаёт черновик (201)."""
    existing = svc.active_application(db, company.id, body.borrowing_mode)
    if existing:
        return svc.application_view(db, existing)
    app = Application(company_id=company.id, borrowing_mode=body.borrowing_mode, term_months=pricing.DEFAULT_TERM,
                      business_profile={})
    if body.borrowing_mode == BorrowingMode.REFINANCE:
        has_loans = db.scalar(select(ExistingLoan.id).where(ExistingLoan.company_id == company.id))
        if not has_loans:
            raise conflict("NO_LOANS_TO_REFINANCE", "У этой компании нет действующих кредитов для рефинансирования")
    else:
        app.amount = min(pricing.DEFAULT_AMOUNT, pricing.MAX_AMOUNT[company.legal_form])
    db.add(app)
    try:
        db.flush()
        db.refresh(app)
        svc.recalc(db, app)
        db.commit()
    except IntegrityError:
        # Второй одновременный запрос (две вкладки, двойной клик) упирается в уникальный
        # индекс активной заявки. Правильный ответ — уже созданный черновик, а не второй.
        db.rollback()
        existing = svc.active_application(db, company.id, body.borrowing_mode)
        if existing is None:
            raise
        return svc.application_view(db, existing)
    response.status_code = 201
    return svc.application_view(db, app)


@router.get("/applications/{application_id}")
def get_application(application_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)):
    return svc.application_view(db, svc.get_for_client(db, application_id, user))


@router.patch("/applications/{application_id}")
def update_draft(application_id: int, body: DraftPatchIn, user: User = Depends(client_user),
                 db: Session = Depends(get_db)):
    app = svc.get_for_client(db, application_id, user, lock=True)
    svc.require_status(app, Status.DRAFT)
    sent = body.model_fields_set
    is_refi = app.borrowing_mode == BorrowingMode.REFINANCE
    errors: dict[str, str] = {}

    if "amount" in sent and body.amount is not None:
        if is_refi:
            errors["amount"] = "Сумма рефинансирования равна остатку долга и не меняется"
        elif err := pricing.amount_error(app.company.legal_form, body.amount):
            errors["amount"] = err
    if "term_months" in sent and body.term_months is not None:
        if err := pricing.term_error(body.term_months):
            errors["term_months"] = err
    if "product_id" in sent and body.product_id is not None and is_refi:
        errors["product_id"] = "Для рефинансирования продукт не выбирается"
    loan = None
    if "existing_loan_id" in sent and body.existing_loan_id is not None:
        if not is_refi:
            errors["existing_loan_id"] = "Кредит выбирается только при рефинансировании"
        else:
            loan = svc.owned_loan(db, app.company_id, body.existing_loan_id)
            if svc.loan_taken_by_other(db, loan.id, app.id):
                raise conflict("LOAN_ALREADY_IN_APPLICATION", "По этому кредиту уже есть активная заявка")
    if errors:
        raise validation(errors)

    if "amount" in sent and body.amount is not None:
        app.amount = body.amount
    if "term_months" in sent and body.term_months is not None:
        app.term_months = body.term_months
    if "product_id" in sent and body.product_id is not None:
        app.product_id = body.product_id
    if loan is not None:
        app.existing_loan_id = loan.id
        app.existing_loan = loan
    if body.business_profile is not None:
        svc.merge_profile(app, body.business_profile.model_dump(exclude_unset=True))
    if "current_step" in sent:
        app.current_step = body.current_step
    svc.recalc(db, app)
    db.commit()
    return svc.application_view(db, app)


@router.post("/applications/{application_id}/submit")
def submit(application_id: int, body: SubmitIn, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = svc.get_for_client(db, application_id, user, lock=True)
    if app.status != Status.DRAFT:
        raise conflict("ALREADY_SUBMITTED", "Заявка уже отправлена")
    missing = svc.missing_for_submit(app)
    if not body.confirm_data:
        missing["confirm_data"] = "Подтвердите достоверность данных"
    if app.borrowing_mode == BorrowingMode.NEW_CREDIT and app.amount:
        if err := pricing.amount_error(app.company.legal_form, app.amount):
            missing["amount"] = err
    if missing:
        raise validation(missing, "Заявка заполнена не полностью")
    if app.existing_loan_id and svc.loan_taken_by_other(db, app.existing_loan_id, app.id):
        raise conflict("LOAN_ALREADY_IN_APPLICATION", "По этому кредиту уже есть активная заявка")

    svc.recalc(db, app)
    now = utcnow()
    app.status = Status.IN_REVIEW
    app.submitted_at = now
    app.number = f"D-{now.year}-{app.id:06d}"
    app.current_step = None
    svc.add_event(db, app, EventType.SUBMITTED, user)
    db.commit()
    db.refresh(app)
    return svc.application_view(db, app)


@router.post("/applications/{application_id}/info-response")
def info_response(application_id: int, body: ClientAnswerIn, user: User = Depends(client_user),
                  db: Session = Depends(get_db)):
    app = svc.get_for_client(db, application_id, user, lock=True)
    svc.require_status(app, Status.NEED_INFO)
    request: InfoRequest | None = next((r for r in reversed(app.info_requests) if r.answered_at is None), None)
    if request is None:
        raise conflict("NO_OPEN_REQUEST", "Нет открытого запроса сведений")
    fields = body.fields.model_dump(exclude_unset=True)
    errors = {}
    if not body.answer_text.strip():
        errors["answer_text"] = "Напишите ответ"
    for key in request.requested_fields:
        v = fields.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            errors[f"fields.{key}"] = "Обязательное поле"
    if errors:
        raise validation(errors)

    request.answer_text = body.answer_text.strip()
    request.answer_fields = fields
    request.answered_at = utcnow()
    svc.merge_profile(app, fields)
    # Ответ не должен оставить анкету неполной: проверяем её целиком, а не только спрошенные поля.
    svc.require_complete(db, app, prefix="fields")
    svc.recalc(db, app)
    app.status = Status.IN_REVIEW
    svc.add_event(db, app, EventType.INFO_PROVIDED, user, {"text": request.answer_text, "fields": fields})
    db.commit()
    db.refresh(app)
    return svc.application_view(db, app)


@router.post("/applications/{application_id}/accept")
def accept(application_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = svc.get_for_client(db, application_id, user, lock=True)
    if app.status == Status.COMPLETED:
        raise conflict("ALREADY_ACCEPTED", "Условия уже приняты")
    svc.require_status(app, Status.APPROVED, Status.COUNTER_OFFER)
    app.status = Status.COMPLETED
    app.completed_at = utcnow()
    svc.add_event(db, app, EventType.ACCEPTED, user)
    db.commit()
    db.refresh(app)
    return svc.application_view(db, app)


@router.post("/applications/{application_id}/supplement")
def supplement(application_id: int, body: ClientAnswerIn, user: User = Depends(client_user),
               db: Session = Depends(get_db)):
    """«Вернуться к заявке» при других условиях: клиент дополняет сведения, предложение аннулируется."""
    app = svc.get_for_client(db, application_id, user, lock=True)
    svc.require_status(app, Status.COUNTER_OFFER)
    if not body.answer_text.strip():
        raise validation({"answer_text": "Напишите, что хотите дополнить"})
    fields = body.fields.model_dump(exclude_unset=True)
    for d in app.decisions:
        d.is_active = False
    svc.merge_profile(app, fields)
    svc.require_complete(db, app, prefix="fields")
    svc.recalc(db, app)
    app.status = Status.IN_REVIEW
    app.decided_at = None
    svc.add_event(db, app, EventType.SUPPLEMENTED, user, {"text": body.answer_text.strip(), "fields": fields})
    db.commit()
    db.refresh(app)
    return svc.application_view(db, app)
