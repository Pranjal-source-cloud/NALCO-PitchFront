"""
Database engine / session management.

Uses a central Postgres/Supabase database when DATABASE_URL is configured
(the intended production setup, so multiple Shift Incharges on different
mobile networks all share one source of truth). Falls back to a local
SQLite file purely for local development — this fallback must never be
relied on for the multi-user production deployment.
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from config import DATABASE_URL, LOCAL_SQLITE_PATH
from models import Base

_engine = None
_SessionFactory = None
_backend_label = None


def _build_engine():
    global _backend_label
    if DATABASE_URL:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            # SQLAlchemy 1.4+/2.x requires the postgresql:// scheme
            url = url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
        _backend_label = "Central Cloud Database (Postgres)"
        return engine
    else:
        db_path = os.path.abspath(LOCAL_SQLITE_PATH)
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        _backend_label = "Local SQLite (development only — not for multi-user production)"
        return engine


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_backend_label():
    if _backend_label is None:
        get_engine()
    return _backend_label


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = scoped_session(
            sessionmaker(bind=engine, autoflush=False, autocommit=False)
        )
    return _SessionFactory


def init_db():
    """Create all tables if they do not already exist. Safe to call every run."""
    engine = get_engine()
    Base.metadata.create_all(engine)


@contextmanager
def get_db_session():
    """Context manager yielding a SQLAlchemy session; commits on success, rolls back on error."""
    SessionFactory = get_session_factory()
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
