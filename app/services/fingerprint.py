import hashlib
import json

from app.schemas.job import JobCreate
from app.services.validation import normalize_email, normalize_text


def compute_request_hash(job: JobCreate) -> str:
    """
    Compute a deterministic SHA-256 hash for a job creation payload.
    The hash is invariant to recipient order and whitespace/case noise, ensuring
    identical requests are detected for idempotency.
    """
    # Normalize recipients and sort them so order does not affect the hash
    normalized_recipients = sorted(
        [
            normalize_text(r.name).casefold(),
            normalize_email(r.email).casefold(),
        ]
        for r in job.recipients
    )

    canonical_data = {
        "authorized_signatory": normalize_text(job.authorized_signatory),
        "event_date": job.event_date.isoformat(),
        "event_name": normalize_text(job.event_name),
        "organization_name": normalize_text(job.organization_name),
        "recipients": normalized_recipients,
    }

    canonical_json = json.dumps(canonical_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
