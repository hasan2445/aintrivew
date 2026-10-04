import logging

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import DATABASE_URL, IS_PRODUCTION

logger = logging.getLogger(__name__)


def _build_engine():
    """Create the SQLAlchemy engine, verifying connectivity up front.

    ``create_engine`` is lazy, so the previous try/except around it never caught
    a bad DATABASE_URL. We open a real connection here instead. In production a
    failure is fatal; in development we fall back to a shared in-memory SQLite
    database so the app is still runnable offline.
    """
    kwargs = {"pool_pre_ping": True, "future": True}
    if DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in DATABASE_URL:
            kwargs["poolclass"] = StaticPool
            kwargs.pop("pool_pre_ping", None)

    engine = create_engine(DATABASE_URL, **kwargs)
    try:
        with engine.connect():
            pass
        return engine
    except SQLAlchemyError as exc:
        if IS_PRODUCTION:
            raise RuntimeError(
                f"Could not connect to DATABASE_URL in production: {exc}"
            ) from exc
        logger.warning(
            "Failed to connect to DATABASE_URL (%s); falling back to in-memory SQLite. "
            "All data will be lost on restart.",
            exc,
        )
        return create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )


engine = _build_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
        # Roll back any transaction the request left open without committing,
        # so a pooled connection is never handed on mid-transaction.
        db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
