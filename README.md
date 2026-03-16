# celine-webapp

REC participant webapp — SvelteKit 2 / Svelte 5 frontend with a FastAPI Backend-for-Frontend (BFF). Deployed same-origin behind oauth2_proxy.

## Architecture

The webapp uses the BFF pattern:
- The frontend (SvelteKit) communicates exclusively with the BFF at `/api/*`
- The BFF reads the JWT from the `X-Auth-Request-Access-Token` header injected by oauth2_proxy
- The BFF proxies authenticated requests to backend services (Digital Twin, nudging-tool)
- No cross-origin requests from the browser

## Quick Start

**Backend (BFF):**
```bash
uv run -m celine.webapp.main
# Listens on http://localhost:8000
```

**Frontend:**
```bash
cd frontend
pnpm install
pnpm dev
# Listens on http://localhost:5173
```

For local development, proxy `/api` to the backend via Vite config or a local reverse proxy.

## Features

| Feature | Description |
|---|---|
| Overview | Energy consumption and production summary |
| Notifications | User notification list and preferences |
| Settings | Account settings, terms acceptance |
| Web Push | VAPID-based push notification subscription |
| Digital Twin | Real-time energy data via DT integration |
| Assistant | Embedded AI assistant (proxied to celine-ai-assistant) |

## Documentation

| Document | Description |
|---|---|
| [Architecture](https://celine-eu.github.io/projects/celine-webapp/docs/architecture.md) | BFF pattern, JWT flow, service dependencies, deployment model |
| [API Reference](https://celine-eu.github.io/projects/celine-webapp/docs/api-reference.md) | All BFF endpoints: user, overview, notifications, settings |
| [Features](https://celine-eu.github.io/projects/celine-webapp/docs/features.md) | Terms acceptance, web push, digital twin integration |
| [Development](https://celine-eu.github.io/projects/celine-webapp/docs/development.md) | Local dev proxy setup, env vars, running tests |

## License

Apache 2.0 — Copyright © 2025 Spindox Labs
