# API Reference

All BFF endpoints are served under `/api`. The JWT is read from the `X-Auth-Request-Access-Token` header (injected by oauth2_proxy). No client-side auth header is needed.

## User

### `GET /api/me`

Returns the authenticated user's profile. Used by the frontend layout loader to enforce terms acceptance.

**Response:**
```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "name": "Alice Rossi",
  "groups": ["/viewers"],
  "terms_accepted": true
}
```

If `terms_accepted` is `false`, the frontend redirects to the terms acceptance flow.

### `POST /api/me/terms`

Record the user's acceptance of terms. Sets `terms_accepted = true` for the authenticated user.

---

## Overview

### `GET /api/overview`

Returns the energy overview for the authenticated user's community. Aggregates data from the Digital Twin.

**Response:**
```json
{
  "community_id": "COMM1",
  "period": "2026-03",
  "production_kwh": 1200.5,
  "consumption_kwh": 980.3,
  "shared_kwh": 430.1,
  "incentive_eur": 85.20
}
```

---

## Notifications

### `GET /api/notifications`

List notifications for the authenticated user.

**Query params:**
- `limit` — max results (default 20)
- `offset` — pagination offset
- `unread` — if `true`, return only unread

### `POST /api/notifications/{id}/read`

Mark a notification as read.

### `DELETE /api/notifications/{id}`

Delete a notification.

---

## Settings

### `GET /api/settings`

Return the user's current settings including notification preferences and push subscription status.

### `PUT /api/settings`

Update notification preferences.

**Request body:**
```json
{
  "notifications_enabled": true,
  "preferred_language": "en",
  "max_per_day": 3
}
```

### `GET /api/settings/vapid-public-key`

Return the VAPID public key for web push subscription setup.

### `POST /api/settings/push-subscribe`

Register a browser push subscription endpoint.

### `POST /api/settings/push-unsubscribe`

Remove a push subscription.

---

## Assistant Proxy

### `* /api/assistant/{path}`

Proxy all assistant requests (GET, POST, DELETE) to the celine-ai-assistant service, forwarding the user's access token.
