"""Единый формат ошибок: {"error": {"code", "message", "fields"}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict[str, str] | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


def not_found(message: str = "Объект не найден") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def validation(fields: dict[str, str], message: str = "Проверьте введённые данные") -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, fields)


def _body(code: str, message: str, fields: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "fields": fields or {}}}


def _pydantic_message(err: dict) -> str:
    t = err.get("type", "")
    ctx = err.get("ctx") or {}
    if t == "missing":
        return "Обязательное поле"
    if t in ("int_parsing", "int_type", "int_from_float"):
        return "Введите целое число"
    if t in ("decimal_parsing", "float_parsing", "decimal_type", "float_type"):
        return "Введите число"
    if t == "greater_than_equal":
        return "Значение не может быть отрицательным" if ctx.get("ge") in (0, "0") else f"Значение должно быть не меньше {ctx.get('ge')}"
    if t == "less_than_equal":
        return f"Значение должно быть не больше {ctx.get('le')}"
    if t == "string_too_short":
        return "Заполните поле"
    if t == "string_too_long":
        return f"Не больше {ctx.get('max_length')} символов"
    if t in ("enum", "literal_error"):
        return "Недопустимое значение"
    if t == "extra_forbidden":
        return "Неизвестное поле"
    if t in ("bool_parsing", "bool_type"):
        return "Ожидается true или false"
    return "Некорректное значение"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message, exc.fields))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            fields.setdefault(".".join(loc) or "_", _pydantic_message(err))
        return JSONResponse(status_code=422, content=_body("VALIDATION_ERROR", "Проверьте введённые данные", fields))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED", 403: "FORBIDDEN"}.get(exc.status_code, f"HTTP_{exc.status_code}")
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail)))
