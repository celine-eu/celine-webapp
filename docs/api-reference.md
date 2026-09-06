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

Behind `DATA_SHARING_ENABLED`, **off by default**. While the flag is off — or while
`ONBOARDING_API_URL` is unset — every route here answers `404` and the app hides the
section, so nothing half-working is exposed.

**These routes are proxies.** Onboarding owns the member's dataspace identity, resolves
their credential and holds the connector grants; this service forwards the member's own
token to `/api/me/data-sharing` and passes the answer back. It holds no credential and no
service account, so it cannot act on a member's behalf — and neither can an administrator.

The browser talks only to this service: onboarding is not same-origin.

### `GET /api/data-sharing`

Every offer this member's community publishes, merged with their decision on it.

Offers are read from the published vocabulary on each request and never cached or
vendored: two copies of the text somebody agrees to is how the thing displayed and the
thing recorded drift apart. The merge happens in onboarding, beside the credential that
reads both.

- `has_identity: false` with an empty list — a normal state, not an error.
- `state` — why, in one word: `ok`, `no_dataspace` (the community does not take part),
  `no_identity` (no credential yet), `identity_conflict` (an operator's to clear), or
  `ambiguous_community`. Additive; `has_identity` has not moved.
- `503` — onboarding, or the dataspace behind it, is unreachable.
- `502` — onboarding answered something this service cannot pass on. A deployment fault,
  deliberately distinct from the `404` that means the feature is off.

**The prompt.** Two further fields say whether the app should ask:

- `asked` — false only for a member who has neither dismissed the banner nor decided
  anything, including in onboarding's own funnel. That is the first-run sequence.
- `review_due` — true when the newest of their dismissal and their decisions is older
  than `DATA_SHARING_REVIEW_AFTER_DAYS`. That is the "you are sharing data, review your
  settings" reminder.

Being asked is this service's state, not onboarding's: onboarding holds no session with
the member. It is recorded by `POST /api/onboarding/seen` with `{"page_key":
"data-sharing"}`, the same route every in-app tour uses, and marking it again moves the
timestamp forward so the reminder can be dismissed more than once.

### `POST /api/data-sharing/{offer_id}`

Grant or withdraw one offer. Body: `{"enabled": true | false}`.

**Withdrawal is the reason this route exists.** The onboarding wizard can only grant, so
without it a consent could be given and never taken back — a compliance defect rather than
a missing feature. Anything that reworks this surface must keep withdrawal reachable
independently of the wizard.

- `409` — there is no decision here to make: no dataspace identity yet, an offer this REC
  does not publish, or one disclosed under a contract rather than consented to. The
  detail onboarding gave is forwarded and names which.
- `503` — onboarding, or the dataspace behind it, is unreachable.

### `GET /api/data-sharing/history`

What has happened with this member's data, served by provenance under their own
credential. Absent provenance returns an empty history rather than an error — decided in
onboarding, where the credential is.

---

## Feedback

### `POST /api/feedback`

Submit user feedback. Returns `201` on success.

---

## Health

### `GET /health`

Service health check.
