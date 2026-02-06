# REC Participant Webapp (SvelteKit + FastAPI BFF)

This is a scaffold for a renewable energy community participant webapp.

## Structure
- `frontend/` SvelteKit 2 / Svelte 5 + Bulma UI
- `src/celine/webapp/` FastAPI backend-for-frontend (BFF)

## Run backend (uv)
From repo root:
```bash
uv run -m celine.webapp.main
```
Backend listens on http://localhost:8000

The JWT is expected in `X-Auth-Request-Access-Token` (oauth2_proxy style).
Signature is not verified (minimal validation).

## Run frontend
```bash
cd frontend
npm i
npm run dev
```
Frontend listens on http://localhost:5173

For local development you can proxy `/api` to the backend using your reverse proxy or by configuring Vite.
(This scaffold assumes same-origin deployment behind oauth2_proxy.)

## Notes
- Terms acceptance is enforced by the frontend layout loader using `/api/me`.
- Web push is implemented via service worker and VAPID public key endpoint; actual delivery is out of scope here.
- Data sources (Digital Twin + broker) are stubbed.
