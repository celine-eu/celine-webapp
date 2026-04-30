# API Reference

All BFF endpoints are served under `/api`. The JWT is read from the `X-Auth-Request-Access-Token` header (injected by oauth2_proxy). Interactive docs at `http://localhost:8014/docs`.

## User

### `GET /api/me`

Returns the authenticated user's profile, terms acceptance status, and settings.

### `POST /api/terms/accept`

Record the user's acceptance of the current terms version.

---

## Overview

### `GET /api/overview`

Returns the energy overview for the authenticated user's community. Aggregates data from the Digital Twin.

---

## Weather

### `GET /api/weather`

Returns current weather conditions for the user's community location via the Digital Twin.

---

## Forecast

### `GET /api/forecast`

Returns energy production/consumption forecast for the user via the Digital Twin.

---

## Community

### `GET /api/community`

Returns community metadata (name, description, areas, links) from the rec-registry.

---

## Suggestions and Commitments

### `GET /api/suggestions`

List active flexibility window suggestions for the user. Includes current window details, acceptance status, and available actions.

### `POST /api/suggestions/{suggestion_id}/remind`

Schedule a flexibility reminder for a suggestion via the nudging-tool.

### `POST /api/suggestions/{suggestion_id}/respond`

Accept or reject a flexibility suggestion. Creates a commitment in the flexibility-api.

### `DELETE /api/commitments/{commitment_id}`

Cancel an active commitment.

---

## Gamification

### `GET /api/gamification`

Returns the user's gamification profile: points from flexibility-api, badges, level, and community ranking from Digital Twin.

### `GET /api/gamification/history`

Returns the user's commitment history from the flexibility-api.

---

## CO2 Settings

### `GET /api/settings/co2`

Returns CO2 emission factors and configuration.

---

## Settings

### `GET /api/settings`

Return the user's current settings (language, units, notification preferences).

### `PUT /api/settings`

Update user settings.

---

## Notifications

### `GET /api/notifications`

List notifications for the authenticated user.

**Query params:**
- `limit` — max results (default 20)
- `offset` — pagination offset
- `unread` — if `true`, return only unread

### `POST /api/notifications/enable`

Enable notifications for the user.

### `POST /api/notifications/disable`

Disable notifications for the user.

### `POST /api/notifications/read-all`

Mark all notifications as read.

### `POST /api/notifications/{notification_id}/read`

Mark a single notification as read.

### `GET /api/notifications/webpush/vapid-public-key`

Return the VAPID public key for web push subscription setup.

### `POST /api/notifications/webpush/subscribe`

Register a browser push subscription endpoint.

### `POST /api/notifications/webpush/unsubscribe`

Remove a push subscription.

---

## Feedback

### `POST /api/feedback`

Submit user feedback. Returns `201` on success.

---

## Health

### `GET /health`

Service health check.
