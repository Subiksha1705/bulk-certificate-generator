#!/usr/bin/env python3
"""
CLI script to generate test payloads for the Bulk Certificate Generator.
Usage:
    python scripts/generate_payload.py --count 300 --invalid 5
"""

import argparse
import json
import random

FIRST_NAMES = [
    "Aarav",
    "Aditi",
    "Ananya",
    "Dev",
    "Diya",
    "Ishaan",
    "Kavya",
    "Manish",
    "Neha",
    "Pranav",
    "Pooja",
    "Rahul",
    "Rohan",
    "Sanjay",
    "Sneha",
    "Subiksha",
    "Tanvi",
    "Varun",
    "Vikram",
    "Zoya",
    "Elena",
    "Liam",
    "Sophia",
    "Lucas",
]

LAST_NAMES = [
    "Sharma",
    "Verma",
    "Patel",
    "Rao",
    "Reddy",
    "Iyer",
    "Nair",
    "Mehta",
    "Gupta",
    "Singh",
    "Das",
    "Ramesh",
    "Mukherjee",
    "Kapoor",
    "Bhat",
    "Chopra",
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
]

INVALID_SAMPLES = [
    {"name": "", "email": "missing.name@example.com"},
    {"name": "   ", "email": "whitespace.name@example.com"},
    {"name": "Bad Email User", "email": "not-an-email"},
    {"name": "No Domain", "email": "user@"},
    {"name": "No At Sign", "email": "username.domain.com"},
    {"name": "Emoji Name 😊", "email": "emoji@example.com"},
    {"name": "Too Long Name " + ("X" * 60), "email": "toolong@example.com"},
]


def generate_payload(count: int = 300, invalid: int = 0) -> dict:
    """Generate a bulk certificate job payload dictionary."""
    valid_count = max(0, count - invalid)
    recipients = []

    # Valid recipients
    for i in range(valid_count):
        fname = random.choice(FIRST_NAMES)
        lname = random.choice(LAST_NAMES)
        name = f"{fname} {lname}"
        email = f"{fname.lower()}.{lname.lower()}{i + 1}@example.com"
        recipients.append({"name": name, "email": email})

    # Invalid recipients
    for i in range(invalid):
        sample = INVALID_SAMPLES[i % len(INVALID_SAMPLES)]
        recipients.append(dict(sample))

    # Shuffle to simulate realistic mixed input
    random.shuffle(recipients)

    return {
        "event_name": "Full-Stack AI Engineering Workshop",
        "event_date": "2026-10-15",
        "organization_name": "TechCraft Innovations",
        "authorized_signatory": "Dr. Aris Thorne",
        "recipients": recipients,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate bulk certificate job test payloads")
    parser.add_argument(
        "--count",
        type=int,
        default=300,
        help="Total number of recipients to generate (default: 300)",
    )
    parser.add_argument(
        "--invalid",
        type=int,
        default=0,
        help="Number of invalid recipients to include (default: 0)",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation spaces (default: 2)",
    )

    args = parser.parse_args()
    payload = generate_payload(count=args.count, invalid=args.invalid)
    print(json.dumps(payload, indent=args.indent))


if __name__ == "__main__":
    main()
