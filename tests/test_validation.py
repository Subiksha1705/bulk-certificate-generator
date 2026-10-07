from datetime import date

import pydantic
import pytest

from app.constants import (
    MSG_EMAIL_REQUIRED,
    MSG_NAME_INVALID_CHARS,
    MSG_NAME_LENGTH,
    MSG_NAME_REQUIRED,
)
from app.schemas.job import JobCreate
from app.services.validation import (
    normalize_email,
    normalize_text,
    validate_recipient,
    validate_recipients,
)


def test_normalize_helpers() -> None:
    """Verify whitespace stripping and internal space collapsing."""
    assert normalize_text(None) == ""
    assert normalize_text("   ") == ""
    assert normalize_text("  Subiksha   P   R  ") == "Subiksha P R"
    assert normalize_email(None) == ""
    assert normalize_email("   subiksha@example.com   ") == "subiksha@example.com"


@pytest.mark.parametrize(
    "name,email,expected_errors",
    [
        # Name required
        (None, "user@example.com", [MSG_NAME_REQUIRED]),
        ("", "user@example.com", [MSG_NAME_REQUIRED]),
        ("   ", "user@example.com", [MSG_NAME_REQUIRED]),
        # Name lengths
        ("A", "user@example.com", [MSG_NAME_LENGTH]),
        ("A" * 61, "user@example.com", [MSG_NAME_LENGTH]),
        # Name character validation
        ("12345", "user@example.com", [MSG_NAME_INVALID_CHARS]),
        ("User123", "user@example.com", [MSG_NAME_INVALID_CHARS]),
        ("Subiksha 😊", "user@example.com", [MSG_NAME_INVALID_CHARS]),
        ("Subiksha @ Work", "user@example.com", [MSG_NAME_INVALID_CHARS]),
        # Valid special characters
        ("D'Souza", "user@example.com", []),
        ("José Silva", "user@example.com", []),
        ("Mary-Ann Watson", "user@example.com", []),
        ("Dr. Subiksha P. R.", "user@example.com", []),
        # Email required
        ("Subiksha", None, [MSG_EMAIL_REQUIRED]),
        ("Subiksha", "", [MSG_EMAIL_REQUIRED]),
        ("Subiksha", "   ", [MSG_EMAIL_REQUIRED]),
        # Email invalid format
        ("Subiksha", "abc", ["Invalid email: 'abc'"]),
        ("Subiksha", "a@b", ["Invalid email: 'a@b'"]),
        ("Subiksha", "user@", ["Invalid email: 'user@'"]),
        ("Subiksha", "@example.com", ["Invalid email: '@example.com'"]),
        ("Subiksha", "a" * 250 + "@example.com", [f"Invalid email: '{'a' * 250}@example.com'"]),
        # Multiple errors combined
        ("", "bad_email", [MSG_NAME_REQUIRED, "Invalid email: 'bad_email'"]),
    ],
)
def test_validate_recipient_table(
    name: str | None, email: str | None, expected_errors: list[str]
) -> None:
    """Table-driven test verifying individual recipient validation rules."""
    errors = validate_recipient(name, email)
    assert errors == expected_errors


def test_validate_recipients_duplicate_detection() -> None:
    """Verify duplicate row detection across batch items with case insensitivity."""
    items = [
        {"name": "Subiksha P R", "email": "subiksha@example.com"},
        {"name": "Rahul Kumar", "email": "rahul@example.com"},
        {"name": "subiksha p r", "email": "SUBIKSHA@EXAMPLE.COM"},  # duplicate of row 1
        {"name": "", "email": "invalid"},
    ]

    checks = validate_recipients(items)
    assert len(checks) == 4

    assert checks[0].is_valid is True
    assert checks[0].errors == []

    assert checks[1].is_valid is True
    assert checks[1].errors == []

    assert checks[2].is_valid is False
    assert "Duplicate of row 1" in checks[2].errors

    assert checks[3].is_valid is False
    assert MSG_NAME_REQUIRED in checks[3].errors
    assert "Invalid email: 'invalid'" in checks[3].errors
    assert checks[3].error_message == f"{MSG_NAME_REQUIRED}; Invalid email: 'invalid'"


def test_job_create_schema_valid() -> None:
    """Verify valid JobCreate schema instantiation."""
    payload = {
        "event_name": "  Python   Masterclass  ",
        "event_date": "2026-10-10",
        "organization_name": "  ABC Technologies  ",
        "authorized_signatory": "  Priya Sharma  ",
        "recipients": [
            {"name": "Subiksha P R", "email": "subiksha@example.com"},
        ],
    }
    job = JobCreate.model_validate(payload)
    assert job.event_name == "Python Masterclass"
    assert job.organization_name == "ABC Technologies"
    assert job.authorized_signatory == "Priya Sharma"
    assert job.event_date == date(2026, 10, 10)


def test_job_create_schema_bounds_and_rejections() -> None:
    """Verify JobCreate field bounds, date ranges, and extra field rejection."""
    valid_base = {
        "event_name": "Python Workshop",
        "event_date": "2026-10-10",
        "organization_name": "ABC Tech",
        "authorized_signatory": "Priya Sharma",
        "recipients": [{"name": "Subiksha", "email": "s@example.com"}],
    }

    # 1. Event name length bounds (3..100)
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "event_name": "AB"})
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "event_name": "A" * 101})

    # 2. Organization name length bounds (2..80)
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "organization_name": "A"})
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "organization_name": "A" * 81})

    # 3. Signatory length bounds (2..50)
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "authorized_signatory": "A"})
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "authorized_signatory": "A" * 51})

    # 4. Event date bounds (2000-01-01 .. 2100-12-31)
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "event_date": "1999-12-31"})
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "event_date": "2101-01-01"})
    # Future date is permitted
    future_job = JobCreate.model_validate({**valid_base, "event_date": "2030-05-15"})
    assert future_job.event_date == date(2030, 5, 15)

    # 5. Empty recipients list
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "recipients": []})

    # 6. Extra fields forbidden (catches typos like 'date' instead of 'event_date')
    with pytest.raises(pydantic.ValidationError):
        JobCreate.model_validate({**valid_base, "date": "2026-10-10"})
