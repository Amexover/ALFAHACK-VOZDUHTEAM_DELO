"""Тела запросов ручек отдела. Строгие модели — незнакомое поле не проходит молча."""

from pydantic import Field

from app.schemas import Strict


class CommentIn(Strict):
    """Необязательный комментарий сотрудника: попадает во внутреннюю историю обработки."""

    comment: str | None = Field(None, max_length=2000)


class CancelAutoRejectIn(Strict):
    reason: str = Field(min_length=1, max_length=2000)


class ScoringPreviewIn(Strict):
    """Предварительный пересчёт оценки: «а если сумма или срок другие».

    Оба поля необязательны — можно менять только одно. Заявку запрос не меняет.
    """

    amount: int | None = Field(None, ge=0, le=10**12)
    term_months: int | None = Field(None, ge=0, le=1200)
