# Bulk Certificate Generator — Interview Study Guide & Architecture Notes

This document is your living study guide for the Bulk Certificate Generator project. It documents the core architectural decisions, data models, state machines, and interview questions with answers for each completed phase.

---

## Phase 0: Environment, Scaffolding & Project Foundation

### 1. What was built
- Project repository structure with modular packaging (`app/models`, `app/schemas`, `app/routers`, `app/services`, `app/utils`, `app/assets`).
- Virtual environment setup pinned to Python 3.12 with development and runtime dependencies pinned in `requirements.txt` and `requirements-dev.txt`.
- Application configuration via `pydantic-settings` with environment variable loading and `.env.example` reference.
- Base FastAPI application instance with lifespan management stub and a `/health` liveness endpoint.
- Certificate template assets (`app/assets/template/certificate_template.png`, dimensions: 2000 × 1414 px) and static Google Fonts (Lora, Great Vibes) under SIL Open Font License.
- Pytest test runner configuration with health endpoint validation (`tests/test_health.py`).

### 2. Why these choices were made
- **Python 3.12 & Type Annotations:** Provides modern type checking, performance gains, and compatibility with FastAPI and SQLAlchemy 2.0.
- **Pydantic Settings:** Enables type-safe configuration with automatic parsing of environment variables, defaults, and casting.
- **Modular Directory Layout:** Separates concerns strictly into routers (HTTP/routing only), services (business logic), models (DB persistence), schemas (validation/DTOs), and assets.
- **Static TTF Fonts:** ReportLab requires static non-variable TrueType fonts for reliable PDF font rendering and glyph extraction.
- **Pre-verified Template Image:** Reading template pixel dimensions with Pillow ensures layout coordinates map accurately to PDF points during rendering.

### 3. How it works
- The FastAPI application is initialized in `app/main.py` using an async lifespan context manager.
- Configuration is loaded via `app/config.get_settings()`, which caches the parsed `Settings` instance using `functools.lru_cache`.
- Incoming health check requests to `/health` return HTTP 200 with `{"status": "ok"}` without hitting database layers (database connectivity checks are attached in Phase 1).

### 4. Likely Interview Questions & Answers

#### Q1: Why structure the codebase with separated `routers/` and `services/` layers?
**Answer:**
Separating routers from services ensures strict separation of concerns. Routers handle HTTP-specific concerns like request routing, status codes, query parameters, and background task dispatch. Services encapsulate pure business logic and database operations, remaining completely decoupled from FastAPI or HTTP request contexts. This makes the business logic modular, independently testable with unit tests, and easily reusable (e.g., from CLI scripts or background workers).

#### Q2: Why use `pydantic-settings` instead of `os.environ.get()` or a raw dictionary?
**Answer:**
`pydantic-settings` validates configuration types at startup (e.g., ensuring `MAX_RECIPIENTS_PER_JOB` is an integer and `RECOVER_ON_STARTUP` is a boolean), provides default fallbacks, handles `.env` files automatically, and fails fast if required settings are missing or invalid before the app starts serving traffic.

#### Q3: Why are static TTF fonts bundled directly in the repository rather than downloaded at runtime?
**Answer:**
Bundling the SIL OFL-licensed static fonts ensures deterministic, reproducible PDF generation in all environments (local, CI/CD, and production container/serverless environments like Render). Variable fonts or dynamic runtime downloads can fail due to network restrictions, rate limiting, or font rendering incompatibilities with ReportLab.

---

## Phase 1: Database Layer, ORM Models & Unguessable IDs

### 1. What was built
- Configured SQLAlchemy 2.0 database engine in [app/database.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/database.py) with connection recycling (`pool_recycle=300`) and pre-ping (`pool_pre_ping=True`) for Neon/Postgres, plus automatic fallback for SQLite in-memory tests (`StaticPool`).
- Implemented ORM models in [app/models/job.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/models/job.py) (`GenerationJob`) and [app/models/certificate.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/models/certificate.py) (`Certificate`) using SQLAlchemy 2.0 type-annotated style (`Mapped[...]`, `mapped_column`), string enums, indexed foreign keys, and cascading delete relationships.
- Defined domain enums in [app/models/enums.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/models/enums.py) (`JobStatus`, `CertificateStatus`, `FailureType`).
- Implemented cryptographically secure, unguessable ID generation in [app/utils/ids.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/utils/ids.py) (`JOB-YYYY-XXXXXXXX` and `CERT-YYYY-XXXXXXXX`) using a 32-character unambiguous Base-32 alphabet (`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`).
- Wired automatic database schema creation (`Base.metadata.create_all`) into FastAPI lifespan and updated `GET /health` to perform active `SELECT 1` database health validation.
- Built comprehensive test suite in [tests/test_models.py](file:///Users/subiksharamesh/bulk-certificate-generator/tests/test_models.py) and [tests/test_health.py](file:///Users/subiksharamesh/bulk-certificate-generator/tests/test_health.py) with isolated test databases.

### 2. Why these choices were made
- **Unguessable IDs as Primary Keys:** Sequential IDs (e.g. `CERT-1`, `CERT-2`) allow unauthorized users to scrape certificates and recipient names by enumerating endpoints. 8 random characters from a 32-character alphabet provides over 1 trillion combinations ($32^8 \approx 1.1 \times 10^{12}$ per year), making brute-force scanning infeasible while eliminating ambiguous characters (`0`, `O`, `1`, `I`).
- **SQLAlchemy 2.0 `Mapped` Syntax:** Eliminates legacy string-based column definitions, giving complete IDE autocomplete, static type checking with Mypy/Pyright, and cleaner code.
- **`native_enum=False`:** Storing enums as VARCHAR strings rather than PostgreSQL native enum types avoids complex database migrations when enum values change and enables seamless SQLite compatibility for local/in-memory unit tests.
- **Pre-ping & Connection Recycling:** Serverless PostgreSQL (such as Neon free tier) closes idle connections aggressively when scaling to zero. `pool_pre_ping=True` and `pool_recycle=300` prevent stale connection errors on incoming requests.

### 3. How it works
- When the FastAPI application starts up, `Base.metadata.create_all(bind=engine)` creates the `generation_jobs` and `certificates` tables and their indexes if they do not already exist.
- Each `GenerationJob` has a one-to-many relationship with `Certificate`, ordered by `row_number` and configured with `cascade="all, delete-orphan"`.
- `/health` checks database connectivity with `db.execute(text("SELECT 1"))`. If the database is responsive, it returns HTTP 200 `{"status": "ok", "database": "ok"}`; on database failure, it catches the error and returns HTTP 503 `{"status": "error", "database": "error"}`.

### 4. Likely Interview Questions & Answers

#### Q1: Why use random 8-character string primary keys instead of auto-incrementing integers or UUIDv4?
**Answer:**
Auto-incrementing integers create an enumeration vulnerability for public endpoints (such as public certificate verification and download). Anyone could iterate through `CERT-1`, `CERT-2` to scrape recipient names and organization details. Standard UUIDv4 strings are 36 characters long, awkward to print on certificates or read aloud. An 8-character string from an unambiguous 32-character Base-32 alphabet ($32^8 \approx 1.1 \times 10^{12}$ combinations) provides high unguessability, fits cleanly on paper certificates, omits easily confused characters like `0/O` and `1/I`, and serves directly as the primary key without an extra translation table.

#### Q2: Why configure `native_enum=False` for SQLAlchemy Enum columns?
**Answer:**
Native PostgreSQL ENUM types require specific DDL statements (`ALTER TYPE ... ADD VALUE`) to modify and are not natively supported by SQLite. Using `native_enum=False` stores the enum value as a standard `VARCHAR` column with validation handled at the Python/application layer. This allows the same codebase and test suite to run seamlessly across in-memory SQLite for fast unit testing and PostgreSQL in production without database migration friction.

#### Q3: How do `pool_pre_ping` and `pool_recycle` prevent errors on serverless databases like Neon?
**Answer:**
Neon automatically scales idle database computes to zero to save resources, closing existing TCP sockets. If the application holds a pool of stale connections, the next incoming query would fail with a `BrokenPipeError` or `OperationalError`. `pool_pre_ping=True` issues a lightweight `SELECT 1` before checking out a connection from the pool, silently refreshing dead sockets. `pool_recycle=300` proactively retires connections older than 5 minutes.

---

## Phase 2: Input Schemas, Validation & Request Fingerprinting

### 1. What was built
- Pure validation engine in [app/services/validation.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/services/validation.py) validating individual recipient names and emails (`NAME_REQUIRED`, `NAME_TOO_SHORT`, `NAME_TOO_LONG`, `NAME_INVALID_CHARS`, `EMAIL_REQUIRED`, `EMAIL_INVALID`) and detecting case-insensitive duplicate rows (`DUPLICATE_ROW`).
- Pydantic v2 schemas in [app/schemas/job.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/schemas/job.py) and [app/schemas/certificate.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/schemas/certificate.py) for request payloads (`JobCreate`, `RecipientIn`) and responses (`JobOut`, `JobCreateResponse`, `CertificateOut`, `CertificateListOut`, `VerifyOut`).
- Deterministic request fingerprinting engine in [app/services/fingerprint.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/services/fingerprint.py) calculating SHA-256 request hashes invariant to recipient sorting or case/whitespace variations.
- Unit test suite in [tests/test_validation.py](file:///Users/subiksharamesh/bulk-certificate-generator/tests/test_validation.py) and [tests/test_fingerprint.py](file:///Users/subiksharamesh/bulk-certificate-generator/tests/test_fingerprint.py) covering all validation bounds, regexes, duplicates, and hash invariances.

### 2. Why these choices were made
- **Dual Validation Boundary:** Structural errors (missing payload fields, non-object recipient items, date out of bounds) fail fast with HTTP 422. Recipient data quality errors (invalid email format, blank names, duplicate rows) do NOT reject the whole batch; they are recorded per recipient as `FAILED/VALIDATION` so valid certificates are never blocked.
- **Pure Functions Without Side Effects:** Writing validation and fingerprinting as pure functions (zero DB and zero HTTP dependencies) guarantees 100% deterministic, high-speed unit testing.
- **Order-Insensitive Content Hashing:** Sorting normalized `(casefold_name, casefold_email)` pairs before SHA-256 hashing guarantees that resubmissions with rearranged recipient rows are recognized as identical requests for idempotency.
- **`extra="forbid"` on JobCreate:** Catches client field typos (e.g. `date` instead of `event_date`) immediately at the HTTP boundary before database ingestion.

### 3. How it works
- `JobCreate` validates job metadata (length bounds, date ranges) and parses `recipients: list[RecipientIn]`.
- `validate_recipients()` iterates through recipients, normalizes names and emails, validates constraints, detects duplicate rows using a hash set, and produces `RecipientCheck` objects with error details.
- `compute_request_hash()` builds a canonical dictionary of normalized job metadata and sorted recipient tuples, converts to compact JSON (`separators=(',', ':')`), and computes a 64-character SHA-256 hex digest.

### 4. Likely Interview Questions & Answers

#### Q1: What is the difference between job-level validation and recipient-level validation?
**Answer:**
Job-level validation enforces structural requirements (e.g., valid ISO event date, non-empty recipient list, required event/organization names). If any job-level rule fails, FastAPI rejects the entire request with HTTP 422. In contrast, recipient-level validation isolates individual data problems (such as a malformed email or duplicate row). Rather than aborting the entire batch of 500 recipients because of one typo, invalid recipients are recorded as `FAILED` with `failure_type = VALIDATION` and specific error messages, while valid recipients proceed to certificate generation.

#### Q2: How does the request fingerprinting algorithm guarantee idempotency even if recipient rows are reordered?
**Answer:**
`compute_request_hash()` extracts each recipient as a normalized, case-folded pair `(name, email)`. Before serializing the payload to canonical JSON, the list of recipient pairs is sorted lexicographically. This ensures that two requests with identical content in different orders produce identical JSON strings, resulting in the exact same SHA-256 hash.

#### Q3: Why normalize strings before hashing and validation?
**Answer:**
Client applications and user copy-pasting often introduce invisible whitespace noise, leading/trailing spaces, or varying capitalization (`SUBIKSHA@EXAMPLE.COM` vs `subiksha@example.com`). Normalizing text (stripping surrounding whitespace, collapsing internal multi-spaces, and case-folding emails) ensures consistent validation, prevents duplicate row false-negatives, and ensures accurate idempotency deduplication.

---

## Phase 3: PDF Generation, Visual Calibration & Glyph Fitting

### 1. What was built
- Decoupled coordinate and layout system in [app/services/layout.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/services/layout.py) mapping template top-left pixels (2000 × 1414 px) to A4 landscape PDF points (841.89 × 595.28 pt) with field-specific bounds (`FieldSpec`).
- Deterministic ReportLab PDF generator in [app/services/certificate_generator.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/services/certificate_generator.py) with static TTF font registration, cached background template rendering, metadata injection, and `invariant=1` deterministic byte generation.
- Dynamic font size auto-fitting and glyph inspection (`check_glyphs()`, `fit_font_size()`) that verifies character coverage in the font face and gracefully steps down font sizes (1 px per step) until text fits within field max widths, raising typed non-retryable exceptions (`UnsupportedCharacterError`, `TextOverflowError`).
- PDF rendering and calibration script in [scripts/render_sample.py](file:///Users/subiksharamesh/bulk-certificate-generator/scripts/render_sample.py) creating sample, calibration (100px grid, baseline ticks, dashed max-width boxes), and stress test PDFs.
- Pytest suite in [tests/test_generation.py](file:///Users/subiksharamesh/bulk-certificate-generator/tests/test_generation.py) (43 total passing tests).

### 2. Why these choices were made
- **Template Pixel Coordinates:** Specifying layout coordinates in template image pixels (origin top-left) rather than raw PDF points makes visual calibration intuitive: developers can measure exact pixel positions directly from graphic design tools (Canva/Photoshop) without manually computing PDF math.
- **Deterministic PDF Generation (`invariant=1`):** Enabling ReportLab's `invariant=1` removes runtime timestamps and non-deterministic object IDs from PDF byte streams. Identical input always produces byte-identical PDFs, enabling the self-healing storage architecture (Phase 6) to regenerate missing files safely.
- **Glyph Verification Before Rendering:** Checking `font.face.charToGlyph` catches unsupported emojis or non-Latin glyphs before ReportLab renders missing character boxes (`.notdef`), classifying them as non-retryable `VALIDATION` errors.
- **Dynamic Auto-Shrink Font Fitting:** Stepping font size down to `min_px` ensures that long names (e.g. 40–50 characters) shrink gracefully to fit their designated lines instead of clipping or overlapping borders.

### 3. How it works
- `TemplateLayout` scales pixel dimensions by `PAGE_HEIGHT_PT / template_height_px` (≈ 0.421) and transforms the Y-axis (`pdf_y = PAGE_HEIGHT_PT - (pixel_y * scale)`).
- When `generate_certificate_pdf()` is called, it loads the cached template image, draws it over the canvas, and loops through the field specifications.
- Each text string is checked for glyph support and measured using `pdfmetrics.stringWidth`. If the text exceeds the field's `max_width_px`, the font size is iteratively reduced until it fits or reaches `min_px`.
- The PDF is finalized to an in-memory byte buffer and returned.

### 4. Likely Interview Questions & Answers

#### Q1: How does the system ensure generated PDFs are 100% deterministic?
**Answer:**
ReportLab normally includes creation timestamps, file modification times, and random document ID hashes inside the PDF catalog dictionary. By setting `canvas.Canvas(..., invariant=1, pageCompression=1)` and avoiding any dynamic timestamps in rendering, two generation calls for the same certificate produce byte-for-byte identical binaries. This is critical for self-healing storage: if a PDF is deleted or lost on ephemeral cloud storage (e.g. Render), the server can regenerate the exact same file on demand.

#### Q2: What happens when a recipient name is very long or contains special characters?
**Answer:**
1. **Character Check:** The text is first checked against the font's glyph mapping (`font.face.charToGlyph`). If unsupported characters (e.g. emoji or unsupported scripts) are present, `UnsupportedCharacterError` is raised.
2. **Auto-fit:** If glyphs are supported, `fit_font_size` measures the text width in PDF points. If it exceeds `max_width_px`, font size steps down 1 px at a time until it fits or reaches `min_px`.
3. **Overflow Guard:** If the text still exceeds max width at `min_px`, `TextOverflowError` is raised. Both exceptions inherit from `CertificateDataError` and are marked as non-retryable `VALIDATION` failures.

#### Q3: How do you handle changing or resizing the certificate template background image?
**Answer:**
All coordinate specifications live in [app/services/layout.py](file:///Users/subiksharamesh/bulk-certificate-generator/app/services/layout.py) in template pixels. `TemplateLayout` automatically inspects the template image dimensions via Pillow on startup and dynamically scales all pixel coordinates to A4 landscape PDF points. Changing the template design or dimensions requires updating numeric coordinates in `layout.py` without touching any rendering or business logic.



