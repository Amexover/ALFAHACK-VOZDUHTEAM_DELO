"""Врезки в существующие ручки сотрудника.

Каждая зависимость заменяет в чужой функции ровно одно: `Depends(staff_user)` на
`Depends(...)` из этого модуля. Тела чужих функций не меняются — это требование
контракта: однострочные правки сигнатур git мержит без конфликта, правки тела — нет.

Что делает зависимость:

1. принимает заявку в конвейер, если она попала к сотруднику впервые;
2. сверяет этап и исполнителя по единым правилам (app.staff_pipeline.rules);
3. записывает переход и запись внутренней истории в ту же транзакцию, что и само действие.

Пункт 3 важен: запись живёт в одной сессии с телом чужой функции. Если тело откажет
(не тот статус, не прошла проверка полей), транзакция не фиксируется и во внутренней
истории не остаётся ничего. Записывается только то, что действительно произошло.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import validation
from app.models import Application, User
from app.schemas import ApproveIn, CounterOfferIn, RejectIn, RequestInfoIn
from app.services import applications as svc
from app.staff_pipeline import pipeline, rules
from app.staff_pipeline.enums import PipelineAction
from app.staff_pipeline.models import ApplicationPipeline
from app.staff_pipeline.security import DepartmentMember, current_member


def _checked(db: Session, member: DepartmentMember, application_id: int,
             action: PipelineAction) -> tuple[Application, ApplicationPipeline]:
    # Та же блокировка, что у claim/release: назначение не может измениться
    # между проверкой прав здесь и фиксацией действия в существующей ручке.
    app = svc.get_for_staff(db, application_id, lock=True)
    pl = pipeline.ensure(db, app)
    rules.require(member, app, pl, action)
    return app, pl


def queue_viewer(member: DepartmentMember = Depends(current_member),
                 db: Session = Depends(get_db)) -> User:
    """Очередь сотрудника: заявки, впервые попавшие в очередь, принимаются в конвейер."""
    pipeline.ensure_all(db, pipeline.submitted_applications(db))
    db.commit()
    return member.user


def card_viewer(application_id: int, member: DepartmentMember = Depends(current_member),
                db: Session = Depends(get_db)) -> User:
    """Карточка заявки: открытие карточки тоже принимает заявку в конвейер."""
    app = svc.get_for_staff(db, application_id, lock=True)
    pipeline.ensure(db, app)
    db.commit()
    return member.user


def info_requester(application_id: int, body: RequestInfoIn,
                   member: DepartmentMember = Depends(current_member),
                   db: Session = Depends(get_db)) -> User:
    """Запрос сведений у клиента: отсчёт норматива этапа останавливается до ответа."""
    app, pl = _checked(db, member, application_id, PipelineAction.REQUEST_INFO)
    pipeline.record_info_request(db, member, app, pl, body.message.strip(), body.requested_fields)
    return member.user


def approver(application_id: int, body: ApproveIn,
             member: DepartmentMember = Depends(current_member),
             db: Session = Depends(get_db)) -> User:
    """Одобрение: причина обязательна, анкета должна быть полной.

    Обе проверки стоят здесь, а не в теле чужой ручки: по контракту в app/api/staff.py
    правятся только сигнатуры. Любая ошибка откатывает транзакцию — ни решение,
    ни запись во внутренней истории не сохраняются.
    """
    app, pl = _checked(db, member, application_id, PipelineAction.APPROVE)
    comment = (body.comment or "").strip()
    if not comment:
        db.rollback()
        raise validation({"comment": "Укажите причину одобрения"})
    svc.require_complete(db, app, message=svc.INCOMPLETE_FOR_STAFF)
    pipeline.record_decision(db, member, app, pl, PipelineAction.APPROVE, comment=comment)
    return member.user


def counter_offer_maker(application_id: int, body: CounterOfferIn,
                        member: DepartmentMember = Depends(current_member),
                        db: Session = Depends(get_db)) -> User:
    app, pl = _checked(db, member, application_id, PipelineAction.COUNTER_OFFER)
    # Предложение других условий — такое же положительное решение: анкета должна быть полной.
    svc.require_complete(db, app, message=svc.INCOMPLETE_FOR_STAFF)
    pipeline.record_decision(db, member, app, pl, PipelineAction.COUNTER_OFFER,
                             comment=body.comment.strip() or None,
                             payload={"amount": body.amount, "term_months": body.term_months,
                                      "rate": float(body.rate)})
    return member.user


def rejecter(application_id: int, body: RejectIn,
             member: DepartmentMember = Depends(current_member),
             db: Session = Depends(get_db)) -> User:
    app, pl = _checked(db, member, application_id, PipelineAction.REJECT)
    pipeline.record_decision(db, member, app, pl, PipelineAction.REJECT,
                             comment=(body.comment or "").strip() or None,
                             payload={"reason_code": body.reason_code})
    return member.user
