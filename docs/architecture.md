# Architecture

## BFF Pattern

The webapp uses a Backend-for-Frontend (BFF) architecture. The SvelteKit frontend never talks directly to backend microservices — all requests go through the FastAPI BFF layer.

Benefits:
- A single auth boundary: the BFF validates the JWT and attaches credentials
- The browser is not exposed to internal service URLs or access tokens
- The BFF can aggregate, transform, and cache data from multiple services

## Deployment Model

Requests from the browser pass through Caddy (TLS termination) -> oauth2_proxy (OIDC authentication against Keycloak) -> the BFF. The BFF then forwards authenticated requests to internal services.

| Layer | Component | Role |
|---|---|---|
| Ingress | Caddy | TLS termination, reverse proxy |
| Auth | oauth2_proxy | OIDC login with Keycloak, JWT injection |
| Application | FastAPI BFF | Request handling, service aggregation |
| Backend services | digital-twin, nudging-tool, flexibility-api, rec-registry | Domain data |

The BFF is deployed as a standalone container. The participant frontend is served from [celine-frontend](https://github.com/celine-eu/celine-frontend) `apps/webapp`.

## JWT Flow

1. User authenticates via Keycloak through oauth2_proxy.
2. oauth2_proxy injects the access token into the `X-Auth-Request-Access-Token` header.
3. The BFF reads this header on each request — signature is not re-verified (trusted internal header).
4. The BFF extracts the user subject (`sub`), groups, and email from the token.
5. Downstream service calls include the access token as `Authorization: Bearer <token>`.

## Service Dependencies

| Service | Usage |
|---|---|
| **Digital Twin** | Energy overview, weather, forecast, participant values, community data |
| **nudging-tool** | Notification list, preferences, web push, flexibility reminders |
| **flexibility-api** | Gamification points, commitment history, flexibility window responses |
| **rec-registry** | Community metadata (name, areas, links) |
| **Keycloak** | Identity provider (via oauth2_proxy) |

All service clients are provided via `celine-sdk`.

## Database

PostgreSQL (async via SQLAlchemy + asyncpg). Stores:
- User settings (language, units)
- Terms acceptance records
- Feedback submissions

## Frontend

This repository is a pure API backend. The participant frontend (SvelteKit) is maintained separately in [celine-frontend](https://github.com/celine-eu/celine-frontend) `apps/webapp`. The frontend communicates exclusively with this BFF at `/api/*`.
