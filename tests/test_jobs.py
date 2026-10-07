from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import CertificateStatus, FailureType
from app.models.job import GenerationJob


def test_create_job_success_and_recipient_isolation(
    client: TestClient, db_session: Session
) -> None:
    """
    Verify POST /api/jobs/ creates a job with 202 Accepted, separates valid (PENDING)
    from invalid (FAILED/VALIDATION) recipients, and persists rows.
    """
    payload = {
        "event_name": "Python Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Technologies",
        "authorized_signatory": "Priya Sharma",
        "recipients": [
            {"name": "Subiksha P R", "email": "subiksha@example.com"},
            {"name": "Rahul Kumar", "email": "rahul@example.com"},
            {"name": "", "email": "abc"},  # Invalid name + invalid email
        ],
    }

    response = client.post("/api/jobs/", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert data["job_id"].startswith("JOB-")
    assert data["status"] == "PENDING"
    assert data["total"] == 3
    assert data["processed"] == 1  # 1 invalid recipient processed at intake
    assert data["successful"] == 0
    assert data["failed"] == 1
    assert data["progress_percentage"] == 33.3
    assert data["idempotent_replay"] is False
    assert data["links"]["self"] == f"/api/jobs/{data['job_id']}"
    assert data["links"]["certificates"] == f"/api/jobs/{data['job_id']}/certificates"

    # Verify database persistence
    job = db_session.get(GenerationJob, data["job_id"])
    assert job is not None
    assert len(job.certificates) == 3

    # Row 1 (valid)
    assert job.certificates[0].row_number == 1
    assert job.certificates[0].recipient_name == "Subiksha P R"
    assert job.certificates[0].status == CertificateStatus.PENDING
    assert job.certificates[0].failure_type is None

    # Row 2 (valid)
    assert job.certificates[1].row_number == 2
    assert job.certificates[1].status == CertificateStatus.PENDING

    # Row 3 (invalid at intake)
    assert job.certificates[2].row_number == 3
    assert job.certificates[2].status == CertificateStatus.FAILED
    assert job.certificates[2].failure_type == FailureType.VALIDATION
    assert "Name is required" in job.certificates[2].error_message
    assert "Invalid email: 'abc'" in job.certificates[2].error_message
    assert job.certificates[2].completed_at is not None


def test_create_job_idempotent_replay(client: TestClient) -> None:
    """Verify that submitting the identical request returns 200 OK with the existing job."""
    payload = {
        "event_name": "FastAPI Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [
            {"name": "Subiksha P R", "email": "subiksha@example.com"},
        ],
    }

    # 1. First submission -> 202 Accepted
    resp1 = client.post("/api/jobs/", json=payload)
    assert resp1.status_code == 202
    data1 = resp1.json()
    assert data1["idempotent_replay"] is False

    # 2. Second submission -> 200 OK with identical job_id
    resp2 = client.post("/api/jobs/", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["idempotent_replay"] is True
    assert data2["job_id"] == data1["job_id"]


def test_create_job_reordered_recipients_idempotency(client: TestClient) -> None:
    """Verify that reordering recipients still triggers idempotent replay."""
    payload1 = {
        "event_name": "Idempotency Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"},
        ],
    }
    payload2 = {
        "event_name": "Idempotency Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [
            {"name": "Bob Jones", "email": "bob@example.com"},
            {"name": "Alice Smith", "email": "alice@example.com"},
        ],
    }

    resp1 = client.post("/api/jobs/", json=payload1)
    assert resp1.status_code == 202
    job_id1 = resp1.json()["job_id"]

    resp2 = client.post("/api/jobs/", json=payload2)
    assert resp2.status_code == 200
    assert resp2.json()["job_id"] == job_id1
    assert resp2.json()["idempotent_replay"] is True


def test_create_job_all_invalid_recipients_fails_immediately(client: TestClient) -> None:
    """Verify that a job with 100% invalid recipients is immediately marked FAILED."""
    payload = {
        "event_name": "Invalid Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [
            {"name": "", "email": "bad1"},
            {"name": "   ", "email": "bad2"},
        ],
    }

    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "FAILED"
    assert data["total"] == 2
    assert data["processed"] == 2
    assert data["successful"] == 0
    assert data["failed"] == 2
    assert data["completed_at"] is not None


def test_get_job_by_id_endpoint(client: TestClient) -> None:
    """Verify GET /api/jobs/{job_id} and 404 handling."""
    payload = {
        "event_name": "Query Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [{"name": "Subiksha", "email": "s@example.com"}],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    get_resp = client.get(f"/api/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["job_id"] == job_id
    assert get_resp.json()["event_name"] == "Query Workshop"

    # Unknown job ID
    unknown_resp = client.get("/api/jobs/JOB-2026-UNKNOWN1")
    assert unknown_resp.status_code == 404


def test_list_job_certificates_endpoint(client: TestClient) -> None:
    """Verify GET /api/jobs/{job_id}/certificates pagination and status filtering."""
    payload = {
        "event_name": "Listing Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [
            {"name": "Subiksha P R", "email": "subiksha@example.com"},
            {"name": "Rahul Kumar", "email": "rahul@example.com"},
            {"name": "", "email": "bad_email"},
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    # 1. List all (3 total)
    list_all = client.get(f"/api/jobs/{job_id}/certificates")
    assert list_all.status_code == 200
    assert list_all.json()["total"] == 3
    assert len(list_all.json()["certificates"]) == 3

    # 2. Filter by status=FAILED (1 match)
    list_failed = client.get(f"/api/jobs/{job_id}/certificates?status=FAILED")
    assert list_failed.status_code == 200
    assert list_failed.json()["total"] == 1
    assert list_failed.json()["certificates"][0]["failure_type"] == "VALIDATION"
    assert list_failed.json()["certificates"][0]["view_url"] is None

    # 3. Filter by status=PENDING (2 matches)
    list_pending = client.get(f"/api/jobs/{job_id}/certificates?status=PENDING")
    assert list_pending.status_code == 200
    assert list_pending.json()["total"] == 2

    # 4. Pagination limit=1
    page1 = client.get(f"/api/jobs/{job_id}/certificates?limit=1&offset=0")
    assert page1.status_code == 200
    assert page1.json()["total"] == 3
    assert len(page1.json()["certificates"]) == 1
    assert page1.json()["certificates"][0]["row_number"] == 1

    # 5. Invalid status filter -> 422
    invalid_status = client.get(f"/api/jobs/{job_id}/certificates?status=NON_EXISTENT")
    assert invalid_status.status_code == 422

    # 6. Unknown job ID -> 404
    unknown_job = client.get("/api/jobs/JOB-2026-NOTFOUND9/certificates")
    assert unknown_job.status_code == 404


def test_create_job_422_structural_errors(client: TestClient) -> None:
    """Verify 422 responses for structural request errors."""
    valid_base = {
        "event_name": "Valid Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [{"name": "Subiksha", "email": "s@example.com"}],
    }

    # Empty recipients
    resp = client.post("/api/jobs/", json={**valid_base, "recipients": []})
    assert resp.status_code == 422

    # Extra forbidden field
    resp = client.post("/api/jobs/", json={**valid_base, "extra_field": "disallowed"})
    assert resp.status_code == 422

    # Invalid ISO date
    resp = client.post("/api/jobs/", json={**valid_base, "event_date": "not-a-date"})
    assert resp.status_code == 422
