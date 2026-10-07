from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app


def test_health_check_success(client: TestClient) -> None:
    """Verify that /health returns 200 and database ok when the database is reachable."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_check_database_failure() -> None:
    """Verify that /health returns 503 when database execution fails."""
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("Connection refused", {}, None)

    def _override_get_db_failure():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db_failure
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/health")
            assert response.status_code == 503
            assert response.json() == {"status": "error", "database": "error"}
    finally:
        app.dependency_overrides.clear()
