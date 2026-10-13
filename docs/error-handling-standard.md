# Shared Error Handling Standard 1.0.0

Status: **proposal, not yet rolled out**. Scope: active Python backend and worker
projects owned by the platform. Adoption is **per repository** after reviewing
that repository's existing API contracts; this file does not change runtime
behavior by itself.

## 1. Pattern and source evidence

Architectural name: **typed application/domain exceptions + exception
translation at the transport boundary + centralized exception mapping**.
Related ideas: Ports and Adapters / Clean Architecture, Exception Translation,
and the FastAPI exception-handler registry. The goal is a **single failure
policy**, not an exception-handling business service.

Observed reference implementations (not to be copied verbatim):

- `HageGyakutai/DevJobs`: `src/devjobs/services/exceptions.py` contains
  `DevJobsDomainError` and specialized lookup/integration exceptions;
  `apps/api/routers/frontend.py` converts known service errors to stable UI
  codes/statuses; `apps/api/errors/frontend.py` supplies an error envelope and
  HTTP/validation handlers; `apps/api/main.py` registers handlers.
  `tests/contracts/test_http_exception_boundary.py` checks the layer boundary.
  **Important:** mapping is partly still inside routers; frontend and legacy
  endpoints have different response formats.
- `HageGyakutai/hvpn-bot`: `application/errors.py` defines application
  exceptions; `web/exception_handlers.py` has a centralized mapping of
  exception types to status/code/safe detail, and `web/schemas/errors.py`
  includes a request ID. Registered once in `web/app.py`.
- `hage-vpn/services/auth-service`: application exception types already
  exist, but multiple routers repeat `try/except` -> `HTTPException`.
- `auth-service-template`: has a password/domain exception family and
  centralized SQLAlchemy/422 redaction handlers; must preserve their behavior.

The shared contract combines the best **boundaries**, not an identical
module layout or a blind copy of a project's response JSON.

## 2. Required responsibility boundaries

```text
Domain / Application
    raises typed domain/application errors (no HTTP or FastAPI)
        |
        v
Transport exception mapping (FastAPI adapter, installed at app startup)
    maps a known error class to status + stable machine code + safe public text
        |
        v
Versioned HTTP contract + request_id

Infrastructure adapter: provider/DB/client-specific failure
    -> typed application/integration failure when expected
    -> the same transport mapper (or unexpected failure fallback)
```

- Business policy lives in domain/use cases; transport is not imported there.
- Ports must document failure semantics and adapter mapping where needed.
- Routers should call use cases and return DTOs; avoid repeated `try/except`
  mapping for **known application errors** when a centralized mapping can cover
  them. Transport-only security/HTTP checks may remain at the API boundary.
- Application errors are typed exceptions, not HTTP responses or sentinel
  `{"success":false}` dictionaries.
- Each bounded context owns its own error catalog and error mapping. Do not
  import another microservice's internal Python exceptions.
- A central **policy document** is shared; a mandatory `shared-errors`
  runtime dependency or global exception class across services is **not**
  required. Keep service deployment independent.

Suggested minimal layout (adapt existing structure, do not require renames):

```text
src/<service>/services/exceptions.py         # or domain/errors.py
src/<service>/api/errors/catalog.py           # code/status/public message mapping
src/<service>/api/errors/handlers.py          # HTTP / validation / fallback
src/<service>/api/schemas/errors.py           # versioned response schema
src/<service>/main.py                         # register handlers exactly once
tests/contracts/test_error_contract.py
tests/contracts/test_http_exception_boundary.py
```

## 3. Error taxonomy and mapping

Define an `ApplicationError` (or retain an established existing base), with
explicit child types for expected failure cases. Example **categories**:

| Category | Meaning | Typical HTTP behavior |
| --- | --- | --- |
| NotFound | Resource absent or hidden from another owner | 404 |
| Conflict | Duplicate, illegal state, version/idempotency race | 409 |
| Authentication | Missing, bad, expired or untrusted credentials | 401 |
| Authorization | Authenticated but not permitted | 403, sometimes 404 for owner isolation |
| InvalidDomainState | Valid schema, rejected business rules | 400/409/422 as **existing contract** requires |
| RateLimited | Bounded abuse/retry policy | 429 (+ safe Retry-After where specified) |
| DependencyUnavailable | Expected external provider/DB/cache outage | 503/502, by contract and dependency role |
| Unexpected | Unknown bug, unmapped exception | 500 with **generic** message |

**Do not infer a status from an exception's text, arbitrary subclass name,
or a generic status-code property passed from the domain.** Use an explicit,
auditable mapping of **known class -> immutable public error specification**.
Unknown application subclasses fail to a sanitized 500 until reviewed.
Do not expose `str(exc)` by default.

Use stable namespaced machine-readable codes, e.g.
`auth.invalid_credentials`, `auth.refresh_invalid`,
`billing.idempotency_conflict`. The code is part of the contract:
clients must branch on code, **not** localized title/detail or class name.
Keep codes stable; create new codes for semantic changes. Avoid account
enumeration by intentionally using the same public code/message for errors
that must be indistinguishable.

A public error mapping may also specify required safe response headers
(`WWW-Authenticate`, `Retry-After`), but never arbitrary exception-supplied
headers or values without validation.

## 4. HTTP payload versioning — compatibility first

The **mandatory common invariant** is a stable code, correct HTTP status,
sanitized public message, documented schema and correlation/request ID where
the active contract permits. **Do not blindly rewrite existing responses.**

For **new versioned APIs** prefer the interoperable RFC 9457
Problem Details contract (`application/problem+json`), with a service-owned
`type` URI, `title`, `status`, safe `detail`, and extensions `code` and
`request_id`:

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "This operation conflicts with the current state.",
  "code": "example.operation_conflict",
  "request_id": "req-8b62"
}
```

The `about:blank` type in this example is generic; stable documented
problem-type URIs may be introduced later. `instance` should be used only
when the representation is safe for the particular deployment.

Existing contracts may use different formats:

- DevJobs Product UI uses `{"error":{"code","title","message","action"?}}`.
- HVPN Bot API uses `{"error_code","detail","request_id"}`.
- Current Auth endpoints frequently return `{"detail":...}`, including
  security-sensitive and legacy client contracts.
- Some internal API health/readiness or Telegram contracts use different
  schemas.

Retain those formats on existing versions until clients and versioned
contracts are migrated. A local mapper can use the same **internal catalog**
while serializing a different **public response profile**; never infer
compatibility from successful status codes alone. Do not require a UI
`action` object on non-UI APIs.

## 5. Request IDs, logging and privacy

- Establish or reuse a trusted `request_id` once per inbound HTTP request.
  Do not blindly trust arbitrary user-supplied correlation IDs. Bound length
  and format before trusting external identifiers; provide a generated ID
  otherwise.
- Include request ID in logs. Expose it in a response/header only where the
  relevant API contract allows; preserve existing response semantics.
- Expected client errors: one concise, structured INFO/WARNING as warranted;
  never log user passwords, credentials, access/refresh/verification tokens,
  provider secrets, raw HTTP bodies, PII or SQL bind parameters.
- Unexpected failures: one safe ERROR with internal correlation ID/trace
  according to the production logging policy; return sanitized 500.
  Log traces only to controlled sinks, never HTTP clients.
- Handle validation errors without echoing Pydantic `input` or submitted
  secret fields. Response details should use safe field locations/error
  categories, with secrets filtered; validate safe field names too.
- Use `Cache-Control: no-store` for auth/security/private error responses
  and preserve CORS/security headers where relevant.
- Do not catch `BaseException` and swallow cancellation/shutdown signals.
  Keep `ExceptionGroup`/worker cancellation semantics intact.

## 6. Delivery-specific behavior

**FastAPI:** register application error, transport HTTP and validation
handlers in one composition point. For unknown failures rely on a tested safe
500 policy; production must not return tracebacks. Preserve status, content
type, safe headers and response profiles; special-case health/readiness only
when already contracted.

**Worker/Celery/Airflow:** no HTTP status mapping inside tasks. Translate
expected failures to typed outcomes with explicit retryability, exponential
backoff only for safe operations, idempotency and dead-letter/final failure
semantics. Do not classify an arbitrary exception as retryable by message.
One operation should generate one clear failure record, not stack traces
repeated independently by every layer.

**Inter-service HTTP:** adapters map remote status/provider error to stable
local application errors and preserve correlation IDs; do not blindly relay
remote error bodies or secret-bearing provider responses to callers.

## 7. Mandatory tests and architecture gates

For each adopted service:

1. Test the hierarchy: domain/application has no FastAPI/Starlette or HTTP
   transport imports; routers/use cases remain thin.
2. Enumerate known error classes and assert **every** class is explicitly
   mapped to the intended code/status/public message. Verify unmapped types
   produce sanitized 500 (and are logged safely).
3. Test API client-visible shape, content-type, response headers and stable
   error codes **for every existing contract/profile**. Do not unexpectedly
   change `detail`/status/body for older endpoints.
4. Test 400/401/403/404/409/422/429/503, as applicable: wrong/expired
   credentials, nonexistent or foreign-owned resources, input validation,
   provider outage, rate-limit and retry-header behavior.
5. Test that passwords, JWTs, cookies, verification codes, API keys, DB
   exceptions, submitted malformed values and SQL statements do not leak
   through HTTP errors/logs. Test generic 500 and request ID traceability.
6. Worker paths (when present): test retry classification, cancellation,
   idempotency and final failure visibility.
7. Run the **repository's existing** Ruff formatter/linter, MyPy,
   unit/contract/integration checks, and its canonical full Quality Gate.
   Do not replace or weaken any established gate.

A static `HTTPException` import boundary test is a useful guard, but prefer
AST-aware checks over brittle string searches. Allow transport boundary
modules (`api/errors`, `api/routers`, middleware) explicitly.
Tests must flag drift between catalog, docs/OpenAPI and actual response shape.

## 8. Safe adoption plan

1. **Inventory** the current service's exception classes, HTTP error formats,
   status codes, headers, logging/correlation and client consumers.
2. **Documentation first:** identify existing contracts and explicit non-goals.
3. Add a typed central mapper and API handler **without changing wire format**.
   Keep the old endpoint behaviors until new contract versions are approved.
4. Refactor repeated router mappings incrementally, one bounded context per
   PR. Do not hide unknown bugs by mapping every exception to 200 or 400.
5. Add contract/security/regression tests and architecture guard.
6. Run exact-commit local full Quality Gate. Merge only after explicit project
   owner approval, respecting each repository's CI minute-saving rules.
7. Add a **short pointer** to this standard in each repository's `AGENTS.md`
   (or equivalent agent instruction); for projects with no `AGENTS.md`,
   establish one before claiming agent enforcement.

Start with **Auth in hage-vpn** as the pilot (strict backward compatibility).
Then consider `auth-service-template`, `hvpn-bot`, DevJobs and remaining
active API/worker repositories independently. Documentation alone is
**not** evidence that runtime code was migrated in every repository.

## 9. Definition of done

A repository is compliant only after: documented error catalog; explicit
domain-to-transport mapping; safe stable client response; validation redaction;
request correlation appropriate to its API; unit/contract/security tests;
architecture checks; agent rule referring to this version; and final
repository-specific full Quality Gate. Global rollout requires a maintained
per-repository acceptance list; never claim "all projects" from a
single documentation PR.
