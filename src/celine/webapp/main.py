import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db, connect, q1, qall
from .auth import get_user_from_request, User
from .models import (
    MeResponse,
    AcceptTermsRequest,
    OverviewResponse,
    NotificationItem,
    SettingsModel,
    WebPushUnsubscribeRequest,
)

POLICY_VERSION = os.environ.get("REC_POLICY_VERSION", "2026-02-01")

VAPID_PUBLIC_KEY = os.environ.get(
    "REC_VAPID_PUBLIC_KEY", "BEl6E7l0vYd-EXAMPLE-REPLACE-ME"
)
# VAPID private key is intentionally not used in this scaffold.

app = FastAPI(title="REC Webapp BFF", version="0.1.0")

# In production, same-origin behind oauth2_proxy -> CORS not needed.
# For local dev, enabling permissive CORS can be handy.
if os.environ.get("REC_DEV_CORS", "0") == "1":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def _startup() -> None:
    init_db()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def ensure_user_row(user: User) -> None:
    with connect() as conn:
        existing = q1(conn, "select user_id from users where user_id = ?", (user.sub,))
        if not existing:
            # Default: no smart meter; can be toggled later by admin tooling.
            conn.execute(
                "insert into users(user_id, email, name, has_smart_meter) values(?,?,?,?)",
                (user.sub, user.email, user.name, 0),
            )
        # Ensure settings row
        s = q1(conn, "select user_id from settings where user_id = ?", (user.sub,))
        if not s:
            conn.execute(
                "insert into settings(user_id, simple_mode, font_scale, email_notifications) values(?,?,?,?)",
                (user.sub, 0, 1.0, 0),
            )

        # Seed a couple of notifications for UX demo if none exist
        cnt = q1(
            conn,
            "select count(1) as c from notifications where user_id = ?",
            (user.sub,),
        )
        if cnt and int(cnt["c"]) == 0:
            for i in range(2):
                nid = str(uuid.uuid4())
                conn.execute(
                    "insert into notifications(id, user_id, created_at, title, body, severity, read_at) values(?,?,?,?,?,?,?)",
                    (
                        nid,
                        user.sub,
                        (
                            datetime.now(timezone.utc) - timedelta(hours=6 * (i + 1))
                        ).isoformat(),
                        "Suggestion: consume when clean energy is high",
                        "This is a stub notification. You will receive real indications once nudging is integrated.",
                        "info" if i == 0 else "warning",
                        None,
                    ),
                )


def terms_required_for(user_id: str) -> tuple[bool, str | None]:
    with connect() as conn:
        row = q1(
            conn,
            "select policy_version from policy_acceptance where user_id = ? and policy_version = ?",
            (user_id, POLICY_VERSION),
        )
        return (row is None, row["policy_version"] if row else None)


def has_smart_meter(user_id: str) -> bool:
    with connect() as conn:
        row = q1(
            conn, "select has_smart_meter from users where user_id = ?", (user_id,)
        )
        return bool(row and int(row["has_smart_meter"]) == 1)


def get_settings(user_id: str) -> SettingsModel:
    with connect() as conn:
        row = q1(
            conn,
            "select simple_mode, font_scale, email_notifications from settings where user_id = ?",
            (user_id,),
        )
        if not row:
            return SettingsModel()
        return SettingsModel(
            simple_mode=bool(int(row["simple_mode"])),
            font_scale=float(row["font_scale"]),
            notifications={"email_enabled": bool(int(row["email_notifications"]))},
        )


def webpush_configured(user_id: str) -> bool:
    with connect() as conn:
        row = q1(
            conn,
            "select 1 as one from webpush_subscriptions where user_id = ? limit 1",
            (user_id,),
        )
        return row is not None


@app.get("/api/me", response_model=MeResponse)
def me(request: Request, user: User = Depends(get_user_from_request)) -> MeResponse:
    ensure_user_row(user)
    required, accepted_version = terms_required_for(user.sub)
    s = get_settings(user.sub)
    return MeResponse(
        user={"sub": user.sub, "email": user.email, "name": user.name},
        has_smart_meter=has_smart_meter(user.sub),
        terms_required=required,
        policy_version=POLICY_VERSION,
        accepted_policy_version=accepted_version,
        simple_mode=s.simple_mode,
        font_scale=s.font_scale,
        notification_permission=request.headers.get(
            "X-REC-Notification-Permission", "default"
        ),
        webpush_configured=webpush_configured(user.sub),
    )


@app.post("/api/terms/accept")
def accept_terms(
    request: Request,
    body: AcceptTermsRequest,
    user: User = Depends(get_user_from_request),
) -> JSONResponse:
    ensure_user_row(user)
    if not body.accept:
        return JSONResponse(status_code=400, content={"detail": "accept must be true"})
    with connect() as conn:
        conn.execute(
            "insert or ignore into policy_acceptance(user_id, policy_version, accepted_at, accepted_from_ip) values(?,?,?,?)",
            (user.sub, POLICY_VERSION, now_iso(), client_ip(request)),
        )
    return JSONResponse(content={"ok": True})


@app.get("/api/overview", response_model=OverviewResponse)
def overview(user: User = Depends(get_user_from_request)) -> OverviewResponse:
    ensure_user_row(user)
    # Stubbed KPIs until Digital Twin integration exists
    user_has_prod = False  # could be inferred from DT later
    user_consumption = 42.3
    user_production = 18.7 if user_has_prod else None
    user_self = 12.1 if user_has_prod else None
    user_rate = (
        (user_self / user_consumption)
        if (user_self is not None and user_consumption > 0)
        else None
    )

    rec_prod = 1200.0
    rec_cons = 1650.0
    rec_self = 980.0
    rec_rate = rec_self / rec_cons if rec_cons > 0 else 0.0

    base = datetime.now(timezone.utc).date()
    trend = []
    for d in range(7):
        day = (base - timedelta(days=(6 - d))).isoformat()
        trend.append(
            {
                "date": day,
                "production_kwh": 160.0 + d * 5.0,
                "consumption_kwh": 220.0 + d * 3.0,
                "self_consumption_kwh": 130.0 + d * 4.0,
            }
        )

    return OverviewResponse(
        period="Last 7 days",
        user={
            "production_kwh": user_production,
            "consumption_kwh": user_consumption,
            "self_consumption_kwh": user_self,
            "self_consumption_rate": user_rate,
        },
        rec={
            "production_kwh": rec_prod,
            "consumption_kwh": rec_cons,
            "self_consumption_kwh": rec_self,
            "self_consumption_rate": rec_rate,
        },
        trend=trend,
    )


@app.get("/api/notifications", response_model=list[NotificationItem])
def notifications(
    user: User = Depends(get_user_from_request),
) -> list[NotificationItem]:
    ensure_user_row(user)
    with connect() as conn:
        rows = qall(
            conn,
            "select id, created_at, title, body, severity, read_at from notifications where user_id = ? order by created_at desc limit 50",
            (user.sub,),
        )
    return [
        NotificationItem(
            id=r["id"],
            created_at=r["created_at"],
            title=r["title"],
            body=r["body"],
            severity=r["severity"],
            read_at=r["read_at"],
        )
        for r in rows
    ]


@app.post("/api/notifications/enable")
def enable_notifications(user: User = Depends(get_user_from_request)) -> JSONResponse:
    ensure_user_row(user)
    # Idempotent placeholder: in a real implementation this might register the user in the nudging tool
    return JSONResponse(content={"ok": True})


@app.get("/api/notifications/webpush/vapid-public-key")
def vapid_public_key(user: User = Depends(get_user_from_request)) -> JSONResponse:
    ensure_user_row(user)
    return JSONResponse(content={"public_key": VAPID_PUBLIC_KEY})


@app.post("/api/notifications/webpush/subscribe")
async def webpush_subscribe(
    request: Request, user: User = Depends(get_user_from_request)
) -> JSONResponse:
    ensure_user_row(user)
    data = await request.json()
    endpoint = data.get("endpoint")
    if not endpoint:
        return JSONResponse(
            status_code=400, content={"detail": "subscription endpoint missing"}
        )
    with connect() as conn:
        conn.execute(
            "insert or replace into webpush_subscriptions(user_id, endpoint, subscription_json, created_at) values(?,?,?,?)",
            (user.sub, endpoint, json.dumps(data), now_iso()),
        )
    return JSONResponse(content={"ok": True})


@app.post("/api/notifications/webpush/unsubscribe")
async def webpush_unsubscribe(
    body: WebPushUnsubscribeRequest, user: User = Depends(get_user_from_request)
) -> JSONResponse:
    ensure_user_row(user)
    with connect() as conn:
        conn.execute(
            "delete from webpush_subscriptions where user_id = ? and endpoint = ?",
            (user.sub, body.endpoint),
        )
    return JSONResponse(content={"ok": True})


@app.get("/api/settings", response_model=SettingsModel)
def settings_get(user: User = Depends(get_user_from_request)) -> SettingsModel:
    ensure_user_row(user)
    return get_settings(user.sub)


@app.put("/api/settings", response_model=SettingsModel)
async def settings_put(
    request: Request, user: User = Depends(get_user_from_request)
) -> SettingsModel:
    ensure_user_row(user)
    data = await request.json()
    model = SettingsModel.model_validate(data)
    with connect() as conn:
        conn.execute(
            "update settings set simple_mode = ?, font_scale = ?, email_notifications = ? where user_id = ?",
            (
                1 if model.simple_mode else 0,
                float(model.font_scale),
                1 if bool(model.notifications.get("email_enabled")) else 0,
                user.sub,
            ),
        )
    return model


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8014")))
