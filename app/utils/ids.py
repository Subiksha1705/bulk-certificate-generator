import secrets
from datetime import UTC, datetime

from app.constants import (
    CERT_ID_PREFIX,
    ID_ALPHABET,
    ID_RANDOM_LENGTH,
    JOB_ID_PREFIX,
)


def _generate_random_id(prefix: str) -> str:
    """Generate an unguessable ID in format `{PREFIX}-{YYYY}-{8-CHAR-BASE32}`."""
    year = datetime.now(UTC).year
    random_part = "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_RANDOM_LENGTH))
    return f"{prefix}-{year}-{random_part}"


def generate_job_id() -> str:
    """Generate an unguessable job ID, e.g. `JOB-2026-K7M3Q9XA`."""
    return _generate_random_id(JOB_ID_PREFIX)


def generate_certificate_id() -> str:
    """Generate an unguessable certificate ID, e.g. `CERT-2026-8F3K2Q9X`."""
    return _generate_random_id(CERT_ID_PREFIX)
