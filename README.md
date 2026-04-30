# CELINE Participant Webapp API

FastAPI Backend-for-Frontend (BFF) for the CELINE REC participant webapp. Deployed same-origin behind oauth2_proxy.

The participant frontend (SvelteKit) is maintained separately in [celine-frontend](https://github.com/celine-eu/celine-frontend) (`apps/webapp`).

## Architecture

The webapp uses the BFF pattern:
- The frontend (SvelteKit) communicates exclusively with the BFF at `/api/*`
- The BFF reads the JWT from the `X-Auth-Request-Access-Token` header injected by oauth2_proxy
- The BFF proxies authenticated requests to backend services (Digital Twin, nudging-tool, flexibility-api, rec-registry)
- No cross-origin requests from the browser

## Quick Start

```bash
uv sync
uv run alembic upgrade head
task run
# Listens on http://localhost:8014
```

For the participant frontend, see [celine-frontend](https://github.com/celine-eu/celine-frontend) `apps/webapp`.

## Features

| Feature | Description |
|---|---|
| Overview | Energy consumption and production summary from Digital Twin |
| Weather | Current weather conditions for the user's community |
| Forecast | Energy production/consumption forecast from Digital Twin |
| Suggestions | Flexibility window suggestions with accept/reject/remind actions |
| Commitments | Active commitment tracking and cancellation |
| Gamification | Points, badges, and commitment history from flexibility-api |
| CO2 | Carbon emission factors and settings |
| Community | Community metadata from rec-registry |
| Notifications | User notification list, read/unread, enable/disable |
| Web Push | VAPID-based push notification subscription via nudging-tool |
| Settings | Account settings (language, units), terms acceptance |
| Feedback | User feedback submission |
| Health | Service health check |

## CLI

```bash
celine-webapp-export-feedback   # Export user feedback data
```

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | BFF pattern, JWT flow, service dependencies, deployment model |
| [API Reference](docs/api-reference.md) | All BFF endpoints with paths and query params |
| [Features](docs/features.md) | Feature details: suggestions, gamification, CO2, feedback |
| [Development](docs/development.md) | Local dev setup, env vars, taskfile commands |

## License

Apache 2.0 — Copyright © 2025 Spindox Labs
