"""Отдел сотрудников банка: роли внутри отдела, внутренний конвейер, скоринг.

Подключается к приложению двумя вставками в точку сборки (app/main.py):
install_staff_pipeline(app) — ручки отдела, seed_department_on_startup() — демо-данные.
Обе вставки — отдельные строки, существующие строки не меняются.
"""

from fastapi import FastAPI

from app.staff_pipeline import models  # noqa: F401  — регистрирует таблицы отдела в метаданных
from app.staff_pipeline.api import router as staff_pipeline_router
from app.staff_pipeline.seed import seed_department_on_startup

__all__ = ["install_staff_pipeline", "seed_department_on_startup", "staff_pipeline_router"]


def install_staff_pipeline(app: FastAPI) -> None:
    """Регистрирует ручки отдела сотрудников."""
    app.include_router(staff_pipeline_router, prefix="/api")
