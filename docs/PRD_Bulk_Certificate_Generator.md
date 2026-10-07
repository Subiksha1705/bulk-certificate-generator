# PRD — Bulk Certificate Generator (v2.0, phase-gated build spec)

> **Audience:** (1) the developer (owner), (2) the coding agent (Antigravity) that implements it.
> **Status:** Final. Supersedes all earlier notes/drafts. If anything conflicts, **this document wins**.
> **Date:** 7 Oct 2026

---

## Table of contents

1. [Agent operating rules (READ FIRST)](#1-agent-operating-rules-read-first)
2. [Product overview](#2-product-overview)
3. [USP / differentiators](#3-usp--differentiators)
4. [Design decisions (the "why")](#4-design-decisions-the-why)
5. [Architecture & repo structure](#5-architecture--repo-structure)
6. [Data model & state machines](#6-data-model--state-machines)
7. [API contract](#7-api-contract)
8. [Certificate template spec](#8-certificate-template-spec)
9. [Validation rules](#9-validation-rules)
10. [Configuration](#10-configuration)
11. [PHASES 0–11](#11-phases)
12. [Appendices: final checklist, interview pack, risks](#12-appendices)

---

## 1. Agent operating rules (READ FIRST)

The owner will be questioned in an interview on this code ("explain it, debug it, change a requirement"). **Understandability beats cleverness.**

### 1.1 Phase gating (hard rule)

1. Implement **exactly one phase at a time**, in order (Phase 0 → 11).
2. When a phase is finished, run its tests, then output the **Phase Report** (§1.3) and **STOP**.
3. Do **not** start the next phase until the owner types **`next`**. If the owner reports a bug, fix it inside the current phase and re-report.
4. Never build ahead (no "while I'm here" extras, no files from later phases).
5. Commit once per phase to local git: `phase-N: <summary>` and tag `phase-N`. **Do not push** to GitHub until Phase 11 (or the owner says so).

### 1.2 Code rules

- Python 3.12, type hints everywhere, SQLAlchemy **2.0 style** (`Mapped[...]`, `mapped_column`), Pydantic **v2**.
- Small functions (aim < 40 lines). Comments explain **why**, not what. No dead code, no TODO litter.
- Follow the structure in §5. Don't add dependencies beyond §5.3 without asking.
- Routers contain **no business logic** — they call `services/`. Services never import FastAPI.
- Format/lint with `ruff` (line length 100) if installed.
- Every phase ships **its own tests**. A phase is not done with red tests.
- If a library API differs from what this PRD assumes, **stop and ask**; don't silently work around it. Report deviations in the Phase Report.

### 1.3 Phase Report (mandatory format after every phase)

```
## Phase N Report
1. What was built (3–6 lines)
2. Files created/changed (tree)
3. How to run & test (exact commands)
4. Expected output (what the owner should see)
5. Explain-it-in-an-interview (5 bullets)
6. Known limitations / deviations from PRD
7. ⏸ Waiting for "next"
```

Also **append a section to `docs/INTERVIEW_NOTES.md`** each phase: *What / Why / How it works / 3 likely questions with answers*. This file is the owner's study guide.

### 1.4 Boundaries — do NOT build

React/any frontend (except the optional 20-line HTML verify page in Phase 8), dashboard, authentication, email sending, Redis, Celery, Docker-for-the-app, Kubernetes, microservices, multiple templates, template editor, AI features.

---

## 2. Product overview

### 2.1 Problem
An organization finishes an event/course and needs certificates for many participants. Calling an API once per certificate is inefficient. The client should submit **one request** with all recipients; the backend validates, generates personalized PDFs from **one predefined template**, tracks progress, isolates failures, and lets the client retrieve certificates.

### 2.2 Goals
- One bulk endpoint; asynchronous generation; per-recipient failure isolation.
- Accurate progress tracking; individual and bulk retrieval.
- Fault tolerance (retry, crash recovery, self-healing storage) and safe duplicate handling.
- Live at ₹0: **Render (free web service) + Neon (free Postgres) + GitHub**.

### 2.3 Non-goals
See §1.4. Plus: no user accounts, no per-tenant isolation, no email delivery.

### 2.4 Assignment traceability matrix

| Assignment requirement | Where satisfied | Phase |
|---|---|---|
| Python + FastAPI + relational DB | FastAPI, PostgreSQL (Neon), SQLAlchemy | 0–1 |
| Accept bulk request | `POST /api/jobs/` | 4 |
| Validate recipient data | `services/validation.py` | 2, 4 |
| Generate via predefined template | ReportLab over `certificate_template.png` | 3, 5 |
| Track generation status / progress | `GET /api/jobs/{id}` | 4, 5 |
| One failure ≠ job failure | per-certificate try/except + failure types | 5 |
| Retrieve generated certificates | list / view / download / zip | 4, 6 |
| Document sync vs async choice | README + §4 | 10 |
| Tests (6 mandatory areas) | `tests/` | every phase, 9 |
| README (setup, run, test, submit, retrieve, decisions) | README | 10 |
| Public GitHub repo | — | 11 |
| Optional small improvements | USPs in §3 | 7–8 |

---

## 3. USP / differentiators

Positioning line:
> **"A fault-tolerant bulk certificate API with asynchronous processing, progress tracking, per-recipient failure isolation, retry, crash recovery, self-healing storage, and publicly verifiable certificates."**

| # | Feature | Why it impresses | Cost | Phase |
|---|---|---|---|---|
| U1 | **Failure isolation** with typed failures (`VALIDATION` = not retryable, `GENERATION` = retryable) | Shows you understand *why* things fail and what retry can fix | Low | 5 |
| U2 | **Retry-failed** (only retryable failures; successes untouched; atomic guard against double-retry) | Core fault-tolerance story | Low | 7 |
| U3 | **Idempotency** via content hash (SHA-256 of normalized payload) + unique DB index + race handling | Real backend thinking, easy to explain | Low | 4 |
| U4 | **Crash recovery**: on startup, unfinished jobs resume | Render free tier restarts/sleeps — this is a *real* need | Low | 5 |
| U5 | **Self-healing storage**: DB is source of truth; PDFs are deterministic; a missing file is regenerated on demand | Solves Render's ephemeral disk at ₹0, no extra storage service | Low | 6 |
| U6 | **Bulk ZIP download** with `results.csv` manifest | What a real organizer actually wants | Low | 6 |
| U7 | **Public verification**: QR code on each certificate → `GET /api/verify/{id}` | Memorable; makes Certificate ID meaningful | Low–Med | 8 |
| U8 | **Unguessable IDs** (random, not sequential) | Public verify/download endpoints without auth are safe-ish by design | Trivial | 1 |
| U9 | **Auto-shrink text fit + glyph check** | Long names never overflow; unsupported glyphs fail cleanly | Low | 3 |
| U10 | **Demo failure switch** (`ENABLE_DEMO_FAILURES`) so reviewers can *see* fail → retry → success live | Makes the USP demonstrable in 60 seconds | Trivial | 7 |

---

## 4. Design decisions (the "why")

| Decision | Choice | Alternatives considered | Rationale (interview answer) |
|---|---|---|---|
| Processing model | **FastAPI `BackgroundTasks`** (in-process, DB-backed state) | Synchronous; Celery+Redis | Sync blocks the client for hundreds of PDFs. Celery/Redis is infra overkill and not free-tier friendly. All state lives in Postgres, so the worker is replaceable — swapping in Celery later changes only the *dispatch line*. Crash recovery (U4) covers BackgroundTasks' main weakness (lost on restart). |
| Public IDs | `JOB-2026-K7M3Q9XA`, `CERT-2026-8F3K2Q9X` — random 8 chars from an unambiguous alphabet; **string primary keys** | Sequential `CERT-2026-00001`; UUID | Sequential IDs let anyone enumerate certificates (names!) via public verify/download. Random 8-char base-32 ≈ 10¹² space; readable on paper (no `0/O/1/I`). Using them as PKs removes a mapping layer. |
| Storage | **Local disk + regenerate-on-miss**; storage behind a tiny class so S3/R2 can be swapped in | PDFs as `bytea` in Neon (0.5 GB limit); external object store | Neon free is small; Render disk is ephemeral. Deterministic PDFs (`invariant=1`) make regeneration safe. Zero extra services. |
| Schema management | `Base.metadata.create_all()` at startup | Alembic | Simpler to explain for a 2-table schema. Alembic → future scope. |
| Enum storage | `String` columns with `Enum(native_enum=False)` | Native PG enums | Avoids painful enum migrations; SQLite-compatible tests. |
| Counters | Stored on job, **recomputed from certificate rows** after each certificate | Increment counters | Recompute is self-correcting (retry, recovery, races). Cost is trivial at ≤1000 rows. |
| Validation boundary | **Structural problems → 422 for whole request** (missing `recipients`, wrong types, bad job fields). **Content problems in a recipient → that recipient is recorded as `FAILED/VALIDATION`**, rest proceed | Reject whole request if any recipient invalid | Matches the assignment: invalid data must not block valid recipients, and failures must be visible in job status. |
| Duplicate rows | Exact duplicate (same name + email, case-insensitive) within one request → later rows `FAILED/VALIDATION` ("Duplicate row") | Allow; dedupe silently | Realistic mistake (double-pasted rows); visible not silent. Easy to remove if requirement changes. |
| Idempotency | Content hash (order-insensitive recipients) with **unique index**; replay returns the **existing job** with `200` + `idempotent_replay:true` | `Idempotency-Key` header | No client cooperation required. Header variant noted as future scope. Race-safe via unique constraint + `IntegrityError` catch. |
| Event date | Any valid date 2000-01-01…2100-12-31 (future allowed) | Reject future dates | The sample date (10 Oct 2026) is in the future relative to today; rejecting would break the sample. |
| Organization shown twice | Template has an `Organization` body line **and** an `Organization Name` footer line → both filled with `organization_name` | Leave one blank | Blank lines look unfinished. Documented; trivially changeable in `layout.py`. |
| Test DB | SQLite in-memory by default; **optional** `TEST_DATABASE_URL` runs the same suite on Postgres | Postgres only | Reviewer can run tests with zero setup; Phase 9 proves it on Postgres too. |
| Job status vocabulary | `PENDING, PROCESSING, COMPLETED, COMPLETED_WITH_ERRORS, FAILED` | — | `FAILED` = nothing succeeded. |

---

## 5. Architecture & repo structure

### 5.1 Request flow

```
Client (Postman / Swagger)
   │ POST /api/jobs/
   ▼
Router ──► JobCreate (Pydantic: structure + job fields)
   │
   ▼
job_service.create_job
   ├─ compute request_hash ──► exists? ──yes──► return existing job (200, replay)
   ├─ validate each recipient (content) → valid / invalid
   ├─ INSERT job + certificate rows (valid=PENDING, invalid=FAILED/VALIDATION)
   └─ commit  (IntegrityError on hash ⇒ race ⇒ return existing)
   │
   ├─► BackgroundTasks.add_task(process_job, job_id, session_factory)
   ▼
202 { job_id, status, total, ... }

Background worker (own DB session):
   for each PENDING certificate of job:
        try  generate PDF → storage.save → status=SUCCESS
        except CertificateDataError → FAILED / VALIDATION   (not retryable)
        except Exception            → FAILED / GENERATION   (retryable)
        recompute job counters → commit      (progress visible to GET /jobs/{id})
   finalize job: COMPLETED | COMPLETED_WITH_ERRORS | FAILED
```

### 5.2 Repo structure (final)

```
bulk-certificate-generator/
├── app/
│   ├── main.py                 # app, lifespan (create_all, recovery), routers, /health
│   ├── config.py               # pydantic-settings
│   ├── constants.py            # length limits, alphabets, regexes
│   ├── database.py             # engine, SessionLocal, Base, get_db
│   ├── dependencies.py         # get_session_factory, get_storage (overridable in tests)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── enums.py            # JobStatus, CertificateStatus, FailureType
│   │   ├── job.py              # GenerationJob
│   │   └── certificate.py      # Certificate
│   ├── schemas/
│   │   ├── job.py              # JobCreate, RecipientIn, JobOut, JobCreateResponse
│   │   └── certificate.py      # CertificateOut, CertificateListOut, VerifyOut
│   ├── routers/
│   │   ├── jobs.py
│   │   ├── certificates.py
│   │   └── verify.py
│   ├── services/
│   │   ├── validation.py       # pure functions
│   │   ├── fingerprint.py      # request hash
│   │   ├── layout.py           # template coordinates (px)
│   │   ├── certificate_generator.py
│   │   ├── storage.py
│   │   ├── certificate_service.py   # build_certificate_data, get_or_regenerate_pdf
│   │   ├── job_service.py      # create_job, retry_failed, queries
│   │   ├── job_processor.py    # process_job, finalize, recover_interrupted_jobs
│   │   └── zip_export.py
│   ├── utils/ids.py
│   └── assets/
│       ├── template/certificate_template.png
│       └── fonts/ (Lora-*.ttf, GreatVibes-Regular.ttf, OFL.txt)
├── scripts/
│   ├── render_sample.py        # sample + calibration PDFs
│   ├── generate_payload.py     # N fake recipients → JSON for Postman
│   └── smoke_test.py           # end-to-end against BASE_URL
├── tests/ (conftest.py, test_health.py, test_models.py, test_validation.py, test_fingerprint.py,
│           test_generation.py, test_jobs.py, test_processing.py, test_certificates.py,
│           test_retry.py, test_verify.py, test_recovery.py)
├── postman/bulk-certificate-generator.postman_collection.json
├── docs/INTERVIEW_NOTES.md
├── requirements.txt · requirements-dev.txt · .env.example · .gitignore · .python-version · README.md
```

### 5.3 Dependencies

`requirements.txt`: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `psycopg2-binary`, `pydantic>=2`, `pydantic-settings`, `reportlab`, `email-validator`.
`requirements-dev.txt`: `-r requirements.txt`, `pytest`, `pytest-cov`, `httpx`, `pypdf`, `ruff`.
Install latest stable, then **pin exact versions** from `pip freeze` for these packages only.

---

## 6. Data model & state machines

### 6.1 `generation_jobs`

| Column | Type | Notes |
|---|---|---|
| `job_id` | `String(32)` **PK** | `JOB-{year}-{8 random}` |
| `event_name` | `String(100)` | |
| `event_date` | `Date` | |
| `organization_name` | `String(80)` | |
| `authorized_signatory` | `String(50)` | |
| `status` | `String(30)` | `JobStatus` |
| `total_recipients` | `Integer` | |
| `processed_count` / `successful_count` / `failed_count` | `Integer` default 0 | recomputed |
| `request_hash` | `String(64)` **UNIQUE, indexed** | idempotency |
| `created_at` | `DateTime(tz)` | UTC |
| `completed_at` | `DateTime(tz)` nullable | |

### 6.2 `certificates`

| Column | Type | Notes |
|---|---|---|
| `certificate_id` | `String(32)` **PK** | `CERT-{year}-{8 random}` |
| `job_id` | `String(32)` **FK → generation_jobs.job_id**, indexed | cascade delete |
| `row_number` | `Integer` | 1-based position in request |
| `recipient_name` | `String(255)` | normalized if valid, raw (truncated) if invalid |
| `recipient_email` | `String(255)` nullable | |
| `status` | `String(20)` | `CertificateStatus` |
| `failure_type` | `String(20)` nullable | `VALIDATION` / `GENERATION` |
| `error_message` | `Text` nullable | |
| `file_path` | `String(255)` nullable | relative, e.g. `JOB-…/CERT-….pdf` |
| `attempts` | `Integer` default 0 | incremented per generation attempt |
| `created_at`, `completed_at` | `DateTime(tz)` | |

Composite index `(job_id, status)`. Relationship: `GenerationJob.certificates` (`order_by=row_number`, `cascade="all, delete-orphan"`).

### 6.3 State machines

```
Certificate:  PENDING ──ok──► SUCCESS
              PENDING ──CertificateDataError──► FAILED(VALIDATION)   [terminal]
              PENDING ──other Exception───────► FAILED(GENERATION) ──retry──► PENDING
              (invalid at intake)             ► FAILED(VALIDATION)   [terminal]

Job:          PENDING ─► PROCESSING ─► COMPLETED               (failed == 0)
                                    ─► COMPLETED_WITH_ERRORS   (0 < successful, failed > 0)
                                    ─► FAILED                  (successful == 0)
              COMPLETED_WITH_ERRORS | FAILED ──retry-failed──► PROCESSING
              All recipients invalid at intake ─► FAILED immediately (no background task)
```

`processed = successful + failed`. `progress_percentage = round(processed / total * 100, 1)`.
Finalization rule is evaluated only when **no PENDING certificates remain**.

---

## 7. API contract

Base path `/api`. JSON everywhere except PDFs/ZIP. Errors use FastAPI's shape `{"detail": ...}`. Routers are mounted so the URL is exactly `/api/jobs/` (with trailing slash) for the create endpoint.

### 7.1 `POST /api/jobs/` — create bulk job

Request:
```json
{
  "event_name": "Python Workshop",
  "event_date": "2026-10-10",
  "organization_name": "ABC Technologies",
  "authorized_signatory": "Priya Sharma",
  "recipients": [
    { "name": "Subiksha P R", "email": "subiksha@example.com" },
    { "name": "Rahul Kumar",  "email": "rahul@example.com" },
    { "name": "",             "email": "abc" }
  ]
}
```
Response **202** (new) / **200** (idempotent replay):
```json
{
  "job_id": "JOB-2026-K7M3Q9XA",
  "status": "PENDING",
  "event_name": "Python Workshop",
  "event_date": "2026-10-10",
  "organization_name": "ABC Technologies",
  "authorized_signatory": "Priya Sharma",
  "total": 3, "processed": 1, "successful": 0, "failed": 1,
  "progress_percentage": 33.3,
  "created_at": "2026-10-07T09:30:00Z", "completed_at": null,
  "idempotent_replay": false,
  "links": { "self": "/api/jobs/JOB-2026-K7M3Q9XA",
             "certificates": "/api/jobs/JOB-2026-K7M3Q9XA/certificates" }
}
```
Errors: **422** (structure/job-field problems; empty list; more than `MAX_RECIPIENTS_PER_JOB`; unknown top-level fields).

### 7.2 `GET /api/jobs/{job_id}`
Same body as above without `idempotent_replay`. **404** if unknown.

### 7.3 `GET /api/jobs/{job_id}/certificates?status=&limit=100&offset=0`
`status` ∈ `PENDING|SUCCESS|FAILED` (else 422); `limit` 1–500; `offset` ≥ 0.
```json
{
  "job_id": "JOB-2026-K7M3Q9XA", "total": 3, "limit": 100, "offset": 0,
  "certificates": [
    { "certificate_id": "CERT-2026-8F3K2Q9X", "row_number": 1,
      "recipient_name": "Subiksha P R", "recipient_email": "subiksha@example.com",
      "status": "SUCCESS", "failure_type": null, "error_message": null, "attempts": 1,
      "view_url": "/api/certificates/CERT-2026-8F3K2Q9X/view",
      "download_url": "/api/certificates/CERT-2026-8F3K2Q9X/download",
      "created_at": "…", "completed_at": "…" },
    { "certificate_id": "CERT-2026-M2P9W4TC", "row_number": 3,
      "recipient_name": "", "recipient_email": "abc",
      "status": "FAILED", "failure_type": "VALIDATION",
      "error_message": "Name is required; Invalid email: 'abc'", "attempts": 0,
      "view_url": null, "download_url": null, "created_at": "…", "completed_at": "…" }
  ]
}
```
`view_url`/`download_url` are non-null **only when SUCCESS**. `total` = rows matching the filter.

### 7.4 `POST /api/jobs/{job_id}/retry-failed`
**202** `{ "job_id": "...", "retried_count": 3, "skipped_non_retryable": 1, "status": "PROCESSING" }`
**404** unknown job · **409** when job is `PENDING/PROCESSING` ("still processing"), `COMPLETED` ("nothing to retry"), or no `FAILED/GENERATION` certificates exist (message states how many validation failures need a corrected resubmission).

### 7.5 `GET /api/jobs/{job_id}/download-all`
`application/zip`, filename `{job_id}.zip`: all SUCCESS PDFs as `{row_number:04d}_{slug-name}_{certificate_id}.pdf` + `results.csv` (`row,name,email,certificate_id,status,failure_type,error_message`; cells beginning with `= + - @` are prefixed with `'` to prevent CSV injection). **404** unknown job · **409** if zero SUCCESS certificates.

### 7.6 `GET /api/certificates/{certificate_id}` → metadata (same object as list item). **404** unknown.
### 7.7 `GET /api/certificates/{certificate_id}/view` → `application/pdf`, `Content-Disposition: inline`.
### 7.8 `GET /api/certificates/{certificate_id}/download` → `application/pdf`, `Content-Disposition: attachment; filename="Certificate_{slug-name}_{certificate_id}.pdf"`.
Both: **404** unknown · **409** `{"detail":"Certificate is not available (status=FAILED)"}` if not SUCCESS. If the file is missing on disk → regenerate transparently (U5).

### 7.9 `GET /api/verify/{certificate_id}`
**200** `{ "valid": true, "certificate_id", "recipient_name", "event_name", "event_date", "organization_name", "issued_at" }` — **no email returned**.
**404** `{ "valid": false }` for unknown or non-SUCCESS certificates.

### 7.10 `GET /health` → `{"status":"ok","database":"ok"}` (503 with `"database":"error"` if `SELECT 1` fails).

---

## 8. Certificate template spec

**Asset:** `app/assets/template/certificate_template.png` (the provided Canva design: green ornamental border, script "Certificate", "OF COMPLETION", four labelled body lines, three footer lines).
**Expected size:** ≈ **2000 × 1414 px** (A4-landscape ratio). The agent **must read the real size with Pillow** and, if different, scale all coordinates by `actual_width / 2000`.
**PDF page:** A4 landscape = 841.89 × 595.28 pt. Scale `px → pt = 595.28 / template_height_px` (≈ 0.421). Layout constants are written in **template pixels (origin top-left)**; a helper converts to PDF points (flip Y).

### 8.1 Field map (initial estimates — Phase 3 calibration is the source of truth)

| Field | Value source | Align | Line x₁–x₂ | Line y | Baseline y | Font | Start / Min px | Max width px |
|---|---|---|---|---|---|---|---|---|
| Recipient name | `recipient_name` | center @ x=1398 | 1008–1787 | 544 | 534 | Lora-SemiBold | 56 / 30 | 740 |
| Event / course | `event_name` | center @ x=1312 | 860–1763 | 650 | 640 | Lora-Medium | 40 / 24 | 860 |
| Organization | `organization_name` | center @ x=1215 | 763–1667 | 747 | 737 | Lora-Medium | 40 / 24 | 860 |
| Date of completion | `event_date` → `10 October 2026` | center @ x=1011 | 750–1271 | 856 | 846 | Lora-Medium | 40 / 30 | 480 |
| Authorized signature | `authorized_signatory` (**script font**) | center @ x=491 | 301–680 | 1136 | 1122 | GreatVibes-Regular | 60 / 32 | 350 |
| Organization Name (footer) | `organization_name` | center @ x=991 | 801–1180 | 1134 | 1121 | Lora-Medium | 30 / 20 | 350 |
| Certificate ID | `certificate_id` | center @ x=1510 | 1320–1699 | 1136 | 1121 | Lora-Medium | 30 / 24 | 350 |
| QR code (Phase 8) | verify URL | box | x 1454–1564 | y 970–1080 | — | — | 110 px square | — |

Text colour: `#1A1A1A` (signatory `#1F2A44` for an "ink" look). Static template text is **never** redrawn.

### 8.2 Rules
- **Fit:** start at the start size; reduce in 1 px steps to the min size until width ≤ max width. Still too wide → raise `TextOverflowError`.
- **Glyph check:** every character must exist in the chosen font (`font.face.charToGlyph`); otherwise `UnsupportedCharacterError`. Both inherit `CertificateDataError` → **non-retryable**.
- **Determinism:** `Canvas(..., invariant=1, pageCompression=1)`; no timestamps, no randomness → identical bytes for identical input.
- **Metadata:** PDF title `Certificate – {name}`, author = organization.
- **Size budget:** average PDF < 500 KB. If larger, re-encode the template (JPEG q≈90, or downscale to 1600 px wide) and re-calibrate.
- **Fonts:** static (non-variable) TTFs, SIL OFL, with `OFL.txt` in the fonts folder. Fetch from Google Fonts (Lora, Great Vibes); if the agent can't download, ask the owner to place them.

---

## 9. Validation rules

### 9.1 Job-level (Pydantic → 422)

| Field | Rule |
|---|---|
| `event_name` | trimmed, collapsed whitespace, 3–100 chars |
| `event_date` | valid ISO date within 2000-01-01…2100-12-31 |
| `organization_name` | trimmed, 2–80 chars |
| `authorized_signatory` | trimmed, 2–50 chars, passes glyph check for the script font |
| `recipients` | list, **1…`MAX_RECIPIENTS_PER_JOB`** items |
| extra top-level keys | forbidden (`extra="forbid"`) — catches typos like `date` |

Job text fields must also pass the glyph + fit check (Phase 3 helper) → 422 with a clear message instead of failing every certificate.

### 9.2 Recipient-level (recorded as `FAILED/VALIDATION`, never aborts the job)

| Code | Rule | Message |
|---|---|---|
| `NAME_REQUIRED` | missing/blank | `Name is required` |
| `NAME_TOO_SHORT` / `NAME_TOO_LONG` | 2–60 chars after normalization | `Name must be 2–60 characters` |
| `NAME_INVALID_CHARS` | must contain a letter; allowed: letters (incl. accents), space, `.` `'` `-`; no control chars | `Name contains unsupported characters` |
| `EMAIL_REQUIRED` | missing/blank | `Email is required` |
| `EMAIL_INVALID` | `email_validator.validate_email(check_deliverability=False)`; ≤ 254 chars | `Invalid email: 'abc'` |
| `DUPLICATE_ROW` | same (casefold name, casefold email) as an earlier row | `Duplicate of row 2` |

Multiple errors on one recipient are joined with `"; "`. Normalization: strip, collapse internal whitespace; email lowercased for hashing/duplicates but stored as entered (trimmed). Structural recipient problems (item isn't an object, `name` is a number) → whole-request 422.

---

## 10. Configuration

`app/config.py` (pydantic-settings, reads `.env`), documented in `.env.example`:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — (required) | `postgresql+psycopg2://user:pass@host/db?sslmode=require` (SQLite allowed for tests) |
| `STORAGE_DIR` | `./storage` | PDF root |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | QR/verify URLs |
| `MAX_RECIPIENTS_PER_JOB` | `1000` (prod: `500`) | request limit |
| `RECOVER_ON_STARTUP` | `true` | resume unfinished jobs |
| `ENABLE_DEMO_FAILURES` | `false` | see Phase 7 |
| `SIMULATED_DELAY_MS` | `0` | per-certificate delay to watch progress in Postman (dev/demo only) |
| `ENVIRONMENT` | `dev` | `dev`/`production` |
| `LOG_LEVEL` | `INFO` | |

Engine options: `pool_pre_ping=True`, `pool_recycle=300` (Neon scales to zero when idle), small pool (`pool_size=5`, `max_overflow=5`); SQLite gets `check_same_thread=False` + `StaticPool` for in-memory tests.

---

## 11. Phases

Time estimates are rough. Every phase ends with: **tests green → Phase Report → commit/tag → STOP, wait for `next`.**

---

### PHASE 0 — Environment & scaffolding (~45 min)

**Goal:** a running skeleton and green smoke test.

**Owner prerequisites (agent: ask and confirm before starting):**
- Python 3.12 and Git installed.
- Choose a dev database — **Option A** Neon free project (same as prod; simplest), **Option B** Docker `postgres:16`, **Option C** native PostgreSQL. Agent records the choice and prints the exact `DATABASE_URL` format.
- Fonts available (agent attempts download; otherwise owner places them in `app/assets/fonts/`).

**Tasks**
1. `git init`; create folders/files per §5.2 (empty `__init__.py` where needed).
2. `.gitignore`: `.venv/`, `.env`, `storage/`, `samples/`, `__pycache__/`, `.pytest_cache/`, `.coverage`, `*.pyc`.
3. Create venv; `requirements.txt` / `requirements-dev.txt` per §5.3; install; pin versions.
4. `.python-version` containing `3.12`.
5. `app/config.py` — `Settings` + cached `get_settings()`. `.env.example` with every §10 variable.
6. `app/main.py` — FastAPI app titled "Bulk Certificate Generator", `lifespan` stub (empty), `GET /health` → `{"status":"ok"}` (DB check comes in Phase 1).
7. Copy the template PNG to `app/assets/template/certificate_template.png`; print its pixel size with Pillow and report it.
8. `docs/INTERVIEW_NOTES.md` skeleton; `tests/test_health.py` using `TestClient`.

**Acceptance**
- `uvicorn app.main:app --reload` starts; `http://localhost:8000/docs` loads; `/health` returns 200.
- `pytest` → 1 passed.
- Template size reported.

**Manual check (owner):** open `/docs`, call `/health`.

---

### PHASE 1 — Database layer & models (~1 h)

**Goal:** tables exist in Postgres; IDs generated safely.

**Tasks**
1. `database.py`: engine from settings (options in §10), `SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)`, `Base(DeclarativeBase)`, `get_db()` generator dependency (yield; always close).
2. `models/enums.py`: `JobStatus`, `CertificateStatus`, `FailureType` as `str, Enum`.
3. `models/job.py`, `models/certificate.py` exactly per §6 (SQLAlchemy 2.0 typed style; `Enum(..., native_enum=False)`; UTC-aware timestamps via a `utcnow()` helper; FK `ondelete="CASCADE"`; composite index). `models/__init__.py` imports both.
4. `utils/ids.py`: `generate_job_id()`, `generate_certificate_id()` using `secrets.choice` over `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, length 8, prefix with current UTC year. (Alphabet/length in `constants.py`.)
5. `main.py` lifespan: `Base.metadata.create_all(engine)`. `/health` now executes `SELECT 1` (503 on failure).
6. `dependencies.py`: `get_session_factory()` returning `SessionLocal` (overridable).
7. `tests/conftest.py`: SQLite in-memory engine (`StaticPool`), fresh schema per test, `client` fixture overriding `get_db` and `get_session_factory`, temp `STORAGE_DIR`. If `TEST_DATABASE_URL` is set, use it instead (create/drop all per test).

**Tests (`test_models.py`):** create job + certificates and read back; relationship ordering by `row_number`; unique `request_hash` raises `IntegrityError`; cascade delete removes certificates; ID format regex `^JOB-\d{4}-[A-HJ-NP-Z2-9]{8}$` / `^CERT-…`; 10 000 generated IDs are unique and exclude `0 O 1 I`.

**Acceptance:** tests green; starting the app creates both tables in the dev DB.

**Manual check (owner):** open the DB (Neon SQL editor / psql / DBeaver) → see `generation_jobs` and `certificates` with the right columns, indexes, FK. Hit `/health` → `database: ok`.

---

### PHASE 2 — Schemas, validation & fingerprint (pure logic) (~1.5 h)

**Goal:** all input rules implemented as **pure, unit-tested functions** (no DB/HTTP).

**Tasks**
1. `constants.py`: all limits from §9.
2. `schemas/job.py`: `RecipientIn` (`name: str | None`, `email: str | None`, extra ignored); `JobCreate` (field validators per §9.1, `extra="forbid"`, list bounds from settings); `JobOut` (with computed `progress_percentage`, `links`); `JobCreateResponse(JobOut + idempotent_replay)`.
3. `schemas/certificate.py`: `CertificateOut` (computes `view_url`/`download_url` only if SUCCESS), `CertificateListOut`, `VerifyOut`.
4. `services/validation.py`:
   - `normalize_text(s) -> str`, `normalize_email(s) -> str`
   - `validate_recipient(name, email) -> list[str]` (error messages; empty = valid)
   - `validate_recipients(items) -> list[RecipientCheck]` where `RecipientCheck(row_number, name, email, errors: list[str])`; adds `DUPLICATE_ROW` detection.
5. `services/fingerprint.py`: `compute_request_hash(job: JobCreate) -> str` — SHA-256 over canonical JSON (`sort_keys=True`, `separators=(",", ":")`) of normalized job fields + recipients as sorted `(casefold name, casefold email)` pairs (invalid ones included, best-effort normalized, `None → ""`).

**Tests (table-driven):** `test_validation.py` — every code in §9.2 (blank, whitespace-only, 1 char, 61 chars, digits-only name, emoji, `D'Souza`, `José`, `Mary-Ann`, `abc`, `a@b`, 255-char email, duplicate rows incl. different case); job-field bounds (date 1999/2101, future date OK, unknown field rejected, 0 and max+1 recipients). `test_fingerprint.py` — same payload ⇒ same hash; recipient order irrelevant; whitespace/case noise irrelevant; any field change ⇒ different hash.

**Acceptance:** `pytest tests/test_validation.py tests/test_fingerprint.py` green; no file in this phase imports FastAPI routers or touches the DB.

**Manual check (owner):** none required; agent prints a small table of sample inputs → outputs in the Phase Report.

---

### PHASE 3 — PDF generator & visual calibration (~2–3 h) ⭐ visual sign-off

**Goal:** a pixel-accurate, deterministic certificate PDF.

**Tasks**
1. `services/layout.py`: dataclass `FieldSpec(center_x, baseline_y, font, start_px, min_px, max_width_px, color)` for each §8.1 field + QR box (QR drawn in Phase 8, box defined now); `px_to_pt` helpers using the real template size.
2. `services/certificate_generator.py`:
   - `register_fonts()` (idempotent), template loaded once (`lru_cache` ImageReader).
   - exceptions: `CertificateDataError` → `UnsupportedCharacterError`, `TextOverflowError`.
   - `@dataclass CertificateData(recipient_name, event_name, event_date, organization_name, authorized_signatory, certificate_id, verify_url: str | None = None)`.
   - `fit_font_size(text, font_name, spec) -> float` and `check_glyphs(text, font_name)`.
   - `generate_certificate_pdf(data) -> bytes` per §8.2 (determinism, metadata). Date rendered as `f"{d.day} {d:%B %Y}"`.
   - `validate_text_renderable(text, field) -> None` public helper reused by job-field validation (wire into `JobCreate` validators now).
3. `scripts/render_sample.py` → writes `samples/sample.pdf` (name "Subiksha P R") **and** `samples/calibration.pdf` (template + 100 px grid with labels, red baseline ticks, dashed max-width boxes for every field, sample text drawn). Also `--stress` writes `samples/stress.pdf` pages for: very long valid name, `D'Souza`, `José`, long event & org names.
4. Measure & report: PDF size, mean generation time over 50 runs.

**Tests (`test_generation.py`):** output starts with `%PDF`; page size ≈ 841.89×595.28; `pypdf` text contains name, event, org, date string, certificate ID, signatory; deterministic (two calls ⇒ identical bytes); emoji and Devanagari/Tamil text raise `UnsupportedCharacterError`; absurdly long text raises `TextOverflowError`; a long-but-fitting name shrinks and succeeds; size < 500 KB.

**Acceptance — OWNER VISUAL SIGN-OFF (blocking):** owner opens `calibration.pdf`, `sample.pdf`, `stress.pdf` and confirms: text sits just above each line, centered, never touching static text/border; script signature looks like a signature; shrinking looks acceptable. Agent adjusts `layout.py` numbers until the owner approves.

**Interview point:** "Coordinates live in one file, in template pixels; changing the template means editing numbers, not logic."

---

### PHASE 4 — Storage & job creation/read endpoints (~2 h)

**Goal:** `POST /api/jobs/` creates a job with certificate rows; idempotency works. (No generation yet — valid certificates stay `PENDING`; say so in the report.)

**Tasks**
1. `services/storage.py` — `PdfStorage(root: Path)`: `save(job_id, cert_id, data: bytes) -> str` (atomic: write temp file then `os.replace`; returns relative path), `read(rel_path) -> bytes | None`, `exists(rel_path) -> bool`. Resolve paths and refuse anything escaping `root`. `dependencies.get_storage()`.
2. `services/job_service.py`:
   - `create_job(db, payload) -> tuple[GenerationJob, bool]` (`bool` = created):
     1. compute hash → look up existing → return `(existing, False)`;
     2. run `validate_recipients`;
     3. insert job (`PENDING`, `total_recipients`) + one certificate per recipient (valid → `PENDING`; invalid → `FAILED/VALIDATION`, `error_message`, `completed_at`, `attempts=0`);
     4. recompute counters; if no valid recipients → job `FAILED` + `completed_at`;
     5. commit; on `IntegrityError` for `request_hash` → rollback, re-query, return `(existing, False)`.
   - `get_job_or_404`, `list_certificates(db, job_id, status, limit, offset)`.
   - `recompute_counts(db, job)` (single `GROUP BY status` query) — shared with Phase 5.
3. `routers/jobs.py`: `POST /api/jobs/` (202 new / 200 replay), `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/certificates`. Register in `main.py`.

**Tests (`test_jobs.py`):** create job → 202 + shape; job & certificate rows persisted; mixed valid/invalid → invalid recorded as `FAILED/VALIDATION` with messages and `row_number`; all-invalid ⇒ job `FAILED`; **identical resubmission ⇒ 200, same `job_id`, `idempotent_replay:true`, no new rows**; reordered recipients ⇒ still replay; changed field ⇒ new job; simulated race (insert same hash then call create) ⇒ returns existing; 422 cases (empty list, > max, unknown field, bad date); GET unknown ⇒ 404; list pagination + `status` filter + invalid filter ⇒ 422.

**Acceptance:** tests green.

**Manual check (owner, Postman/Swagger):** create the §7.1 sample → see `failed: 1`; send it again → `200` replay with the same ID; GET job; list certificates with `?status=FAILED`.

---

### PHASE 5 — Background processing & progress (~2.5 h) ⭐ core

**Goal:** certificates actually get generated asynchronously with live progress and failure isolation.

**Tasks**
1. `services/certificate_service.py`: `build_certificate_data(cert, job) -> CertificateData` (single place that maps DB rows → generator input; reused by self-healing in Phase 6).
2. `services/job_processor.py`:
   - `process_job(job_id, session_factory)` — opens **its own session** (never reuse the request session):
     1. load job; set `PROCESSING` if `PENDING`;
     2. iterate PENDING certificates ordered by `row_number` (re-query in batches of 50 by id so memory stays flat);
     3. per certificate: `attempts += 1`; try → generate → `storage.save` → `SUCCESS`, `file_path`, `completed_at`; `except CertificateDataError` → `FAILED/VALIDATION`; `except Exception` → `FAILED/GENERATION` with `str(exc)[:500]` and `logger.exception`;
     4. `recompute_counts` + **commit after every certificate** (progress is visible immediately);
     5. optional `time.sleep(SIMULATED_DELAY_MS/1000)` per certificate;
     6. when no PENDING remain → `finalize_job` (rule in §6.3), set `completed_at`.
   - Missing job ⇒ log & return. Outer `try/except` marks nothing wrongly: if the worker itself dies, certificates simply remain `PENDING` (recovered later).
   - `recover_interrupted_jobs(session_factory)` — finds jobs in `PENDING`/`PROCESSING` with PENDING certificates and starts `process_job` in daemon threads. Called from lifespan when `RECOVER_ON_STARTUP` is true. (Single-instance assumption documented.)
3. `routers/jobs.py`: after a **new** job with ≥ 1 valid recipient is committed, `background_tasks.add_task(process_job, job_id, session_factory)` where `session_factory` comes from `Depends(get_session_factory)`.
4. Logging config (`LOG_LEVEL`), log lines include `job_id`/`certificate_id`.
5. `scripts/generate_payload.py --count 300 [--invalid 5]` prints a ready-to-paste JSON payload.

**Tests (`test_processing.py`, `test_recovery.py`)** (TestClient runs background tasks before returning, so assertions are deterministic):
- happy path: all SUCCESS, job `COMPLETED`, `processed==total`, PDF files exist & start with `%PDF`;
- progress numbers: counts and `progress_percentage` correct at completion;
- **individual failure**: monkeypatch `job_processor.generate_certificate_pdf` to raise `RuntimeError` for one name ⇒ that cert `FAILED/GENERATION`, others SUCCESS, job `COMPLETED_WITH_ERRORS`, error message stored;
- `CertificateDataError` ⇒ `FAILED/VALIDATION`;
- all-fail ⇒ job `FAILED`; all-invalid intake ⇒ no task scheduled;
- mid-job progress: call `process_job` with a generator patched to raise `KeyboardInterrupt`-free stop after N (or patch to check DB counts between calls) ⇒ counts reflect partial progress;
- recovery: seed a job with PENDING certificates and `PROCESSING` status ⇒ `recover_interrupted_jobs` completes it.

**Acceptance:** tests green; a 300-recipient job completes; `SIMULATED_DELAY_MS=100` lets the owner watch `processed` climb.

**Manual check (owner):** generate a payload (300 recipients incl. 5 invalid), set `SIMULATED_DELAY_MS=100`, POST it, poll `GET /api/jobs/{id}` several times → watch status/progress change → final `COMPLETED_WITH_ERRORS` with `failed: 5`. Check `storage/` contains PDFs.

---

### PHASE 6 — Retrieval: view, download, self-healing, ZIP (~2 h)

**Goal:** every successful certificate is retrievable, even after the disk is wiped.

**Tasks**
1. `certificate_service.get_or_regenerate_pdf(db, cert, storage) -> bytes`: read file; if missing/unreadable → rebuild via `build_certificate_data` + generator → `storage.save` → return bytes; log `"regenerated missing file"`.
2. `routers/certificates.py`: `GET /api/certificates/{id}`, `/view` (inline), `/download` (attachment, sanitized slug filename, `X-Content-Type-Options: nosniff`). 404 unknown, 409 not SUCCESS.
3. `services/zip_export.py` + `GET /api/jobs/{job_id}/download-all`: build the ZIP in a `SpooledTemporaryFile` (not fully in RAM), include `results.csv` (CSV-injection-safe), self-heal each missing file, stream via `StreamingResponse`/`FileResponse`, clean temp file afterwards. 404/409 per §7.5.
4. Refactor Phase 5 processor to use `build_certificate_data` if not already.

**Tests (`test_certificates.py`):** view returns `application/pdf` + inline; download returns attachment with expected filename; bytes start with `%PDF`; unknown ⇒ 404; FAILED/PENDING cert ⇒ 409; **delete the PDF file from storage ⇒ download still works and the file reappears** (self-heal) and bytes equal the original (determinism); ZIP contains N PDFs + `results.csv`; CSV rows correct and injection-safe (`=cmd` name prefixed — use a name allowed by validation only for CSV unit test of the helper); zip of job with zero SUCCESS ⇒ 409.

**Acceptance:** tests green.

**Manual check (owner):** open `/view` in the browser; download one; download the job ZIP and open `results.csv`; **delete the `storage/` folder, download again** → still works.

---

### PHASE 7 — Retry-failed & demo failure switch (~1.5 h)

**Goal:** U2 + U10.

**Tasks**
1. `job_service.retry_failed(db, job_id) -> RetryResult`:
   - allowed only when job status ∈ {`COMPLETED_WITH_ERRORS`, `FAILED`} — enforced by an **atomic conditional update** (`UPDATE … SET status='PROCESSING', completed_at=NULL WHERE job_id=:id AND status IN (…)`; `rowcount == 0` ⇒ 409) so two simultaneous calls can't both retry;
   - select certificates `FAILED` **and** `failure_type == GENERATION`; none ⇒ revert status, 409 with message including the count of validation failures;
   - reset them to `PENDING`, clear `error_message`/`failure_type`/`completed_at` (keep `attempts`); recompute counters.
2. `POST /api/jobs/{job_id}/retry-failed` → 202 payload per §7.4, scheduling `process_job` as a background task.
3. Demo switch (in the processor, not the generator): when `ENABLE_DEMO_FAILURES` is true and a recipient's name starts with `FAILME` (case-insensitive) and this is their **first** attempt (`attempts == 1`), raise `RuntimeError("Simulated transient failure (demo)")`. Second attempt succeeds. Log a warning at startup when enabled.

**Tests (`test_retry.py`):** 5 recipients, 2 `FAILME…` with the switch on ⇒ `COMPLETED_WITH_ERRORS`, failed 2 ⇒ retry ⇒ all SUCCESS, job `COMPLETED`; **successful certificates untouched** (`attempts` unchanged, file `mtime`/generator call count unchanged); validation failures are *not* retried and are reported as `skipped_non_retryable`; retry on `COMPLETED` ⇒ 409; retry while `PROCESSING` ⇒ 409; retry with only validation failures ⇒ 409 with explanatory message; a still-failing certificate (generator patched to always fail) stays `FAILED` with `attempts == 2`; double-retry guard (call service twice) ⇒ second gets 409; unknown job ⇒ 404.

**Acceptance:** tests green.

**Manual check (owner):** set `ENABLE_DEMO_FAILURES=true`; POST a job containing `FAILME One`, `FAILME Two`, plus normal names ⇒ `COMPLETED_WITH_ERRORS (failed 2)` ⇒ `POST …/retry-failed` ⇒ `COMPLETED (failed 0)`. Record this 60-second demo flow for the README.

---

### PHASE 8 — Public verification & QR (USP) (~1.5 h)

**Goal:** U7 — each certificate carries a QR that opens its verification record.

**Tasks**
1. `routers/verify.py`: `GET /api/verify/{certificate_id}` per §7.9 (no email; 404 `{"valid": false}` for unknown/non-SUCCESS).
2. Generator: when `verify_url` is provided, draw a QR in the §8.1 QR box using `reportlab.graphics.barcode.qr.QrCodeWidget` + `renderPDF` (no new dependency). `build_certificate_data` sets `verify_url = f"{PUBLIC_BASE_URL}/api/verify/{certificate_id}"`.
3. Update `render_sample.py` / calibration to show the QR box; **owner re-approves placement** (must not collide with the Certificate ID text or footer lines).
4. *(Optional, ≤ 25 lines, `html.escape` everything, no template engine)* `GET /verify/{certificate_id}` returning a tiny HTML page ("✔ Valid certificate — {name}, {event}, {org}, {date}") so a phone scan shows something friendly. Skip if it risks scope.

**Tests (`test_verify.py`):** valid cert ⇒ 200 with correct fields and **no email key**; unknown ⇒ 404; FAILED cert ⇒ 404; generated PDF contains the QR (assert PDF with `verify_url` differs from without, and the verify URL string is derivable from `build_certificate_data`); regenerated PDF (self-heal) still byte-identical.

**Acceptance:** tests green; owner scans the QR from the PDF with a phone (while the app is reachable — for local testing, use the LAN IP in `PUBLIC_BASE_URL` or verify after deployment).

---

### PHASE 9 — Test hardening & quality pass (~2 h)

**Goal:** the six mandatory test areas are provably covered; code is clean.

**Tasks**
1. Add a README-ready table mapping each mandatory area to test files (see below) and fill any gaps.
2. `pytest --cov=app --cov-report=term-missing` — target ≥ 85 % **meaningful** coverage; add behavior tests for uncovered branches (not trivial asserts).
3. Run the entire suite against Postgres: `TEST_DATABASE_URL=<dev/neon branch> pytest` ⇒ green.
4. `ruff format` + `ruff check` clean; remove dead code; confirm no secrets/`.env` committed; confirm `.env.example` complete.
5. Performance note: run a 500-recipient job locally; record total time and mean PDF size for the README.
6. Review error responses for consistency; ensure no stack traces leak in 500s (add a generic exception handler returning `{"detail":"Internal server error"}` + logging).
7. Fresh-clone rehearsal: new venv → install → `pytest` → run app. Fix anything that breaks.

**Mandatory-area map:**

| Assignment area | Tests |
|---|---|
| Creating a generation job | `test_jobs.py` |
| Input validation | `test_validation.py`, `test_jobs.py` (422/recipient failures) |
| Certificate generation | `test_generation.py`, `test_processing.py` |
| Job status/progress | `test_jobs.py`, `test_processing.py` |
| Individual certificate failure | `test_processing.py`, `test_retry.py` |
| Retrieving certificates | `test_certificates.py` |
| Extras | `test_retry.py`, `test_verify.py`, `test_recovery.py`, idempotency in `test_jobs.py` |

**Acceptance:** all green on SQLite and Postgres; fresh-clone rehearsal passes.

---

### PHASE 10 — Documentation & Postman (~2 h)

**Goal:** a reviewer can run, test and understand everything in 10 minutes.

**Tasks**
1. `README.md` with these sections, in order: **Overview & positioning line · Live demo URL (placeholder until Phase 11) · Features/USPs · Quick start (clone, venv, install, `.env`, DB setup for Neon/Docker/native, run) · Running tests (SQLite default; Postgres option) · Environment variables table · API reference (every endpoint with curl + sample response) · Submitting a request (full example) · Retrieving certificates (single, list, ZIP) · 60-second demo (fail → retry) · Architecture (Mermaid sequence/flow diagram) · Processing flow · Database design (ERD in Mermaid) · Background-processing approach & why not Celery · Error handling & failure types · Idempotency strategy · Retry strategy · Self-healing storage & crash recovery · Design decisions & alternatives (from §4) · Test coverage map · Performance notes · Deployment notes (free-tier caveats) · Learnings · Future scope.**
   - **Learnings:** honest, specific (e.g., BackgroundTasks lifecycle, per-task sessions, deterministic PDFs, free-tier constraints).
   - **Future scope:** Celery/RQ + Redis, `Idempotency-Key` header, Alembic migrations, S3/R2 storage, CSV upload endpoint, API-key auth & rate limiting, webhooks/email delivery, multiple templates, HTML verification page, per-tenant isolation, metrics.
2. `postman/bulk-certificate-generator.postman_collection.json`: variable `base_url`; requests for every endpoint; test scripts that store `job_id` / `certificate_id` into collection variables; includes the demo flow.
3. Finalize `docs/INTERVIEW_NOTES.md` with the Appendix 12.2 Q&A adapted to the actual code (file/function names).
4. Make sure every code block/command in the README was actually executed by the agent.

**Acceptance:** owner follows the README on a clean folder and succeeds; Postman collection imports and the full flow passes.

---

### PHASE 11 — Deployment: GitHub + Neon + Render, all free (~2 h)

**Goal:** live Swagger URL + public repo.

**Owner steps (agent provides exact click-by-click and verifies each):**
1. **GitHub:** create a **public** repo; agent runs `git remote add origin …`, `git push -u origin main --tags`. Confirm no secrets in history (`git log -p` scan for `DATABASE_URL`/passwords).
2. **Neon:** create project (region closest to Render's); copy the connection string; convert to `postgresql+psycopg2://…?sslmode=require`.
3. **Render:** New → Web Service → connect the repo → Runtime **Python** → Build `pip install -r requirements.txt` → Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT` → Plan **Free** → Health check path `/health`.
   Env vars: `DATABASE_URL`, `ENVIRONMENT=production`, `STORAGE_DIR=/tmp/certificates`, `MAX_RECIPIENTS_PER_JOB=500`, `ENABLE_DEMO_FAILURES=true`, `PYTHON_VERSION=3.12.x`, `PUBLIC_BASE_URL` (set after the first deploy to `https://<service>.onrender.com`, then redeploy).
4. Verify current free-tier limits on the Render/Neon dashboards before relying on them (they change): expect spin-down after inactivity (first request after sleep is slow), ephemeral filesystem, limited DB storage/compute hours.

**Agent tasks**
1. `scripts/smoke_test.py --base-url …`: health → create job (incl. 1 invalid + 1 `FAILME`) → poll to completion → list → download one → ZIP → retry → verify → asserts; prints PASS/FAIL per step. Run it locally first, then against the live URL.
2. Confirm production logging, no debug flags, `/docs` enabled.
3. Update README: live URL, "first request may take ~1 min (free tier sleeps)", demo flow against the live URL, the smoke test.
4. Add the live URL to the GitHub repo "About" section.

**Acceptance (live):**
- `https://<service>.onrender.com/docs` loads; smoke test passes.
- **Restart/redeploy the service, then download an existing certificate → still works** (self-healing proven on ephemeral disk).
- Submit a job, wait for sleep or restart mid-processing → job resumes and completes (crash recovery) — if reproducible; otherwise document tested locally.
- Public repo link opens without login; README renders correctly (Mermaid included).

**Final deliverables to submit:** public GitHub URL, live `/docs` URL, Postman collection (in repo).

---

## 12. Appendices

### 12.1 Final Definition-of-Done checklist

- [ ] All six mandatory test areas pass; extras pass; suite passes on SQLite **and** Postgres
- [ ] README complete incl. sync-vs-async reasoning, **Learnings**, **Future scope**
- [ ] Postman collection committed and working
- [ ] Certificate visually approved (calibration, stress cases, QR)
- [ ] Fail → retry demo works locally and live
- [ ] Idempotent replay, crash recovery, self-healing demonstrated
- [ ] No secrets in repo/history; `.env.example` complete
- [ ] Public repo + live Swagger URL
- [ ] `docs/INTERVIEW_NOTES.md` reviewed by the owner (can explain every file)

### 12.2 Interview pack (keep updated in `docs/INTERVIEW_NOTES.md`)

1. **Why BackgroundTasks, not Celery?** Simplicity and free hosting; all state in Postgres; worker is replaceable; crash recovery covers restarts; trade-off: no horizontal scaling/guaranteed delivery.
2. **What if the server restarts mid-job?** Certificates are only marked on completion; on startup `recover_interrupted_jobs` resumes PENDING ones.
3. **How does idempotency work? What if two identical requests arrive simultaneously?** Hash of normalized content, unique index; loser gets `IntegrityError`, re-queries, returns the winner's job.
4. **Why store counters if you can compute them?** Cheap reads for polling; recomputed from rows after each certificate so they can't drift.
5. **Why are some failures non-retryable?** Retrying deterministic data errors never succeeds; typed failures make retry meaningful.
6. **How do you avoid regenerating successes on retry?** Retry only selects `FAILED/GENERATION` rows; tests assert unchanged attempts/files.
7. **Render's disk is ephemeral — how do certificates persist?** DB is the source of truth; PDFs are deterministic; missing file → regenerate on demand.
8. **Why random IDs?** Public endpoints without auth; sequential IDs are enumerable.
9. **Why separate DB session in the worker?** Request session closes when the response is sent; each worker owns its lifecycle.
10. **How would you scale to 100k recipients?** Queue + workers (Celery/RQ), object storage, batch inserts, chunked progress, pagination everywhere (already), rate limits.
11. **Changed requirement drills (where to edit):** add a second template → `layout.py` + `template_id` column; allow duplicate emails → delete `DUPLICATE_ROW` rule in `validation.py`; email certificates → new service called from `process_job` after SUCCESS; new certificate ID format → `utils/ids.py`; require auth → dependency on routers; Celery → replace `add_task` line with `.delay()` and keep `process_job` body; change date format → one line in generator.
12. **What would you improve?** Alembic, S3, `Idempotency-Key`, auth/rate limiting, metrics, webhooks.

### 12.3 Risks & mitigations

| Risk | Mitigation |
|---|---|
| Render free spin-down interrupts a job | Startup recovery (U4); status polling keeps the instance warm; documented |
| Ephemeral disk wipes PDFs | Self-healing regeneration (U5) |
| Neon scale-to-zero causes first-query errors | `pool_pre_ping`, `pool_recycle` |
| Slow PDFs on a tiny free CPU | 500-recipient cap in prod, per-certificate commits so progress is still visible, performance numbers documented |
| Template coordinates off | Calibration PDF + owner sign-off gate in Phase 3 |
| Fonts unavailable offline | Fonts committed to repo (OFL) |
| Variable fonts break ReportLab | Use static TTFs only |
| Owner can't explain code | Phase gating, Phase Reports, `INTERVIEW_NOTES.md`, small functions |
| Scope creep | §1.4 boundaries; stretch ideas live only in README Future scope |

---

**End of PRD. Agent: begin with Phase 0, confirm prerequisites with the owner, and stop after the Phase 0 report.**
