"""SQLAlchemy database models."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Boolean, DateTime, Text, JSON, Integer
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
