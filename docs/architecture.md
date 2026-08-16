# Architecture

## BFF Pattern

The webapp uses a Backend-for-Frontend (BFF) architecture. The SvelteKit frontend never talks directly to backend microservices — all requests go through the FastAPI BFF layer.

Benefits:
- A single auth boundary: the BFF verifies the JWT and forwards it to each service
- The browser is not exposed to internal service URLs or access tokens
- The BFF aggregates and transforms data from multiple services into the shape one screen
  needs — a single request where the browser would otherwise make several

The service owns very little domain logic. What it owns is the **composition**, which
makes its dependency surface wide and shallow: four upstreams, thin use of each, and a
failure in any of them surfaces here.

Nothing is cached. Each request fans out afresh.

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
3. **The BFF verifies the token in full.** It resolves the signing key from the realm's
   JWKS by the token's `kid`, checks the RS256 signature, and enforces `exp`, `nbf` and
   `iss`. `aud` is enforced only when an audience is configured.
4. The BFF extracts the user subject (`sub`), groups, and email **from the verified
   token**. oauth2_proxy also injects `x-auth-request-user` and `x-auth-request-email`;
   neither is read, because neither is signed.
5. Downstream service calls forward the same access token as `Authorization: Bearer <token>`.

There is no unverified path and no development bypass. A hand-assembled or `alg: none`
token is rejected with 401 wherever the service runs.

> An earlier version of this page stated that the signature was not re-verified and the
> header was trusted as internal. That was incorrect. Corrected 2026-08-15.

## Service Dependencies

| Service | Usage |
|---|---|
| **Digital Twin** | Energy overview, weather, forecast, participant values, community data, **gamification points and season ranking** |
| **nudging-tool** | Notification list, preferences, web push, flexibility reminders |
| **flexibility-api** | Commitment history and flexibility window responses |
| **rec-registry** | Community metadata (name, legal and contact details, links) |
| **Keycloak** | Identity provider, and the JWKS this service verifies tokens against |

All service clients are provided via `celine-sdk`, never by reaching into a sibling
checkout. **A `celine-sdk` version bump therefore changes this service's behaviour with no
file in this repository changing** — treat it as a change to the service rather than as
dependency maintenance.

Gamification points come from the Digital Twin rather than the flexibility-api, despite
the latter owning flexibility: the flexibility-api's settlement figure is computed without
a baseline comparison and inflates the value.

## Database

PostgreSQL (async via SQLAlchemy + asyncpg). Stores only what no upstream owns:
- Display settings — `simple_mode`, `font_scale`, web push enablement
- Terms acceptance records, against the current `POLICY_VERSION`
- Onboarding pages already seen
- Badges earned and suggestion interactions
- Feedback submissions

Notification preferences are **not** stored here; they belong to the nudging-tool and are
merged into the settings response at request time.

## Frontend

This repository is a pure API backend. The participant frontend (SvelteKit) is maintained separately in [celine-frontend](https://github.com/celine-eu/celine-frontend) `apps/webapp`. The frontend communicates exclusively with this BFF at `/api/*`.
