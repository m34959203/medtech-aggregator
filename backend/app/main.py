"""Объединённая Medtech-платформа — API.

Кейс 1 (приём прайсов) + Кейс 2 (агрегатор сравнения) в одном сквозном процессе:
загрузка/автосбор → нормализация к справочнику → витрина сравнения цен.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from .auth import require_admin
from .routers import (
    aggregator, auth, basket, chat, clinics, export, feedback, ingestion, leads, portal, review,
)

app = FastAPI(
    title="Medtech Aggregator API",
    description="Сквозной процесс: прайс клиники → нормализация → сравнение цен для пациента.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Схема создаётся миграциями (entrypoint → python -m app.migrate), а не на старте
# приложения — единый источник правды для схемы.


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(clinics.router)
app.include_router(ingestion.router)
app.include_router(aggregator.router)
app.include_router(chat.router)
app.include_router(export.router, dependencies=[Depends(require_admin)])
app.include_router(feedback.router)
app.include_router(leads.router)
app.include_router(review.router, dependencies=[Depends(require_admin)])
app.include_router(portal.router)
app.include_router(basket.router)
app.include_router(auth.router)
