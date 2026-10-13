# Error handling adoption — ozon-product-parser

Audit: 2026-10-13; integration baseline `main` at `fc470274870c744091662ab11890249b6525b688`.
Status: **policy proposal; runtime changes not implemented in this PR**.
This is a scoped audit of the listed files, not a complete error/client inventory.

## Baseline

Python 3.12 CLI/browser/parser/Airflow project, not an inbound HTTP API. client.py raises generic ValueError/FileNotFoundError and lets Requests HTTP errors propagate. airflow_task.py validates SKU with ValueError and runs the parser subprocess with check=True. No AGENTS.md existed. A typed failure catalog and explicit terminal/retryable classification remain pending.

Observed locations: src/ozon_parser/client.py; src/ozon_parser/airflow_task.py; scripts/parse_ozon.py; scripts/get_cookies.py.

## Adapted mandatory target

[Shared Error Handling Standard 1.0.0](error-handling-standard.md):
**Typed Domain/Application Exceptions + Centralized Exception Translation**.

Use parser-owned typed application errors and central CLI/worker translation with stable safe codes. Preserve existing CLI exit semantics and client tests before migration. Airflow owns bounded retries; keep terminal auth/session/CAPTCHA/operator-action failures distinguishable from transient network failures. Do not add HTTP status fields to worker errors or create an unnecessary FastAPI app.

Retain locked Python >=3.12,<3.13 and existing browser/Gmail/DB boundaries. Never echo cookies, Gmail/OAuth tokens, OTPs, response bodies or credentials. Live browser/Ozon/Gmail/PostgreSQL acceptance is not performed by a docs PR. No canonical full gate was found in the inspected tree; establish one separately before claiming full acceptance.

## Compatibility and privacy

Preserve current statuses, JSON/HTML/CLI contracts, messages/field keys, auth/retry/security headers and OpenAPI where present.
No forced JSON/RFC 9457 conversion. Contract changes require a separate owner-approved task.
No cross-repository runtime dependency. Redact secrets; validate/bound correlation identifiers; never suppress cancellation or cleanup failure.
Unknown HTTP failures must remain safe 500; workers retain explicit terminal/retryable/unknown outcomes.

## Pending work and acceptance

Complete the class/raise-site/client/status/body/header or CLI-exit table first.
Add failure/contract/secrecy regression tests, then minimally adapt the existing architecture.
Add AST-aware transport import checks where meaningful. Preserve every existing test and gate.
Run the actual locked checks and real integrations before exact-SHA acceptance.

Existing check commands / applicable verification:

```bash
uv sync --locked
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

Checks have not run for this docs-only proposal. Docker/live-provider validation remains unverified.
Keep PR Draft; owner approval and applicable local Quality Gate on final SHA are required before merge.
No CI workflow changes.
