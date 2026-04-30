# Development

## Prerequisites

- Python >= 3.12 and `uv`
- `task` (go-task)
- PostgreSQL at `localhost:15432` (credentials `postgres:securepassword123`)

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
| `OIDC__*` | (from celine-sdk defaults) | OIDC settings |

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
| `task run` | Start dev server on port 8014 |
| `task debug` | Start with debugger |
| `task alembic:upgrade` | Apply all pending migrations |
| `task alembic:create` | Create new Alembic migration |
| `task release` | Run semantic-release |

## Frontend

The participant frontend is in [celine-frontend](https://github.com/celine-eu/celine-frontend) `apps/webapp`. See that repository for frontend setup instructions.

## JWT Simulation

In local dev, the BFF reads `X-Auth-Request-Access-Token`. Simulate this header using curl:

```bash
curl http://localhost:8014/api/me \
  -H "X-Auth-Request-Access-Token: <your-jwt>"
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

## Running Tests

```bash
uv run pytest -q
```

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
    meta.py              # /health
    deps.py              # FastAPI dependencies
    schemas.py           # Pydantic schemas
  db/
    models.py            # SQLAlchemy ORM models
    session.py           # Async session management
    user_settings.py     # User settings helpers
policies/                # OPA .rego policy files
alembic/                 # Database migrations
```
