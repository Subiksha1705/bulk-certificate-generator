import re
from dataclasses import dataclass
from typing import Any

import email_validator

from app.constants import (
    MAX_EMAIL_LENGTH,
    MAX_RECIPIENT_NAME_LENGTH,
    MIN_RECIPIENT_NAME_LENGTH,
    MSG_EMAIL_REQUIRED,
    MSG_NAME_INVALID_CHARS,
    MSG_NAME_LENGTH,
    MSG_NAME_REQUIRED,
)


def normalize_text(text: str | None) -> str:
    """Strip leading/trailing whitespace and collapse internal whitespace to single spaces."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def normalize_email(email: str | None) -> str:
    """Trim whitespace around email addresses."""
    if email is None:
        return ""
    return email.strip()


def is_valid_name_chars(name: str) -> bool:
    """
    Validate that name contains at least one letter, and all characters are
    letters (including Unicode accents), spaces, periods, apostrophes, or hyphens.
    """
    has_letter = False
    for char in name:
        if char.isalpha():
            has_letter = True
        elif char in (" ", ".", "'", "-"):
            continue
        else:
            return False
    return has_letter


def validate_recipient(name: str | None, email: str | None) -> list[str]:
    """
    Validate an individual recipient's name and email against Section 9.2 rules.
    Returns a list of error message strings (empty list indicates valid).
    """
    errors: list[str] = []

    # 1. Name validation
    norm_name = normalize_text(name)
    if not norm_name:
        errors.append(MSG_NAME_REQUIRED)
    else:
        if not (MIN_RECIPIENT_NAME_LENGTH <= len(norm_name) <= MAX_RECIPIENT_NAME_LENGTH):
            errors.append(MSG_NAME_LENGTH)
        if not is_valid_name_chars(norm_name):
            errors.append(MSG_NAME_INVALID_CHARS)

    # 2. Email validation
    norm_email = normalize_email(email)
    if not norm_email:
        errors.append(MSG_EMAIL_REQUIRED)
    else:
        if len(norm_email) > MAX_EMAIL_LENGTH:
            errors.append(f"Invalid email: '{norm_email}'")
        else:
            try:
                email_validator.validate_email(norm_email, check_deliverability=False)
            except email_validator.EmailNotValidError:
                errors.append(f"Invalid email: '{norm_email}'")

    return errors


@dataclass(slots=True)
class RecipientCheck:
    """Result of validating a recipient row."""

    row_number: int
    name: str
    email: str | None
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        """True if recipient has zero validation errors."""
        return len(self.errors) == 0

    @property
    def error_message(self) -> str | None:
        """Joined error messages formatted for database persistence."""
        if not self.errors:
            return None
        return "; ".join(self.errors)


def validate_recipients(items: list[Any]) -> list[RecipientCheck]:
    """
    Validate a list of recipient objects/dicts with duplicate detection across rows.
    Tracks earlier rows to attach 'Duplicate of row N' errors.
    """
    results: list[RecipientCheck] = []
    seen_recipients: dict[tuple[str, str], int] = {}

    for index, item in enumerate(items, start=1):
        # Extract raw name and email whether item is dict, RecipientIn, or object
        if isinstance(item, dict):
            raw_name = item.get("name")
            raw_email = item.get("email")
        else:
            raw_name = getattr(item, "name", None)
            raw_email = getattr(item, "email", None)

        errors = validate_recipient(raw_name, raw_email)

        norm_name = normalize_text(raw_name)
        norm_email = normalize_email(raw_email)

        # Duplicate detection (case-insensitive on both name and email)
        if norm_name and norm_email:
            key = (norm_name.casefold(), norm_email.casefold())
            if key in seen_recipients:
                first_row = seen_recipients[key]
                errors.append(f"Duplicate of row {first_row}")
            else:
                seen_recipients[key] = index

        results.append(
            RecipientCheck(
                row_number=index,
                name=norm_name if norm_name else (raw_name or "")[:255],
                email=norm_email if norm_email else raw_email,
                errors=errors,
            )
        )

    return results
