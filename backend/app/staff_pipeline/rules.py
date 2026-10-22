"""Правила доступа внутри конвейера: кто и что может сделать с заявкой сейчас.

Одно место на все проверки. Ручки отдела и врезки в существующие ручки сотрудника
спрашивают одну и ту же функцию, и по ней же собирается available_actions —
интерфейс не может «знать» больше сервера, а сервер не может разойтись с интерфейсом.

Два режима:

* учётные записи отдела (верификатор, андеррайтер) работают по правилам конвейера;
* учётные записи сотрудников, существовавшие до появления отдела, работают в прежнем
  режиме — их поведение по контракту менять нельзя. Для них из новых правил действует
  только защита от гонки: решение по заявке, которую держит другой сотрудник, не пройдёт.
"""

from app import catalog
from app.core.errors import ApiError, conflict
from app.enums import Status
from app.models import Application
from app.staff_pipeline.enums import (
    DECISION_ACTIONS,
    OPEN_STAGES,
    PIPELINE_STAGE_LABELS,
    STAFF_ROLE_LABELS,
    STAGE_OWNER_ROLE,
    PipelineAction,
    PipelineStage,
    StaffRole,
)
from app.staff_pipeline.models import ApplicationPipeline
from app.staff_pipeline.security import DepartmentMember

# Действия, которые существовали до отдела: у прежних учётных записей они работают как раньше.
LEGACY_ACTIONS = (PipelineAction.REQUEST_INFO, *DECISION_ACTIONS)

# Действия, доступные только по заявке «на рассмотрении».
NEEDS_IN_REVIEW = (PipelineAction.REQUEST_INFO, *DECISION_ACTIONS)

DECISION_IS_UNDERWRITER_JOB = (
    "Решение по заявке принимает андеррайтер. Верификатор передаёт заявку дальше."
)
PASS_IS_VERIFIER_JOB = (
    "Передаёт заявку на андеррайтинг верификатор. Андеррайтер берёт заявку со своего этапа сам."
)


def _stage_forbidden(message: str) -> ApiError:
    return ApiError(403, "STAGE_FORBIDDEN", message)


def _wrong_stage(message: str) -> ApiError:
    return conflict("WRONG_STAGE", message)


def _not_assigned(message: str) -> ApiError:
    return conflict("NOT_ASSIGNED", message)


def _holder_name(pl: ApplicationPipeline) -> str:
    return pl.assignee.full_name if pl.assignee else "другой сотрудник"


def _stage_label(stage: PipelineStage) -> str:
    return PIPELINE_STAGE_LABELS[stage]


def _owner_label(stage: PipelineStage) -> str:
    return STAFF_ROLE_LABELS[STAGE_OWNER_ROLE[stage]]


def _held_by_other(member: DepartmentMember, pl: ApplicationPipeline) -> ApiError | None:
    """Гонка двух сотрудников закрывается для всех без исключений."""
    if pl.assignee_id is not None and pl.assignee_id != member.user.id:
        return conflict("ALREADY_CLAIMED", f"Заявку уже взял в работу {_holder_name(pl)}")
    return None


def _not_mine(member: DepartmentMember, pl: ApplicationPipeline, message: str) -> ApiError | None:
    if pl.assignee_id is None:
        return _not_assigned(message)
    return None


def _own_stage(member: DepartmentMember, stage: PipelineStage, what: str) -> ApiError | None:
    """Этап ведёт та роль, за которой он закреплён."""
    if STAGE_OWNER_ROLE[stage] != member.staff_role:
        return _stage_forbidden(
            f"Заявка на этапе «{_stage_label(stage)}» — {what} {_owner_label(stage).lower()}"
        )
    return None


def check(member: DepartmentMember, app: Application, pl: ApplicationPipeline,
          action: PipelineAction) -> ApiError | None:
    """Ошибка, которую надо вернуть на это действие, или None, если действие разрешено."""
    stage = PipelineStage(pl.stage)
    status = Status(app.status)

    if action == PipelineAction.CANCEL_AUTO_REJECT:
        if member.staff_role != StaffRole.UNDERWRITER:
            return _stage_forbidden("Отменить автоматический отказ может только андеррайтер")
        if not pl.auto_rejected or status != Status.REJECTED:
            return conflict("NOT_AUTO_REJECTED", "У заявки нет действующего автоматического отказа")
        return _held_by_other(member, pl)

    if error := _held_by_other(member, pl):
        return error

    if action in NEEDS_IN_REVIEW and status != Status.IN_REVIEW:
        return conflict("INVALID_STATUS",
                        f"Действие недоступно: заявка в статусе «{catalog.STATUS_LABELS[status]}»")

    if action in LEGACY_ACTIONS and not member.pipeline_enforced:
        return None

    if member.staff_role is None:
        return _stage_forbidden("Роль внутри отдела не назначена — обратитесь к администратору")

    if action == PipelineAction.CLAIM:
        if stage not in OPEN_STAGES:
            return _wrong_stage("Обработка заявки завершена — брать в работу нечего")
        if error := _own_stage(member, stage, "её ведёт"):
            return error
        if pl.assignee_id == member.user.id:
            return conflict("ALREADY_CLAIMED", "Заявка уже у вас в работе")
        return None

    if action == PipelineAction.RELEASE:
        if stage not in OPEN_STAGES:
            return _wrong_stage("Обработка заявки завершена")
        return _not_mine(member, pl, "Заявка не взята в работу — освобождать нечего")

    if action == PipelineAction.REQUEST_INFO:
        if stage not in OPEN_STAGES:
            return _wrong_stage("Обработка заявки завершена")
        if error := _own_stage(member, stage, "сведения запрашивает"):
            return error
        return _not_mine(member, pl, "Сначала возьмите заявку в работу")

    if action == PipelineAction.PASS_TO_UNDERWRITING:
        if member.staff_role != StaffRole.VERIFIER:
            return _stage_forbidden(PASS_IS_VERIFIER_JOB)
        if stage != PipelineStage.VERIFICATION:
            return _wrong_stage("Заявка уже прошла верификацию" if stage == PipelineStage.UNDERWRITING
                                else "Обработка заявки завершена")
        if status not in (Status.IN_REVIEW, Status.NEED_INFO):
            return conflict("INVALID_STATUS",
                            f"Действие недоступно: заявка в статусе «{catalog.STATUS_LABELS[status]}»")
        return _not_mine(member, pl, "Сначала возьмите заявку в работу")

    if action in DECISION_ACTIONS:
        if member.staff_role != StaffRole.UNDERWRITER:
            return _stage_forbidden(DECISION_IS_UNDERWRITER_JOB)
        if stage != PipelineStage.UNDERWRITING:
            return _wrong_stage("Заявка ещё не прошла верификацию" if stage == PipelineStage.VERIFICATION
                                else "Решение по заявке уже вынесено")
        return _not_mine(member, pl, "Сначала возьмите заявку в работу")

    return None


def require(member: DepartmentMember, app: Application, pl: ApplicationPipeline,
            action: PipelineAction) -> None:
    if error := check(member, app, pl, action):
        raise error


def allowed(member: DepartmentMember, app: Application, pl: ApplicationPipeline) -> list[str]:
    """Что этот сотрудник может сделать с этой заявкой прямо сейчас."""
    return [a.value for a in PipelineAction if check(member, app, pl, a) is None]


def claimable(member: DepartmentMember, app: Application, pl: ApplicationPipeline) -> bool:
    return check(member, app, pl, PipelineAction.CLAIM) is None
