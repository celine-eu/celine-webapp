# Features

## Terms Acceptance

Terms acceptance is enforced at the frontend layout level. On every page load, the `+layout.svelte` root layout calls `GET /api/me`. If the response has `terms_accepted: false`, the user is redirected to a terms page before accessing any other route.

Acceptance is persisted in the database via `POST /api/me/terms`. Once accepted, the check passes on subsequent loads.

## Web Push (VAPID)

The webapp supports browser push notifications using the Web Push Protocol and VAPID keys.

Setup flow:
1. Frontend requests the VAPID public key from `GET /api/settings/vapid-public-key`.
2. Browser subscribes using the Web Push API (`PushManager.subscribe`).
3. The subscription endpoint is registered with the BFF via `POST /api/settings/push-subscribe`.
4. The BFF stores the subscription in the nudging-tool service.
5. Nudging events trigger push deliveries through the registered endpoint.

Note: Actual push delivery is handled by the nudging-tool service, not the BFF.

## Digital Twin Integration

The overview page displays energy data fetched from the Digital Twin service:
- Community-level production and consumption totals
- Participant-level meter readings
- Incentive calculations (Italian REC rules: GSE incentives)

Data is fetched server-side by the BFF, which authenticates with the Digital Twin using the user's access token. Results are transformed into the response format expected by the frontend components.

## Notification Preferences

Users can configure:
- Whether push notifications are enabled
- Preferred language for notification messages
- Maximum notifications per day

Preferences are stored in the nudging-tool database and affect rule evaluation during event ingestion.

## Embedded Assistant

The `/assistant` route embeds the `ChatCore` component from `@celine-eu/assistant-ui`, connected to the celine-ai-assistant service via the BFF proxy at `/api/assistant/*`. The user's identity is forwarded automatically, enabling personalized RAG responses.
