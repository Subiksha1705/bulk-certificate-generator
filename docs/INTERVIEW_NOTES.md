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
