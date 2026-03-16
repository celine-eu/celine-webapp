# Architecture

## BFF Pattern

The webapp uses a Backend-for-Frontend (BFF) architecture. The SvelteKit frontend never talks directly to backend microservices — all requests go through the FastAPI BFF layer.

Benefits:
- A single auth boundary: the BFF validates the JWT and attaches credentials
- The browser is not exposed to internal service URLs or access tokens
- The BFF can aggregate, transform, and cache data from multiple services

## Deployment Model

```
Browser
  |
  v
Caddy (reverse proxy + TLS)
  |
  v
oauth2_proxy  <-->  Keycloak (OIDC)
  |
  v
celine-webapp (SvelteKit + FastAPI BFF, same origin)
  |
  +-->  digital-twin service
  +-->  nudging-tool service
  +-->  celine-ai-assistant service
```

The entire webapp (frontend + BFF) is deployed as a single container. Caddy routes `/*` through oauth2_proxy before forwarding to the webapp.

## JWT Flow

1. User authenticates via Keycloak through oauth2_proxy.
2. oauth2_proxy injects the access token into the `X-Auth-Request-Access-Token` header.
3. The BFF reads this header on each request — signature is not re-verified (trusted internal header).
4. The BFF extracts the user subject (`sub`), groups, and email from the token.
5. Downstream service calls include the access token as `Authorization: Bearer <token>`.

## Service Dependencies

| Service | Usage |
|---|---|
| **Digital Twin** | Energy overview data, participant values |
| **nudging-tool** | Notification list and preferences |
| **celine-ai-assistant** | Embedded chat assistant (proxied) |
| **Keycloak** | Identity provider (via oauth2_proxy) |

## Frontend Structure

```
frontend/src/
  routes/
    +layout.svelte       # App shell — terms acceptance check via /api/me
    +page.svelte         # Overview (energy chart, stat cards)
    assistant/
      +page.svelte       # Embedded ChatCore
    notifications/
      +page.svelte       # Notification list
    settings/
      +page.svelte       # User settings
  lib/
    api.ts               # Typed BFF API client
    stores.ts            # Svelte stores
    components/
      EnergyChart.svelte
      StatCard.svelte
```
