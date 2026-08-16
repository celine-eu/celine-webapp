# Development

## Prerequisites

- Python >= 3.12 and `uv`
- `task` (go-task)
- PostgreSQL at `localhost:15432` — to **run** the service. The test suite needs no
  database; see [Testing](#testing).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...host.docker.internal:15432/celine_webapp` | PostgreSQL async URL |
| `DATABASE_ECHO` | `false` | Log SQL statements |
| `DIGITAL_TWIN_API_URL` | `http://host.docker.internal:8002` | Digital Twin service URL |
| `NUDGING_API_URL` | `http://host.docker.internal:8016` | nudging-tool service URL |
| `FLEXIBILITY_API_URL` | `http://host.docker.internal:8017` | flexibility-api service URL |
| `REC_REGISTRY_URL` | `http://host.docker.internal:8004` | rec-registry service URL |
| `SMART_METER_API_URL` | — | Optional smart meter API URL |
| `NUDGING_INGEST_SCOPE` | `nudging.ingest` | OAuth2 scope for nudging ingest calls |
| `POLICY_VERSION` | `2024-01-01` | Current terms version string |
| `JWT_HEADER_NAME` | `x-auth-request-access-token` | Header carrying the bearer token |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |
| `CELINE_OIDC_*` | (from celine-sdk defaults) | OIDC settings — issuer, JWKS URI, audience |

### Data sharing

Off by default. The section is hidden in the app and the routes answer 404 until the
dataspace is deployed, because a sharing screen that cannot record a decision is worse
than no screen.

| Variable | Default | Description |
|---|---|---|
| `DATA_SHARING_ENABLED` | `false` | Master switch for the whole surface |
| `IDENTITY_REGISTRY_URL` | `http://host.docker.internal:30005` | Resolves the member's DID and credential |
| `DS_CONNECTOR_URL` | `http://host.docker.internal:30001` | Holds the consent records |
| `DS_PROVENANCE_URL` | `http://host.docker.internal:30000` | Serves the member's own history |
| `DS_NS_URL` | — | Vocabulary namespace |
| `DS_RESOLVE_CLIENT_ID` | `svc-celine-webapp` | Service account, used *only* to resolve a credential |
| `DS_RESOLVE_CLIENT_SECRET` | — | Secret for the above |

The routes stay off unless `DATA_SHARING_ENABLED` is true **and** both
`IDENTITY_REGISTRY_URL` and `DS_CONNECTOR_URL` are set.

## Backend Setup

```bash
uv sync
uv run alembic upgrade head
task run
# Listens on http://localhost:8014
```

## Taskfile Commands

| Command | Description |
|---|---|
| `task setup` | `uv sync` |
| `task test` | Run the test suite |
| `task run` | Start dev server on port 8014 |
| `task debug` | Start with debugger |
| `task migrate` | Apply all pending migrations |
| `task migrate:create` | Create a new Alembic migration |
| `task release` | Run semantic-release |

## Frontend

The participant frontend is in [celine-frontend](https://github.com/celine-eu/celine-frontend) `apps/webapp`. See that repository for frontend setup instructions.

## Calling the API locally

In local dev the BFF reads `X-Auth-Request-Access-Token`, the header oauth2-proxy injects
in deployment. `Authorization: Bearer <token>` works as a fallback.

```bash
curl http://localhost:8014/api/me \
  -H "X-Auth-Request-Access-Token: <token>"
```

**The token must be a real one from Keycloak.** It is verified in full here — the signing
key is resolved from the realm's JWKS by the token's `kid`, the signature is checked, and
`exp` and `iss` are enforced. There is no unverified path and no development bypass, so a
hand-assembled or `alg: none` token will be rejected.

A 401 accompanied by this log line is the usual result, and it means the token, not the
network:

```text
Failed to fetch signing key from …/protocol/openid-connect/certs:
  Unable to find a signing key that matches: "None"
```

## CLI

```bash
celine-webapp-export-feedback   # Export user feedback data
```

## Database Migrations

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "add preference column"
```

## Testing

```bash
task test              # the whole suite
task test -- -x -q     # arguments pass through to pytest
```

**The suite needs nothing running** — no PostgreSQL, no Keycloak, no upstream service. It
runs on a clean checkout and in CI, and a test that needs a live service does not belong
in it.

That is achieved at two seams, and both matter when you write a test:

- **Identity is real; only the JWKS fetch is faked.** Tests sign genuine RS256 tokens with
  a throwaway key, and the service verifies them exactly as it does in production —
  signature, expiry, issuer. Nothing overrides the authentication dependency, so a test
  cannot accidentally prove that a token this service *should* reject is accepted.
- **The database is SQLite, one file per test.** Production is PostgreSQL, so a schema
  change is not verified by a green run alone — exercise the migration separately.

### What the suite does and does not tell you

This service is a backend-for-frontend: most of what it does is fan out to the Digital
Twin, rec-registry, flexibility-api and nudging-tool through `celine-sdk`, then compose
the results. Those four are replaced by fakes in `tests/fakes.py`, which reproduce the
shape the SDK returned when they were written.

So a green suite says the composition logic is correct against that shape.
`tests/test_sdk_contract.py` checks the fakes against the installed `celine-sdk` models,
which catches drift in the package — but **not** that a deployed upstream serves what its
own SDK describes. A `celine-sdk` version bump can still change this service's behaviour
with no file here changing. Treat an SDK bump as a change to this service rather than as
dependency maintenance.

### Layout

| File | Covers |
|---|---|
| `tests/test_auth_boundary.py` | what is accepted as an identity, and what is rejected |
| `tests/test_overview_fanout.py` | `/api/overview` — aggregation, trend building, degradation |
| `tests/test_gamification_fanout.py` | `/api/gamification` — season scoring and its fallback |
| `tests/test_nudging_fanout.py` | `/api/settings` and `/api/notifications` |
| `tests/test_sdk_contract.py` | that the fakes still match the installed `celine-sdk` models |
| `tests/test_data_sharing.py` | the data-sharing surface, dataspace stubbed |
| `tests/test_api.py`, `tests/test_forecast.py` | pure mapping and window functions |
| `tests/fakes.py` | the four upstream fakes |

**If you add a field to a fake, assert it in `test_sdk_contract.py` in the same change.**
The fakes are written by hand from reading route code, so an invented attribute will
reproduce whatever you expect of it — that is not a hypothetical, it produced a fully
reproducible and entirely wrong bug report the day the fakes were written.

Tests marked `xfail` with `strict=True` are **known defects, pinned deliberately**, each
with its reason in the marker. Fixing one turns the run red with `XPASS(strict)` — the
signal to remove the marker in the same change. There are none at present.

## Project Layout

```
src/celine/webapp/
  main.py                # FastAPI app factory
  settings.py            # Pydantic settings
  routes.py              # Router registration
  cli.py                 # CLI (celine-webapp-export-feedback)
  api/
    user.py              # /api/me, /api/terms/accept
    overview.py          # /api/overview
    weather.py           # /api/weather
    forecast.py          # /api/forecast
    community.py         # /api/community
    suggestions.py       # /api/suggestions, /api/commitments
    gamification.py      # /api/gamification
    co2_settings.py      # /api/settings/co2
    settings_routes.py   # /api/settings
    notifications.py     # /api/notifications, webpush
    feedback.py          # /api/feedback
    data_sharing.py      # /api/data-sharing
    meta.py              # /health
    deps.py              # FastAPI dependencies — every outbound client is resolved here
    schemas.py           # Pydantic schemas
  services/
    data_sharing.py      # Dataspace calls (identity registry, connector, provenance)
  db/
    models.py            # SQLAlchemy ORM models
    session.py           # Async session management
    user_settings.py     # User settings helpers
alembic/                 # Database migrations
tests/                   # See Testing above
```
