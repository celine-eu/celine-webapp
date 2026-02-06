from pydantic import BaseModel, Field
from typing import Literal

class MeResponse(BaseModel):
  user: dict
  has_smart_meter: bool
  terms_required: bool
  policy_version: str
  accepted_policy_version: str | None = None
  simple_mode: bool = False
  font_scale: float = 1.0
  notification_permission: Literal["default", "granted", "denied"] = "default"
  webpush_configured: bool = False

class AcceptTermsRequest(BaseModel):
  accept: bool = True

class OverviewResponse(BaseModel):
  period: str
  user: dict
  rec: dict
  trend: list[dict]

class NotificationItem(BaseModel):
  id: str
  created_at: str
  title: str
  body: str
  severity: Literal["info", "warning", "critical"]
  read_at: str | None = None

class SettingsModel(BaseModel):
  simple_mode: bool = False
  font_scale: float = Field(default=1.0, ge=0.9, le=1.3)
  notifications: dict = Field(default_factory=lambda: {"email_enabled": False})

class WebPushUnsubscribeRequest(BaseModel):
  endpoint: str
