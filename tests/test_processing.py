from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.certificate import Certificate
from app.models.enums import CertificateStatus, FailureType, JobStatus
from app.models.job import GenerationJob
from app.services import job_processor
from app.services.certificate_generator import CertificateDataError
from app.services.job_processor import process_job
from app.services.job_service import get_job_by_id
from app.services.storage import PdfStorage


def test_happy_path_processing(client: TestClient, db_session: Session, tmp_path: Path):
    """Happy path: all recipients valid, background tasks complete all certificates to SUCCESS."""
    payload = {
        "event_name": "Cloud Computing Summit",
        "event_date": "2026-10-10",
        "organization_name": "CloudWorks Corp",
        "authorized_signatory": "Dr. Sarah Lin",
        "recipients": [
            {"name": "Alice Wonderland", "email": "alice@example.com"},
            {"name": "Bob Builder", "email": "bob@example.com"},
            {"name": "Charlie Chaplin", "email": "charlie@example.com"},
        ],
    }

    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    job_id = data["job_id"]

    # Background tasks executed by TestClient
    job = get_job_by_id(db_session, job_id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.total_recipients == 3
    assert job.processed_count == 3
    assert job.successful_count == 3
    assert job.failed_count == 0
    assert job.completed_at is not None

    # Check certificates and PDF files
    certs = job.certificates
    assert len(certs) == 3
    for cert in certs:
        assert cert.status == CertificateStatus.SUCCESS
        assert cert.failure_type is None
        assert cert.error_message is None
        assert cert.attempts == 1
        assert cert.file_path is not None
        assert cert.completed_at is not None

        pdf_path = tmp_path / cert.file_path
        assert pdf_path.exists()
        assert pdf_path.read_bytes().startswith(b"%PDF")


def test_progress_numbers_and_percentage(client: TestClient):
    """Validate progress numbers and percentage at completion via GET endpoint."""
    payload = {
        "event_name": "AI Workshop",
        "event_date": "2026-11-01",
        "organization_name": "AI Labs",
        "authorized_signatory": "Prof. Turing",
        "recipients": [
            {"name": "Recipient One", "email": "r1@example.com"},
            {"name": "Recipient Two", "email": "r2@example.com"},
        ],
    }

    resp = client.post("/api/jobs/", json=payload)
    job_id = resp.json()["job_id"]

    get_resp = client.get(f"/api/jobs/{job_id}")
    assert get_resp.status_code == 200
    job_out = get_resp.json()
    assert job_out["status"] == "COMPLETED"
    assert job_out["total"] == 2
    assert job_out["processed"] == 2
    assert job_out["successful"] == 2
    assert job_out["failed"] == 0
    assert job_out["progress_percentage"] == 100.0


def test_individual_generation_failure_isolation(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Monkeypatch generate_certificate_pdf to fail for one specific recipient."""
    original_gen = job_processor.generate_certificate_pdf

    def faulty_generator(data):
        if data.recipient_name == "Faulty User":
            raise RuntimeError("Printer out of ink error")
        return original_gen(data)

    monkeypatch.setattr(job_processor, "generate_certificate_pdf", faulty_generator)

    payload = {
        "event_name": "DevSecOps Masterclass",
        "event_date": "2026-12-05",
        "organization_name": "CyberSec Global",
        "authorized_signatory": "Jane Doe",
        "recipients": [
            {"name": "Good User One", "email": "good1@example.com"},
            {"name": "Faulty User", "email": "faulty@example.com"},
            {"name": "Good User Two", "email": "good2@example.com"},
        ],
    }

    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    job = get_job_by_id(db_session, job_id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert job.total_recipients == 3
    assert job.processed_count == 3
    assert job.successful_count == 2
    assert job.failed_count == 1

    faulty_cert = next(c for c in job.certificates if c.recipient_name == "Faulty User")
    assert faulty_cert.status == CertificateStatus.FAILED
    assert faulty_cert.failure_type == FailureType.GENERATION
    assert "Printer out of ink error" in (faulty_cert.error_message or "")
    assert faulty_cert.file_path is None
    assert faulty_cert.attempts == 1

    good_certs = [c for c in job.certificates if c.recipient_name != "Faulty User"]
    for cert in good_certs:
        assert cert.status == CertificateStatus.SUCCESS
        assert cert.file_path is not None


def test_certificate_data_error_marked_as_validation_failure(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """When build_certificate_data raises CertificateDataError, failure_type is VALIDATION."""
    original_build = job_processor.build_certificate_data

    def faulty_data_builder(cert, job):
        if cert.recipient_name == "Invalid Data User":
            raise CertificateDataError("Custom field validation failed")
        return original_build(cert, job)

    monkeypatch.setattr(job_processor, "build_certificate_data", faulty_data_builder)

    payload = {
        "event_name": "Testing Summit",
        "event_date": "2026-09-01",
        "organization_name": "QA Guild",
        "authorized_signatory": "Chief Inspector",
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "Invalid Data User", "email": "invalid@example.com"},
        ],
    }

    resp = client.post("/api/jobs/", json=payload)
    job_id = resp.json()["job_id"]

    job = get_job_by_id(db_session, job_id)
    assert job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert job.successful_count == 1
    assert job.failed_count == 1

    bad_cert = next(c for c in job.certificates if c.recipient_name == "Invalid Data User")
    assert bad_cert.status == CertificateStatus.FAILED
    assert bad_cert.failure_type == FailureType.VALIDATION
    assert "Custom field validation failed" in (bad_cert.error_message or "")


def test_all_fail_sets_job_failed(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """When all generation attempts fail, job status is FAILED."""

    def failing_generator(data):
        raise RuntimeError("Total GPU crash")

    monkeypatch.setattr(job_processor, "generate_certificate_pdf", failing_generator)

    payload = {
        "event_name": "Crash Test",
        "event_date": "2026-08-01",
        "organization_name": "FailSafe Org",
        "authorized_signatory": "Inspector Clouseau",
        "recipients": [
            {"name": "User Alpha", "email": "alpha@example.com"},
            {"name": "User Beta", "email": "beta@example.com"},
        ],
    }

    resp = client.post("/api/jobs/", json=payload)
    job_id = resp.json()["job_id"]

    job = get_job_by_id(db_session, job_id)
    assert job.status == JobStatus.FAILED
    assert job.successful_count == 0
    assert job.failed_count == 2
    assert job.processed_count == 2


def test_all_invalid_intake_fails_immediately_without_background_task(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """When all recipients fail intake, job is marked FAILED immediately with 0 attempts."""
    processor_called = False

    def mock_process_job(*args, **kwargs):
        nonlocal processor_called
        processor_called = True

    monkeypatch.setattr(job_processor, "process_job", mock_process_job)

    payload = {
        "event_name": "Broken Intake",
        "event_date": "2026-07-07",
        "organization_name": "Broken Org",
        "authorized_signatory": "Signer",
        "recipients": [
            {"name": "", "email": "invalid_email"},
            {"name": "   ", "email": "bad_email_2"},
        ],
    }

    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    assert not processor_called

    job = get_job_by_id(db_session, job_id)
    assert job.status == JobStatus.FAILED
    assert job.total_recipients == 2
    assert job.failed_count == 2
    assert job.successful_count == 0
    assert job.processed_count == 2
    for cert in job.certificates:
        assert cert.status == CertificateStatus.FAILED
        assert cert.failure_type == FailureType.VALIDATION
        assert cert.attempts == 0


def test_mid_job_partial_progress_and_commit(
    db_session: Session,
    test_session_factory: sessionmaker[Session],
    tmp_path: Path,
):
    """Verify that job processor commits progress per certificate."""
    storage = PdfStorage(root_dir=str(tmp_path))

    with test_session_factory() as db:
        # Create job directly
        job = GenerationJob(
            job_id="JOB-2026-TESTPROG",
            event_name="Progress Test",
            event_date=date(2026, 10, 10),
            organization_name="Progress Org",
            authorized_signatory="Progress Signer",
            status=JobStatus.PENDING,
            total_recipients=2,
            request_hash="test_progress_hash_123",
        )
        c1 = Certificate(
            certificate_id="CERT-2026-TEST1111",
            job_id=job.job_id,
            row_number=1,
            recipient_name="First User",
            recipient_email="first@example.com",
            status=CertificateStatus.PENDING,
            attempts=0,
        )
        c2 = Certificate(
            certificate_id="CERT-2026-TEST2222",
            job_id=job.job_id,
            row_number=2,
            recipient_name="Second User",
            recipient_email="second@example.com",
            status=CertificateStatus.PENDING,
            attempts=0,
        )
        job.certificates = [c1, c2]
        db.add(job)
        db.commit()

    # Process job directly using session factory
    process_job(
        job_id="JOB-2026-TESTPROG",
        session_factory=test_session_factory,
        storage=storage,
    )

    with test_session_factory() as db:
        final_job = db.get(GenerationJob, "JOB-2026-TESTPROG")
        assert final_job.status == JobStatus.COMPLETED
        assert final_job.processed_count == 2
        assert final_job.successful_count == 2
