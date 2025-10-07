from __future__ import annotations

from fastapi import FastAPI

from app.db.session import init_db
from app.routers import content_router

app = FastAPI(title="Algoritmika Offline API", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(content_router)

