from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus, FailureType, JobStatus
from app.models.job import GenerationJob
from app.services import job_processor, job_service
from app.services.job_service import get_job_by_id


def test_demo_failure_switch_and_retry_flow(
    client: TestClient,
    db_session: Session,
):
    """
    Test full demo failure flow:
    1. ENABLE_DEMO_FAILURES=True -> FAILME recipients fail on attempt 1 with GENERATION error.
    2. Job finishes as COMPLETED_WITH_ERRORS (failed: 2, successful: 3).
    3. Call POST /api/jobs/{id}/retry-failed -> retry succeed on attempt 2, job becomes COMPLETED.
    4. Successful certificates are untouched (attempts == 1).
    """
    settings = get_settings()
    settings.ENABLE_DEMO_FAILURES = True

    try:
        payload = {
            "event_name": "Demo Failures Workshop",
            "event_date": "2026-10-10",
            "organization_name": "Demo Tech",
            "authorized_signatory": "Demo Lead",
            "recipients": [
                {"name": "Alice Normal", "email": "alice@example.com"},
                {"name": "FAILME User One", "email": "fail1@example.com"},
                {"name": "Bob Normal", "email": "bob@example.com"},
                {"name": "FAILME User Two", "email": "fail2@example.com"},
                {"name": "Charlie Normal", "email": "charlie@example.com"},
            ],
        }
        create_resp = client.post("/api/jobs/", json=payload)
        assert create_resp.status_code == 202
        job_id = create_resp.json()["job_id"]

        # 1. Verify initial run results
        job = get_job_by_id(db_session, job_id)
        assert job.status == JobStatus.COMPLETED_WITH_ERRORS
        assert job.total_recipients == 5
        assert job.processed_count == 5
        assert job.successful_count == 3
        assert job.failed_count == 2

        # Check normal certs
        normal_certs = [c for c in job.certificates if not c.recipient_name.startswith("FAILME")]
        for c in normal_certs:
            assert c.status == CertificateStatus.SUCCESS
            assert c.attempts == 1

        # Check failed certs
        fail_certs = [c for c in job.certificates if c.recipient_name.startswith("FAILME")]
        for c in fail_certs:
            assert c.status == CertificateStatus.FAILED
            assert c.failure_type == FailureType.GENERATION
            assert c.attempts == 1
            assert "Simulated transient failure (demo)" in (c.error_message or "")

        # 2. Trigger Retry-Failed
        retry_resp = client.post(f"/api/jobs/{job_id}/retry-failed")
        assert retry_resp.status_code == 202
        retry_data = retry_resp.json()
        assert retry_data["job_id"] == job_id
        assert retry_data["retried_count"] == 2
        assert retry_data["skipped_non_retryable"] == 0

        # 3. Verify post-retry results (all completed)
        db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED
        assert job.processed_count == 5
        assert job.successful_count == 5
        assert job.failed_count == 0

        # Verify attempts
        for c in normal_certs:
            db_session.refresh(c)
            assert c.status == CertificateStatus.SUCCESS
            assert c.attempts == 1  # Untouched!

        for c in fail_certs:
            db_session.refresh(c)
            assert c.status == CertificateStatus.SUCCESS
            assert c.attempts == 2  # Succeeded on 2nd attempt

    finally:
        settings.ENABLE_DEMO_FAILURES = False


def test_retry_with_validation_failures_skipped(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Validation failures are skipped and reported in skipped_non_retryable."""
    # Monkeypatch generator to fail for Transient Error
    original_gen = job_processor.generate_certificate_pdf

    def faulty_gen(data):
        if data.recipient_name == "Transient Error":
            raise RuntimeError("Transient DB glitch")
        return original_gen(data)

    monkeypatch.setattr(job_processor, "generate_certificate_pdf", faulty_gen)

    payload = {
        "event_name": "Mixed Failures Workshop",
        "event_date": "2026-10-10",
        "organization_name": "QA Corp",
        "authorized_signatory": "Signer",
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "Transient Error", "email": "transient@example.com"},
            {"name": "", "email": "bad_email"},  # Validation error at intake
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    job = get_job_by_id(db_session, job_id)
    assert job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert job.failed_count == 2
    assert job.successful_count == 1

    # Restore generator so retry succeeds
    monkeypatch.setattr(job_processor, "generate_certificate_pdf", original_gen)

    retry_resp = client.post(f"/api/jobs/{job_id}/retry-failed")
    assert retry_resp.status_code == 202
    data = retry_resp.json()
    assert data["retried_count"] == 1
    assert data["skipped_non_retryable"] == 1

    db_session.refresh(job)
    assert job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert job.successful_count == 2
    assert job.failed_count == 1


def test_retry_on_completed_job_returns_409(client: TestClient):
    """Retrying a COMPLETED job returns 409 Conflict."""
    payload = {
        "event_name": "Perfect Job",
        "event_date": "2026-10-10",
        "organization_name": "Org",
        "authorized_signatory": "Signer",
        "recipients": [{"name": "Good User", "email": "good@example.com"}],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    retry_resp = client.post(f"/api/jobs/{job_id}/retry-failed")
    assert retry_resp.status_code == 409
    assert "nothing to retry" in retry_resp.json()["detail"]


def test_retry_with_only_validation_failures_returns_409(client: TestClient):
    """Retrying a job with only validation failures returns 409 with explanatory message."""
    payload = {
        "event_name": "Only Validation Failures",
        "event_date": "2026-10-10",
        "organization_name": "Org",
        "authorized_signatory": "Signer",
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "", "email": "invalid_email"},
        ],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    retry_resp = client.post(f"/api/jobs/{job_id}/retry-failed")
    assert retry_resp.status_code == 409
    detail = retry_resp.json()["detail"]
    assert "No retryable generation failures found" in detail
    assert "1 validation failure(s) require a corrected resubmission" in detail


def test_still_failing_certificate_stays_failed_with_incremented_attempts(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """If generator still fails on retry, certificate stays FAILED with attempts == 2."""

    def persistent_failure(data):
        raise RuntimeError("Permanent hardware fault")

    monkeypatch.setattr(job_processor, "generate_certificate_pdf", persistent_failure)

    payload = {
        "event_name": "Faulty Job",
        "event_date": "2026-10-10",
        "organization_name": "Org",
        "authorized_signatory": "Signer",
        "recipients": [{"name": "Fail User", "email": "fail@example.com"}],
    }
    create_resp = client.post("/api/jobs/", json=payload)
    job_id = create_resp.json()["job_id"]

    job = get_job_by_id(db_session, job_id)
    assert job.status == JobStatus.FAILED

    # Retry with generator still broken
    retry_resp = client.post(f"/api/jobs/{job_id}/retry-failed")
    assert retry_resp.status_code == 202

    db_session.refresh(job)
    assert job.status == JobStatus.FAILED
    cert = job.certificates[0]
    assert cert.status == CertificateStatus.FAILED
    assert cert.failure_type == FailureType.GENERATION
    assert cert.attempts == 2


def test_retry_unknown_job_returns_404(client: TestClient):
    """Retrying non-existent job returns 404."""
    resp = client.post("/api/jobs/JOB-2026-UNKNOWN999/retry-failed")
    assert resp.status_code == 404


def test_double_retry_concurrency_guard(
    db_session: Session,
):
    """Directly calling retry_failed service while job is PROCESSING raises JobNotRetryableError."""
    job = GenerationJob(
        job_id="JOB-2026-DOUBLEGUARD",
        event_name="Double Retry Test",
        event_date=date(2026, 10, 10),
        organization_name="Double Org",
        authorized_signatory="Double Signer",
        status=JobStatus.COMPLETED_WITH_ERRORS,
        total_recipients=2,
        request_hash="double_guard_hash",
    )
    c1 = Certificate(
        certificate_id="CERT-2026-DG1",
        job_id=job.job_id,
        row_number=1,
        recipient_name="User 1",
        status=CertificateStatus.SUCCESS,
        attempts=1,
    )
    c2 = Certificate(
        certificate_id="CERT-2026-DG2",
        job_id=job.job_id,
        row_number=2,
        recipient_name="User 2",
        status=CertificateStatus.FAILED,
        failure_type=FailureType.GENERATION,
        attempts=1,
    )
    job.certificates = [c1, c2]
    db_session.add(job)
    db_session.commit()

    # First call succeeds
    job_service.retry_failed(db_session, job.job_id)

    # Immediate second call fails with JobNotRetryableError
    with pytest.raises(job_service.JobNotRetryableError):
        job_service.retry_failed(db_session, job.job_id)
