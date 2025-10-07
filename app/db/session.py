from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base

_engine = None
SessionLocal: sessionmaker | None = None


def _ensure_engine() -> None:
    global _engine, SessionLocal
    if _engine is not None and SessionLocal is not None:
        return

    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    _engine = create_engine(
        settings.database_url,
        echo=False,
        future=True,
        connect_args=connect_args,
    )
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    _ensure_engine()
    assert _engine is not None
    Base.metadata.create_all(bind=_engine)


def reset_engine() -> None:
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None


def get_session() -> Session:
    _ensure_engine()
    assert SessionLocal is not None
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

