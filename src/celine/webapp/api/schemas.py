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
