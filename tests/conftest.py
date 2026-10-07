import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.config import get_settings
from app.database import Base, get_db
from app.dependencies import get_session_factory
from app.main import app


@pytest.fixture(scope="session")
def test_engine():
    """Create test DB engine (PostgreSQL if TEST_DATABASE_URL is set, else SQLite memory)."""
    test_db_url = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    if test_db_url.startswith("sqlite"):
        return create_engine(
            test_db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(test_db_url, pool_pre_ping=True)


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Session factory bound to the test engine."""
    return sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@pytest.fixture
def db_session(test_engine, test_session_factory) -> Generator[Session, None, None]:
    """Provide a clean database session per test with isolated schema."""
    Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db_session, test_session_factory, tmp_path) -> Generator[TestClient, None, None]:
    """TestClient fixture overriding get_db, get_session_factory, and STORAGE_DIR."""
    settings = get_settings()
    original_storage = settings.STORAGE_DIR
    settings.STORAGE_DIR = str(tmp_path)

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def _override_session_factory():
        return test_session_factory

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = _override_session_factory

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    settings.STORAGE_DIR = original_storage
