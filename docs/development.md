# Development

## Prerequisites

- Python ≥ 3.11 and `uv`
- Node.js ≥ 20 and `pnpm`
- A running PostgreSQL instance

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async URL | `postgresql+asyncpg://postgres:postgres@localhost:5432/webapp` |
| `DIGITAL_TWIN_URL` | Digital Twin service URL | `http://localhost:8001` |
| `NUDGING_URL` | Nudging-tool service URL | `http://localhost:8002` |
| `ASSISTANT_URL` | AI assistant service URL | `http://localhost:8003` |
| `VAPID_PUBLIC_KEY` | VAPID public key for web push | required |

## Backend Setup

```bash
# Install dependencies
uv sync

# Apply database migrations
uv run alembic upgrade head

# Start the BFF
uv run -m celine.webapp.main
# Listens on http://localhost:8000
```

## Frontend Setup

```bash
cd frontend
pnpm install
pnpm dev
# Listens on http://localhost:5173
```

## Local Proxy Configuration

For local development, the frontend at `localhost:5173` needs to proxy `/api` requests to the BFF at `localhost:8000`. Configure Vite:

```javascript
// frontend/vite.config.js
export default {
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    }
  }
}
```

## JWT Simulation

In local dev, the BFF reads `X-Auth-Request-Access-Token`. Simulate this header using a curl or Postman request:

```bash
curl http://localhost:8000/api/me \
  -H "X-Auth-Request-Access-Token: <your-jwt>"
```

Generate a test token using Keycloak or create a static token for dev purposes.

## Database Migrations

```bash
# Apply all migrations
uv run alembic upgrade head

# Create a new migration
uv run alembic revision --autogenerate -m "add preference column"
```

## Running Tests

```bash
uv run pytest -q
```

Frontend tests:
```bash
cd frontend && pnpm test
```
