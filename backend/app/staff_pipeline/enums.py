"""Внутренние перечисления отдела сотрудников.

Внешний контракт не трогаем: app.enums.Role и app.enums.Status остаются как есть.
Всё, что здесь описано, живёт только внутри ручек сотрудника и клиенту не отдаётся.
"""

from enum import StrEnum


class StaffRole(StrEnum):
    """Роль внутри отдела. Общая роль пользователя при этом остаётся EMPLOYEE."""

    VERIFIER = "VERIFIER"
    UNDERWRITER = "UNDERWRITER"


class PipelineStage(StrEnum):
    """Внутренний этап обработки заявки. С клиентскими статусами не связан напрямую."""

    VERIFICATION = "VERIFICATION"
    UNDERWRITING = "UNDERWRITING"
    DONE = "DONE"


class PipelineEventType(StrEnum):
    """Типы записей внутренней истории обработки.

    Отдельный перечень, потому что писать новые типы в общую историю заявки нельзя:
    подписи событий у клиента берутся из словаря без защиты и незнакомый тип роняет страницу.
    """

    ACCEPTED_TO_PIPELINE = "ACCEPTED_TO_PIPELINE"
    CLAIMED = "CLAIMED"
    RELEASED = "RELEASED"
    INFO_REQUESTED = "INFO_REQUESTED"
    INFO_PROVIDED = "INFO_PROVIDED"
    PASSED_TO_UNDERWRITING = "PASSED_TO_UNDERWRITING"
    RETURNED_TO_VERIFICATION = "RETURNED_TO_VERIFICATION"
    DECISION_MADE = "DECISION_MADE"
    AUTO_REJECTED = "AUTO_REJECTED"
    AUTO_REJECT_CANCELLED = "AUTO_REJECT_CANCELLED"


class PipelineAction(StrEnum):
    """Действия сотрудника над заявкой внутри конвейера.

    Значения совпадают с тем, что уходит в available_actions и claimable:
    интерфейс рисует кнопки по тому же перечню, по которому сервер проверяет права.
    """

    CLAIM = "claim"
    RELEASE = "release"
    REQUEST_INFO = "request_info"
    PASS_TO_UNDERWRITING = "pass_to_underwriting"
    APPROVE = "approve"
    COUNTER_OFFER = "counter_offer"
    REJECT = "reject"
    CANCEL_AUTO_REJECT = "cancel_auto_reject"


class SnapshotReason(StrEnum):
    """Зачем сохранён снимок оценки."""

    ON_INTAKE = "ON_INTAKE"
    ON_DECISION = "ON_DECISION"


STAFF_ROLE_LABELS = {
    StaffRole.VERIFIER: "Верификатор",
    StaffRole.UNDERWRITER: "Андеррайтер",
}

PIPELINE_STAGE_LABELS = {
    PipelineStage.VERIFICATION: "Проверка сведений",
    PipelineStage.UNDERWRITING: "Принятие решения",
    PipelineStage.DONE: "Обработка завершена",
}

PIPELINE_EVENT_LABELS = {
    PipelineEventType.ACCEPTED_TO_PIPELINE: "Заявка принята в обработку",
    PipelineEventType.CLAIMED: "Заявка взята в работу",
    PipelineEventType.RELEASED: "Заявка освобождена",
    PipelineEventType.INFO_REQUESTED: "Запрошены сведения у клиента",
    PipelineEventType.INFO_PROVIDED: "Клиент прислал сведения",
    PipelineEventType.PASSED_TO_UNDERWRITING: "Передана на андеррайтинг",
    PipelineEventType.RETURNED_TO_VERIFICATION: "Возвращена на проверку сведений",
    PipelineEventType.DECISION_MADE: "Вынесено решение",
    PipelineEventType.AUTO_REJECTED: "Автоматический отказ по правилам банка",
    PipelineEventType.AUTO_REJECT_CANCELLED: "Автоматический отказ отменён",
}

PIPELINE_ACTION_LABELS = {
    PipelineAction.CLAIM: "Взять в работу",
    PipelineAction.RELEASE: "Освободить",
    PipelineAction.REQUEST_INFO: "Запросить сведения",
    PipelineAction.PASS_TO_UNDERWRITING: "Передать на андеррайтинг",
    PipelineAction.APPROVE: "Одобрить",
    PipelineAction.COUNTER_OFFER: "Предложить другие условия",
    PipelineAction.REJECT: "Отказать",
    PipelineAction.CANCEL_AUTO_REJECT: "Отменить автоматический отказ",
}

# Решения — только андеррайтера; верификатор передаёт заявку дальше.
DECISION_ACTIONS = (PipelineAction.APPROVE, PipelineAction.COUNTER_OFFER, PipelineAction.REJECT)

# Этапы, на которых заявка ещё в работе отдела.
OPEN_STAGES = (PipelineStage.VERIFICATION, PipelineStage.UNDERWRITING)

# Норматив времени на этап. Считается в момент запроса, без планировщика и фоновых задач.
STAGE_LIMIT_HOURS = {
    PipelineStage.VERIFICATION: 4,
    PipelineStage.UNDERWRITING: 24,
}

# Какая роль закрывает какой этап.
STAGE_OWNER_ROLE = {
    PipelineStage.VERIFICATION: StaffRole.VERIFIER,
    PipelineStage.UNDERWRITING: StaffRole.UNDERWRITER,
}
