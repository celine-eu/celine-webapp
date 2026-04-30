# Features

## Terms Acceptance

Terms acceptance is enforced at the frontend layout level. On every page load, the frontend calls `GET /api/me`. If the response has `terms_accepted: false`, the user is redirected to a terms page. Acceptance is persisted via `POST /api/terms/accept` and checked against the current `POLICY_VERSION`.

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
- Points from the flexibility-api based on commitment fulfillment
- Badges awarded for achievements (checked and awarded automatically)
- Community ranking from Digital Twin

`GET /api/gamification/history` returns the user's commitment history from the flexibility-api.

## CO2 Reporting

`GET /api/settings/co2` returns carbon emission factors and configuration.

## Community

`GET /api/community` returns community metadata from the rec-registry, including name, description, areas, and links.

## Notifications

The notification system proxies the nudging-tool:
- List notifications with read/unread filtering
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

## Settings

Users can configure language, units, and notification preferences via `GET/PUT /api/settings`. Settings are stored in the local database.
