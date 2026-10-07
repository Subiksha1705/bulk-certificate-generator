from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import SessionLocal
from app.services.storage import PdfStorage


def get_session_factory() -> sessionmaker[Session]:
    """Dependency that provides the session factory for background worker tasks."""
    return SessionLocal


def get_storage() -> PdfStorage:
    """Dependency providing the active PDF storage provider."""
    settings = get_settings()
    return PdfStorage(root_dir=settings.STORAGE_DIR)
