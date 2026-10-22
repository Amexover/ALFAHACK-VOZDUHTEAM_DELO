"""Тела запросов ручек отдела. Строгие модели — незнакомое поле не проходит молча."""

from pydantic import Field

from app.schemas import Strict


class CommentIn(Strict):
    """Необязательный комментарий сотрудника: попадает во внутреннюю историю обработки."""

    comment: str | None = Field(None, max_length=2000)
