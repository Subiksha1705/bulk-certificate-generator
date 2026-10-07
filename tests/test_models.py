import re
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import CERT_ID_REGEX, JOB_ID_REGEX
from app.models import Certificate, CertificateStatus, FailureType, GenerationJob, JobStatus
from app.utils.ids import generate_certificate_id, generate_job_id


def test_job_and_certificates_creation_and_ordering(db_session: Session) -> None:
    """Verify creating a job with certificates and that certificates are ordered by row_number."""
    job_id = generate_job_id()
    job = GenerationJob(
        job_id=job_id,
        event_name="FastAPI Workshop",
        event_date=date(2026, 10, 10),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        status=JobStatus.PENDING,
        total_recipients=3,
        request_hash="hash_123456",
    )

    cert3 = Certificate(
        certificate_id=generate_certificate_id(),
        job_id=job_id,
        row_number=3,
        recipient_name="Charlie Brown",
        recipient_email="charlie@example.com",
        status=CertificateStatus.PENDING,
    )
    cert1 = Certificate(
        certificate_id=generate_certificate_id(),
        job_id=job_id,
        row_number=1,
        recipient_name="Alice Smith",
        recipient_email="alice@example.com",
        status=CertificateStatus.PENDING,
    )
    cert2 = Certificate(
        certificate_id=generate_certificate_id(),
        job_id=job_id,
        row_number=2,
        recipient_name="Bob Jones",
        recipient_email="bob@example.com",
        status=CertificateStatus.PENDING,
    )

    job.certificates = [cert3, cert1, cert2]
    db_session.add(job)
    db_session.commit()

    db_session.expire_all()
    fetched_job = db_session.get(GenerationJob, job_id)
    assert fetched_job is not None
    assert fetched_job.event_name == "FastAPI Workshop"
    assert len(fetched_job.certificates) == 3

    # Relationship must be ordered by row_number: 1, 2, 3
    assert [c.row_number for c in fetched_job.certificates] == [1, 2, 3]
    assert [c.recipient_name for c in fetched_job.certificates] == [
        "Alice Smith",
        "Bob Jones",
        "Charlie Brown",
    ]


def test_unique_request_hash_raises_integrity_error(db_session: Session) -> None:
    """Verify that duplicate request_hash raises an IntegrityError."""
    job1 = GenerationJob(
        job_id=generate_job_id(),
        event_name="Workshop 1",
        event_date=date(2026, 10, 10),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        status=JobStatus.PENDING,
        total_recipients=1,
        request_hash="duplicate_hash_abc",
    )
    db_session.add(job1)
    db_session.commit()

    job2 = GenerationJob(
        job_id=generate_job_id(),
        event_name="Workshop 2",
        event_date=date(2026, 10, 11),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        status=JobStatus.PENDING,
        total_recipients=1,
        request_hash="duplicate_hash_abc",
    )
    db_session.add(job2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_cascade_delete_removes_certificates(db_session: Session) -> None:
    """Verify that deleting a job cascades and deletes associated certificates."""
    job_id = generate_job_id()
    job = GenerationJob(
        job_id=job_id,
        event_name="Workshop 1",
        event_date=date(2026, 10, 10),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        status=JobStatus.PENDING,
        total_recipients=2,
        request_hash="hash_cascade_test",
    )
    cert1 = Certificate(
        certificate_id=generate_certificate_id(),
        job_id=job_id,
        row_number=1,
        recipient_name="Alice Smith",
        status=CertificateStatus.PENDING,
    )
    cert2 = Certificate(
        certificate_id=generate_certificate_id(),
        job_id=job_id,
        row_number=2,
        recipient_name="Bob Jones",
        status=CertificateStatus.FAILED,
        failure_type=FailureType.VALIDATION,
        error_message="Invalid email",
    )
    job.certificates = [cert1, cert2]
    db_session.add(job)
    db_session.commit()

    # Confirm certificates exist
    certs_before = db_session.scalars(select(Certificate).where(Certificate.job_id == job_id)).all()
    assert len(certs_before) == 2

    # Delete the job
    db_session.delete(job)
    db_session.commit()

    # Certificates must be deleted
    certs_after = db_session.scalars(select(Certificate).where(Certificate.job_id == job_id)).all()
    assert len(certs_after) == 0


def test_id_format_regex() -> None:
    """Verify that generated job and certificate IDs match expected regex format."""
    job_id = generate_job_id()
    cert_id = generate_certificate_id()

    assert re.match(JOB_ID_REGEX, job_id) is not None, f"Invalid job ID: {job_id}"
    assert re.match(CERT_ID_REGEX, cert_id) is not None, f"Invalid cert ID: {cert_id}"


def test_ten_thousand_generated_ids_unique_and_exclude_ambiguous_chars() -> None:
    """Generate 10,000 IDs to test uniqueness and absence of ambiguous chars 0, O, 1, I."""
    job_ids = {generate_job_id() for _ in range(10_000)}
    cert_ids = {generate_certificate_id() for _ in range(10_000)}

    assert len(job_ids) == 10_000, "Collision detected in 10,000 job IDs"
    assert len(cert_ids) == 10_000, "Collision detected in 10,000 cert IDs"

    disallowed_chars = set("0O1I")
    for j_id in job_ids:
        # Extract random part after prefix and year
        random_part = j_id.split("-")[-1]
        assert not any(c in disallowed_chars for c in random_part), f"Disallowed char in {j_id}"

    for c_id in cert_ids:
        random_part = c_id.split("-")[-1]
        assert not any(c in disallowed_chars for c in random_part), f"Disallowed char in {c_id}"
