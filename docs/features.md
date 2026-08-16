# Features

## Terms Acceptance

Terms acceptance is enforced at the frontend layout level. On every page load, the frontend calls `GET /api/me`. If the response has `terms_required: true`, the user is redirected to a terms page. Acceptance is persisted via `POST /api/terms/accept` and checked against the current `POLICY_VERSION` — raising that version requires every member to accept again.

## Overview and Energy Data

The overview page displays energy data fetched from the Digital Twin service:
- Community-level production and consumption totals
- Participant-level meter readings
- Incentive calculations (Italian REC rules: GSE incentives)

Data is fetched server-side by the BFF, which authenticates with the Digital Twin using the user's access token.

## Weather and Forecast

- `GET /api/weather` returns current weather conditions for the user's community location via the Digital Twin.
- `GET /api/forecast` returns energy production/consumption forecasts.

## Flexibility Suggestions

The suggestions system integrates with the flexibility-api and Digital Twin to present energy flexibility opportunities:

1. `GET /api/suggestions` lists active flexibility windows with available actions.
2. Users can accept or reject suggestions via `POST /api/suggestions/{id}/respond`, which creates commitments in the flexibility-api.
3. Users can schedule reminders via `POST /api/suggestions/{id}/remind`, which delegates to the nudging-tool via the Digital Twin.
4. Active commitments can be cancelled via `DELETE /api/commitments/{id}`.

## Gamification

`GET /api/gamification` aggregates data from multiple services:
- **Season points from the Digital Twin** (`rec_points_leaderboard`, `rec_participant_points`), not from the flexibility-api — its settlement figure omits the baseline comparison and inflates the value
- Badges awarded for achievements, stored locally
- The member's own anonymous season ranking, from the Digital Twin

Points and the level ladder are scoped to the current season, so the ladder resets each
season. Where the season data is unavailable — an older Digital Twin, or a device not yet
in the fleet — the endpoint falls back to an all-time total and shows no ranking at all.
The response does not say which mode produced it.

`GET /api/gamification/history` returns the user's commitment history from the flexibility-api, with settled reward points cross-referenced against the Digital Twin's figures.

## CO2 Reporting

`GET /api/settings/co2` returns carbon emission factors and configuration.

## Community

`GET /api/community` returns community metadata from the rec-registry, including name, description, areas, and links.

## Notifications

The notification system proxies the nudging-tool:
- List notifications (no filtering is exposed through this API)
- Mark individual or all notifications as read
- Enable/disable notifications per user

## Web Push (VAPID)

Setup flow:

1. Frontend requests the VAPID public key from `GET /api/notifications/webpush/vapid-public-key`.
2. Browser subscribes using the Web Push API (`PushManager.subscribe`).
3. The subscription endpoint is registered via `POST /api/notifications/webpush/subscribe`.
4. The BFF stores the subscription in the nudging-tool service.
5. Nudging events trigger push deliveries through the registered endpoint.

Actual push delivery is handled by the nudging-tool service, not the BFF.

## Feedback

Users can submit feedback via `POST /api/feedback`. Feedback data can be exported using the `celine-webapp-export-feedback` CLI tool.

## Data Sharing

A member's own decisions about sharing their energy data, at `GET /api/data-sharing` and
`POST /api/data-sharing/{offer_id}`, with their history at `/api/data-sharing/history`.

**Off by default** (`DATA_SHARING_ENABLED`): while the dataspace is undeployed the routes
answer 404 and the app hides the section, because a sharing screen that cannot record a
decision is worse than no screen.

The offers a member sees are read from the published vocabulary on each request rather
than from a local copy — two copies of the text somebody agrees to is how the thing
displayed and the thing recorded drift apart.

**Withdrawal is the point of the surface.** The onboarding wizard can only grant, so
without these routes a consent could be given and never taken back. Every call is made
with the member's own credential: it is their act, and an administrator cannot perform it
for them.

## Settings

`GET/PUT /api/settings` presents one settings object assembled from two owners:

- **This service** stores display preferences — `simple_mode`, `font_scale` — and web push
  enablement.
- **The nudging-tool** owns the notification limit, the email channel and the per-kind
  catalogue.

The split is invisible to the app, which reads and writes a single object. Some
notification kinds are marked non-editable and cannot be switched off by a member.
