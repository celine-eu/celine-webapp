"""Pydantic schemas for API requests and responses."""

import re
from pydantic import BaseModel, Field
from pydantic import model_validator
from typing import Literal, Optional


# User schemas
class UserBase(BaseModel):
    """Base user schema."""

    sub: str
    email: str
    name: str


class UserInDB(UserBase):
    """User in database."""

    id: int

    class Config:
        from_attributes = True


# Me endpoint
class MeResponse(BaseModel):
    """Response for /api/me endpoint."""

    user: dict
    terms_required: bool
    policy_version: str
    accepted_policy_version: Optional[str] = None
    simple_mode: bool = False
    font_scale: float = 1.0
    notification_permission: Literal["default", "granted", "denied"] = "default"
    webpush_configured: bool = False


# Terms
class AcceptTermsRequest(BaseModel):
    """Request to accept terms."""

    accept: bool = True


# Overview
class OverviewResponse(BaseModel):
    """Response for overview endpoint."""

    period: str
    user: dict
    rec: dict
    trend: list[dict]
    devices: list[dict]


# Notifications
class NotificationItem(BaseModel):
    """Notification item."""

    id: str
    created_at: str
    title: str
    body: str
    severity: Literal["info", "warning", "critical"]
    read_at: Optional[str] = None
    deleted_at: Optional[str] = None


# Settings
class NotificationSettingsModel(BaseModel):
    """Notification settings."""

    email_enabled: bool = False
    email: str = ""
    webpush_enabled: bool = False
    limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def validate_email_notifications(self) -> "NotificationSettingsModel":
        if not self.email_enabled:
            return self

        email = (self.email or "").strip()
        if not email:
            raise ValueError("Email address is required when email notifications are enabled")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise ValueError("Email address format is invalid")
        self.email = email
        return self


# Settings
class SettingsModel(BaseModel):
    """User settings model."""

    simple_mode: bool = False
    font_scale: float = Field(default=1.0, ge=0.9, le=1.3)
    notifications: NotificationSettingsModel = Field(
        default_factory=NotificationSettingsModel
    )


# WebPush
class WebPushUnsubscribeRequest(BaseModel):
    """Request to unsubscribe from web push."""

    endpoint: str


class VapidKeyResponse(BaseModel):
    """VAPID public key response."""

    public_key: str


# Generic responses
class SuccessResponse(BaseModel):
    """Generic success response."""

    ok: bool = True


class PushSubscriptionPayload(BaseModel):
    """What the browser sends after navigator.serviceWorker.pushManager.subscribe()"""

    endpoint: str
    p256dh: str
    auth: str


class PushSubscriptionUnsubscribePayload(BaseModel):

    endpoint: str


# ─── Weather schemas ─────────────────────────────────────────────────────────

class WeatherCurrent(BaseModel):
    temp: float
    humidity: int
    uvi: float
    clouds: int
    wind_deg: int
    weather_main: str
    weather_description: str
    sunrise: str
    sunset: str


class WeatherDayItem(BaseModel):
    date: str
    temp_min: float
    temp_max: float
    temp_day: float
    pop: float
    rain: Optional[float] = None
    clouds: int
    uvi: float
    weather_main: str
    weather_description: str
    summary: Optional[str] = None


class WeatherAlertItem(BaseModel):
    event: str
    sender_name: str
    start_ts: str
    end_ts: str
    description: str


class WeatherIrradianceItem(BaseModel):
    ts: str
    shortwave_radiation: float
    diffuse_radiation: float
    global_tilted_irradiance: float
    cloud_cover: float


class WeatherResponse(BaseModel):
    current: Optional[WeatherCurrent] = None
    daily: list[WeatherDayItem] = []
    hourly_irradiance: list[WeatherIrradianceItem] = []
    alerts: list[WeatherAlertItem] = []


# ─── Forecast schemas ─────────────────────────────────────────────────────────

class ForecastHourItem(BaseModel):
    ts: str
    value: float
    lower: Optional[float] = None
    upper: Optional[float] = None
    period: str  # "actual" | "forecast"


class ForecastResponse(BaseModel):
    user_forecast: list[ForecastHourItem] = []
    rec_forecast: list[ForecastHourItem] = []


# ─── Suggestions schemas ──────────────────────────────────────────────────────

class SuggestionItem(BaseModel):
    id: str
    suggestion_type: str
    period_start: str
    period_end: str
    from_label: str
    to_label: str
    impact_kwh_estimated: float
    reward_points: int
    confidence: float
    description: str
    reason: str


class SuggestionRespondRequest(BaseModel):
    response: Literal["accepted", "declined"]


# ─── Gamification schemas ─────────────────────────────────────────────────────

class BadgeItem(BaseModel):
    badge_id: str
    label: str
    icon: str
    earned_at: str


class GamificationResponse(BaseModel):
    total_points: int
    level: int
    next_level_at: int
    badges: list[BadgeItem] = []
    actions_taken: int
