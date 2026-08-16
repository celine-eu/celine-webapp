# API Reference

All BFF endpoints are served under `/api`. The JWT is read from the
`X-Auth-Request-Access-Token` header (injected by oauth2_proxy), falling back to
`Authorization: Bearer`. The token is **verified in full** — see
[Architecture](architecture.md#jwt-flow); every endpoint below answers `401` without a
valid one.

Interactive docs at `http://localhost:8014/api/docs`, OpenAPI schema at
`http://localhost:8014/api/openapi.json`.

## User

### `GET /api/me`

Returns the authenticated user's profile, terms acceptance status, and settings.

### `POST /api/terms/accept`

Record the user's acceptance of the current terms version.

---

## Overview

### `GET /api/overview`

Returns the energy overview for the authenticated user's community. Aggregates four
separate Digital Twin fetches into the member's totals, the community's totals, and a
daily trend.

Query parameters:
- `days`: relative range in days when no custom dates are provided, default `7`, maximum `365`.
- `start_date` and `end_date`: inclusive custom date range in `YYYY-MM-DD` format, maximum 1 year. Both must be provided together.

Responses:
- `400` — dates supplied singly, reversed, in the future, or spanning more than a year.
- `404` — the caller is not a participant, or has no community membership.

**Individual upstream failures degrade rather than fail.** If the member's meter data
cannot be fetched, the response is still `200` with `null` figures in that block and the
community block populated; the trend always contains one entry per day in the range,
filled or `null`. A dashboard with gaps is preferred to no dashboard.

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

Returns community metadata (name, description, legal and contact details, links) from the
rec-registry.

Always `200`. If the registry is unreachable, misconfigured, or rejects the token, the
response falls back to `{"key": "unknown", "name": "REC"}` rather than an error — the
three cases are indistinguishable to the caller and are separated only in the logs.

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

Returns the user's gamification profile: season points, level, badges, accepted-action
count and anonymous season ranking.

Points come from the Digital Twin's `rec_points_leaderboard` and `rec_participant_points`
fetchers — **not** from the flexibility-api. The flexibility-api's `reward_points_actual`
is deliberately not used, because its settlement formula does not compare against baseline
and so inflates the value.

Two modes, and the response does not label which one produced it:
- **Season** — a usable leaderboard row supplies `total_points`, the `season_*` fields and
  `ranking`. The level ladder is 100 points per level applied to season points, so it
  resets each season.
- **Fallback** — when that row is unavailable or malformed (older Digital Twin deployment,
  device not yet in the fleet, brand-new device), `total_points` is the all-time sum of
  daily points, every `season_*` field is `null`, and `ranking` is `null`.

### `GET /api/gamification/history`

Returns the user's commitment history from the flexibility-api.

---

## CO2 Settings

### `GET /api/settings/co2`

Returns CO2 emission factors and configuration.

---

## Settings

Settings are split across two owners and merged into one object here: `simple_mode`,
`font_scale` and `webpush_enabled` are stored by this service, while the notification
limit, the email channel and the per-kind catalogue belong to the nudging-tool.

### `GET /api/settings`

Return the merged settings.

Query parameters:
- `lang` — language for the notification-kind catalogue. Falls back to `Accept-Language`.
  Only `it`, `en` and `es` are recognised; anything else is dropped.

Responses:
- `502` — notification preferences could not be loaded. Settings are not rendered
  half-known.
- A catalogue that fails to load degrades quietly instead: `200` with `kinds: []`.

### `PUT /api/settings`

Update settings, writing each half to its owner. Returns the merged result.

Only kinds marked `enabled` are sent upstream. Kinds with `editable: false` (such as
`extr_event`) are not a member's to switch off and keep that flag across the round trip.

Responses:
- `422` — the body could not be validated. `detail` is a plain string suitable for
  display, such as `Email address format is invalid`, not an array of error objects.
- `502` — the nudging-tool rejected or could not accept the update.

---

## Notifications

### `GET /api/notifications`

List notifications for the authenticated user, from the nudging-tool.

Takes **no query parameters** — the upstream client's `limit`, `offset` and `unread_only`
are not exposed here and its defaults apply. `severity` is normalised to `critical`,
`warning` or `info`; any other value the upstream introduces collapses to `info`.

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

## Data sharing

Behind `DATA_SHARING_ENABLED`, **off by default**. While the flag is off — or while the
identity registry or connector URL is unset — every route here answers `404` and the app
hides the section, so nothing half-working is exposed.

Every call is made with the **member's own verifiable credential**. This service only
resolves which credential is theirs; it cannot act on their behalf, and neither can an
administrator.

### `GET /api/data-sharing`

Every published offer, merged with this member's decision on it.

Offers are read from the published vocabulary on each request and never cached or
vendored: two copies of the text somebody agrees to is how the thing displayed and the
thing recorded drift apart. If the vocabulary is unreachable the call fails rather than
serving a stale copy.

- `has_identity: false` with an empty list — a member with no dataspace identity. A normal
  state, not an error.
- `503` — the dataspace is unreachable.

### `POST /api/data-sharing/{offer_id}`

Grant or withdraw one offer. Body: `{"enabled": true | false}`.

**Withdrawal is the reason this route exists.** The onboarding wizard can only grant, so
without it a consent could be given and never taken back — a compliance defect rather than
a missing feature. Anything that reworks this surface must keep withdrawal reachable
independently of the wizard.

- `409` — the account has no dataspace identity, or the offer is contract-based and
  therefore disclosed rather than toggled.
- `503` — the dataspace is unreachable.

### `GET /api/data-sharing/history`

What has happened with this member's data, served by provenance under their own
credential. Absent provenance returns an empty history rather than an error.

---

## Feedback

### `POST /api/feedback`

Submit user feedback. Returns `201` on success.

---

## Health

### `GET /health`

Service health check.
