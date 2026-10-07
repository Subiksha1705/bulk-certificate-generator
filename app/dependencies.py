from sqlalchemy.orm import Session, sessionmaker

from app.database import SessionLocal


def get_session_factory() -> sessionmaker[Session]:
    """Dependency that provides the session factory for background worker tasks."""
    return SessionLocal
