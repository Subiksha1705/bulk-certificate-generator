from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def get_engine_and_session_factory(database_url: str | None = None):
    """Create database engine and sessionmaker based on the provided or configured URL."""
    url = database_url or get_settings().DATABASE_URL

    if url.startswith("sqlite"):
        engine_kwargs: dict = {
            "connect_args": {"check_same_thread": False},
        }
        if ":memory:" in url or "mode=memory" in url:
            engine_kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **engine_kwargs)
    else:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=5,
        )

    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    return engine, session_factory


engine, SessionLocal = get_engine_and_session_factory()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
