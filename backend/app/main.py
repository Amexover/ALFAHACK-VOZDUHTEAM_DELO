from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import applications, auth, companies, meta, pricing, staff
from app.core.errors import install_error_handlers
from app.core.settings import settings
from app.seed import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Дело — API кредитов для бизнеса",
    description="Демонстрационный бэкенд MVP. Все данные синтетические.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)

for module in (meta, auth, companies, pricing, applications, staff):
    app.include_router(module.router, prefix="/api")
