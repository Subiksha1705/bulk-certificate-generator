from app.schemas.job import JobCreate, RecipientIn
from app.services.fingerprint import compute_request_hash


def test_fingerprint_determinism_and_recipient_order_invariance() -> None:
    """Verify that fingerprinting is deterministic and insensitive to recipient order."""
    job1 = JobCreate(
        event_name="Python Workshop",
        event_date="2026-10-10",
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        recipients=[
            RecipientIn(name="Subiksha P R", email="subiksha@example.com"),
            RecipientIn(name="Rahul Kumar", email="rahul@example.com"),
        ],
    )

    # Same recipients in reversed order
    job2 = JobCreate(
        event_name="Python Workshop",
        event_date="2026-10-10",
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        recipients=[
            RecipientIn(name="Rahul Kumar", email="rahul@example.com"),
            RecipientIn(name="Subiksha P R", email="subiksha@example.com"),
        ],
    )

    hash1 = compute_request_hash(job1)
    hash2 = compute_request_hash(job2)
    assert len(hash1) == 64
    assert hash1 == hash2


def test_fingerprint_whitespace_and_case_insensitivity() -> None:
    """Verify that case and internal/surrounding whitespace noise do not alter the hash."""
    job1 = JobCreate(
        event_name="Python Workshop",
        event_date="2026-10-10",
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        recipients=[
            RecipientIn(name="Subiksha P R", email="subiksha@example.com"),
        ],
    )

    job2 = JobCreate(
        event_name="  Python    Workshop  ",
        event_date="2026-10-10",
        organization_name="  ABC   Technologies  ",
        authorized_signatory="  Priya   Sharma  ",
        recipients=[
            RecipientIn(name="  SUBIKSHA   P   R  ", email="  SUBIKSHA@EXAMPLE.COM  "),
        ],
    )

    assert compute_request_hash(job1) == compute_request_hash(job2)


def test_fingerprint_changes_on_any_field_modification() -> None:
    """Verify that changing any job or recipient field alters the computed hash."""
    base_payload = {
        "event_name": "Python Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Technologies",
        "authorized_signatory": "Priya Sharma",
        "recipients": [
            RecipientIn(name="Subiksha P R", email="subiksha@example.com"),
        ],
    }
    base_hash = compute_request_hash(JobCreate(**base_payload))

    # 1. Modify event_name
    diff_event = compute_request_hash(JobCreate(**{**base_payload, "event_name": "Go Workshop"}))
    assert diff_event != base_hash

    # 2. Modify event_date
    diff_date = compute_request_hash(JobCreate(**{**base_payload, "event_date": "2026-10-11"}))
    assert diff_date != base_hash

    # 3. Modify organization_name
    diff_org = compute_request_hash(JobCreate(**{**base_payload, "organization_name": "XYZ Corp"}))
    assert diff_org != base_hash

    # 4. Modify authorized_signatory
    diff_sig = compute_request_hash(
        JobCreate(**{**base_payload, "authorized_signatory": "Ananya Roy"})
    )
    assert diff_sig != base_hash

    # 5. Modify recipient name
    diff_rec = compute_request_hash(
        JobCreate(
            **{
                **base_payload,
                "recipients": [RecipientIn(name="Subiksha Sharma", email="subiksha@example.com")],
            }
        )
    )
    assert diff_rec != base_hash
