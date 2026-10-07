"""Application constants for Bulk Certificate Generator."""

import re
from datetime import date

# Public ID generation
ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 characters, no 0, O, 1, I
ID_RANDOM_LENGTH = 8
JOB_ID_PREFIX = "JOB"
CERT_ID_PREFIX = "CERT"
JOB_ID_REGEX = r"^JOB-\d{4}-[A-HJ-NP-Z2-9]{8}$"
CERT_ID_REGEX = r"^CERT-\d{4}-[A-HJ-NP-Z2-9]{8}$"

# Length & Range limits (from PRD Section 9)
MIN_EVENT_NAME_LENGTH = 3
MAX_EVENT_NAME_LENGTH = 100

MIN_EVENT_DATE = date(2000, 1, 1)
MAX_EVENT_DATE = date(2100, 12, 31)

MIN_ORGANIZATION_NAME_LENGTH = 2
MAX_ORGANIZATION_NAME_LENGTH = 80

MIN_SIGNATORY_LENGTH = 2
MAX_SIGNATORY_LENGTH = 50

MIN_RECIPIENT_NAME_LENGTH = 2
MAX_RECIPIENT_NAME_LENGTH = 60

MAX_EMAIL_LENGTH = 254
DEFAULT_MAX_RECIPIENTS_PER_JOB = 1000

# Name validation regex:
# Must contain at least one letter (\p{L} via unicodedata or regex).
# Allowed characters: Unicode letters, spaces, hyphens, single quotes, periods.
# No control characters or digits-only.
NAME_ALLOWED_CHARS_PATTERN = re.compile(r"^[\w\s\.\'\-]+$", re.UNICODE)

# Recipient Error Messages (PRD Section 9.2)
MSG_NAME_REQUIRED = "Name is required"
MSG_NAME_LENGTH = f"Name must be {MIN_RECIPIENT_NAME_LENGTH}–{MAX_RECIPIENT_NAME_LENGTH} characters"
MSG_NAME_INVALID_CHARS = "Name contains unsupported characters"
MSG_EMAIL_REQUIRED = "Email is required"
