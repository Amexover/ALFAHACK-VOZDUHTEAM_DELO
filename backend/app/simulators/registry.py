"""Локальный симулятор реестра: проверяется только формат номера, а не существование бизнеса."""

from app.catalog import LEGAL_FORMS
from app.enums import LegalForm


def format_error(legal_form: str, number: str) -> str | None:
    meta = LEGAL_FORMS[LegalForm(legal_form)]
    if not number.isdigit() or len(number) != meta["registration_length"]:
        return f"{meta['registration_label']} должен содержать {meta['registration_length']} цифр"
    return None


def registration_check(legal_form: str, number: str) -> dict:
    ok = format_error(legal_form, number) is None
    return {
        "key": "registration",
        "label": "Регистрация бизнеса",
        "status": "OK" if ok else "FAIL",
        "details": "Формат регистрационного номера подтверждён (симулятор реестра)" if ok else "Неверный формат номера",
    }
