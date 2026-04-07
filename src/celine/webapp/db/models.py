"""SQLAlchemy database models."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Boolean, DateTime, Integer, Uuid
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
