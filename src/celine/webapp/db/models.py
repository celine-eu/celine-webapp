"""SQLAlchemy database models."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Boolean, DateTime, Integer, Uuid, Text, LargeBinary, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class PolicyAcceptance(Base):
    """Policy acceptance tracking."""

    __tablename__ = "policy_acceptance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_from_ip: Mapped[Optional[str]] = mapped_column(String(50))


class Settings(Base):
    """User settings."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    simple_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    font_scale: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    email_notifications: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    webpush_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SuggestionInteraction(Base):
    """Records user responses to load-shifting suggestions."""

    __tablename__ = "suggestion_interactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    suggestion_id: Mapped[str] = mapped_column(String(255), nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    response: Mapped[str] = mapped_column(String(20), nullable=False)
    impact_kwh_estimated: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reward_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserBadge(Base):
    """Badges earned by users."""

    __tablename__ = "user_badges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    badge_id: Mapped[str] = mapped_column(String(50), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FeedbackEntry(Base):
    """Stores user feedback together with page diagnostics."""

    __tablename__ = "feedback_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    page_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locale: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    viewport_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    viewport_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    screen_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    screen_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    color_scheme: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    client_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    extra_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    screenshot_mime_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    screenshot_bytes: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
