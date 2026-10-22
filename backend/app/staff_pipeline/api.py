"""Ручки отдела сотрудников. Префикс /staff, пути не пересекаются с существующими ручками."""

from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import pricing
from app.api.auth import user_view
from app.core.db import get_db
from app.core.errors import validation
from app.enums import BorrowingMode
from app.models import Application
from app.services import applications as svc
from app.staff_pipeline import pipeline, rules, scoring
from app.staff_pipeline.enums import PipelineAction, PipelineStage
from app.staff_pipeline.models import ApplicationPipeline
from app.staff_pipeline.schemas import CancelAutoRejectIn, CommentIn, ScoringPreviewIn
from app.staff_pipeline.security import DepartmentMember, current_member
from app.staff_pipeline.views import (
    member_view,
    pipeline_view,
    queue_item_view,
    scoring_preview_view,
    scoring_view,
)

router = APIRouter(prefix="/staff", tags=["staff-department"])


class QueueScope(StrEnum):
    """Срезы очереди: свободные, мои в работе, просроченные, все."""

    FREE = "free"
    MINE = "mine"
    OVERDUE = "overdue"
    ALL = "all"


@router.get("/me")
def me(member: DepartmentMember = Depends(current_member)):
    """«Кто я» внутри отдела: общая учётная запись плюс роль, права и нормативы этапов."""
    return {"user": user_view(member.user), "department": member_view(member)}


def _in_scope(scope: QueueScope, member: DepartmentMember, pl: ApplicationPipeline, block: dict) -> bool:
    if scope == QueueScope.ALL:
        return True
    open_stage = pipeline.stage_of(pl) != PipelineStage.DONE
    if scope == QueueScope.FREE:
        return open_stage and pl.assignee_id is None
    if scope == QueueScope.MINE:
        return open_stage and pl.assignee_id == member.user.id
    return bool(block["is_overdue"])


@router.get("/queue")
def queue(scope: QueueScope = QueueScope.FREE, stage: PipelineStage | None = None,
          q: str | None = Query(None, max_length=200),
          member: DepartmentMember = Depends(current_member), db: Session = Depends(get_db)):
    """Очередь отдела со сроками по этапу.

    Сроки считаются в момент запроса: ни планировщика, ни фоновых задач в проекте нет.
    Заявки, попавшие в очередь впервые, здесь же принимаются в конвейер.
    """
    rows = pipeline.ensure_all(db, pipeline.submitted_applications(db))
    db.commit()

    items = [queue_item_view(db, member, app, pl) for app, pl in rows]
    counts = {
        s.value: sum(1 for (_, pl), item in zip(rows, items) if _in_scope(s, member, pl, item["pipeline"]))
        for s in QueueScope
    }

    needle = (q or "").strip().lower()
    selected = [
        item for (_, pl), item in zip(rows, items)
        if _in_scope(scope, member, pl, item["pipeline"])
        and (stage is None or item["pipeline"]["stage"] == stage.value)
        and (not needle or needle in (item["number"] or "").lower() or needle in item["company_name"].lower())
    ]
    # Срочное — выше: сначала просроченные, затем те, у кого меньше времени до срока.
    selected.sort(key=lambda i: (i["pipeline"]["time_left_minutes"] is None,
                                 i["pipeline"]["time_left_minutes"] or 0))
    return {"scope": scope.value, "counts": counts, "items": selected}


def _load(db: Session, application_id: int, lock: bool = True) -> tuple[Application, ApplicationPipeline]:
    app = svc.get_for_staff(db, application_id, lock=lock)
    return app, pipeline.ensure(db, app)


@router.get("/applications/{application_id}/pipeline")
def application_pipeline(application_id: int, member: DepartmentMember = Depends(current_member),
                         db: Session = Depends(get_db)):
    """Внутренняя карточка конвейера и история обработки. Клиенту не отдаётся никогда."""
    app, pl = _load(db, application_id)
    db.commit()
    return pipeline_view(db, member, app, pl)


@router.post("/applications/{application_id}/claim")
def claim(application_id: int, member: DepartmentMember = Depends(current_member),
          db: Session = Depends(get_db)):
    """Взять свободную заявку в работу. Занятую не отдаём — в ответе видно, кто её держит."""
    app, pl = _load(db, application_id, lock=True)
    rules.require(member, app, pl, PipelineAction.CLAIM)
    pipeline.claim(db, member, app, pl)
    db.commit()
    return pipeline_view(db, member, app, pl)


@router.post("/applications/{application_id}/release")
def release(application_id: int, body: CommentIn | None = None,
            member: DepartmentMember = Depends(current_member), db: Session = Depends(get_db)):
    """Вернуть свою заявку в очередь. Попадает во внутреннюю историю обработки."""
    app, pl = _load(db, application_id, lock=True)
    rules.require(member, app, pl, PipelineAction.RELEASE)
    pipeline.release(db, member, app, pl, comment=(body.comment or "").strip() or None if body else None)
    db.commit()
    return pipeline_view(db, member, app, pl)


@router.post("/applications/{application_id}/pass-to-underwriting")
def pass_to_underwriting(application_id: int, body: CommentIn | None = None,
                         member: DepartmentMember = Depends(current_member),
                         db: Session = Depends(get_db)):
    """Передать заявку на этап решения. Решение принимает андеррайтер, не верификатор."""
    app, pl = _load(db, application_id, lock=True)
    rules.require(member, app, pl, PipelineAction.PASS_TO_UNDERWRITING)
    pipeline.pass_to_underwriting(db, member, app, pl,
                                  comment=(body.comment or "").strip() or None if body else None)
    db.commit()
    return pipeline_view(db, member, app, pl)


# ---------- скоринг ----------

@router.post("/applications/{application_id}/cancel-auto-reject")
def cancel_auto_reject(application_id: int, body: CancelAutoRejectIn,
                       member: DepartmentMember = Depends(current_member), db: Session = Depends(get_db)):
    """Отменить автоматический отказ с причиной и взять заявку на андеррайтинг."""
    reason = body.reason.strip()
    if not reason:
        raise validation({"reason": "Укажите причину отмены автоматического отказа"})
    app, pl = _load(db, application_id)
    rules.require(member, app, pl, PipelineAction.CANCEL_AUTO_REJECT)
    decision = pipeline.cancel_auto_reject(db, member, app, pl, reason)
    db.commit()
    # FK обновлён напрямую; relationship мог быть прочитан при построении прав.
    db.expire(pl, ["assignee"])
    return {"application_id": app.id, "status": app.status, "status_label": "На рассмотрении",
            "pipeline": pipeline_view(db, member, app, pl), "reason": reason,
            "cancelled_decision": {"id": decision.id, "kind": decision.kind,
                                   "reject_reason_code": decision.reject_reason_code,
                                   "created_by": decision.created_by, "created_at": decision.created_at,
                                   "is_active": decision.is_active}}

@router.get("/applications/{application_id}/scoring")
def application_scoring(application_id: int, member: DepartmentMember = Depends(current_member),
                        db: Session = Depends(get_db)):
    """Оценка заявки с разбором по правилам, версией набора и историей снимков.

    Клиенту не отдаётся ни в каком виде: рекомендация — совет сотруднику, а не решение.
    """
    app, _ = _load(db, application_id, lock=True)
    # Заявки, принятые в конвейер до появления снимков, получают снимок при первом открытии.
    scoring.ensure_intake_snapshot(db, app)
    db.commit()
    return scoring_view(db, app)


def _preview_errors(app: Application, body: ScoringPreviewIn) -> dict[str, str]:
    """Пересчёт проверяется теми же границами, что и «другие условия»: иначе он бесполезен."""
    errors: dict[str, str] = {}
    if body.amount is not None:
        if app.borrowing_mode == BorrowingMode.REFINANCE and app.existing_loan is not None:
            balance = app.existing_loan.balance
            if not pricing.MIN_AMOUNT <= body.amount <= balance:
                errors["amount"] = (f"Для рефинансирования — от {pricing.rub(pricing.MIN_AMOUNT)} "
                                    f"до остатка долга ({pricing.rub(balance)})")
        elif error := pricing.amount_error(app.company.legal_form, body.amount):
            errors["amount"] = error
    if body.term_months is not None and (error := pricing.term_error(body.term_months)):
        errors["term_months"] = error
    return errors


@router.post("/applications/{application_id}/scoring/preview")
def application_scoring_preview(application_id: int, body: ScoringPreviewIn,
                                member: DepartmentMember = Depends(current_member),
                                db: Session = Depends(get_db)):
    """Как изменится оценка при другой сумме или сроке. Сохранённую заявку не меняет."""
    app = svc.get_for_staff(db, application_id)
    if errors := _preview_errors(app, body):
        raise validation(errors)
    return scoring_preview_view(db, app, body.amount, body.term_months)
