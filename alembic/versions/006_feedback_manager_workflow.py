"""Add REC ownership and manager review state to participant feedback.

Revision ID: 006
Revises: 005
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("feedback_entries"):
        # Feedback originally pre-dated an Alembic revision and was created by
        # Base.metadata.create_all(). A clean installation must not depend on
        # starting the API before running migrations.
        op.create_table(
            "feedback_entries",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("community_key", sa.String(length=255), nullable=True),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("page_url", sa.Text(), nullable=False),
            sa.Column("page_title", sa.Text(), nullable=True),
            sa.Column("page_path", sa.Text(), nullable=True),
            sa.Column("locale", sa.String(length=32), nullable=True),
            sa.Column("timezone", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("viewport_width", sa.Integer(), nullable=True),
            sa.Column("viewport_height", sa.Integer(), nullable=True),
            sa.Column("screen_width", sa.Integer(), nullable=True),
            sa.Column("screen_height", sa.Integer(), nullable=True),
            sa.Column("color_scheme", sa.String(length=16), nullable=True),
            sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=True),
            sa.Column("client_ip", sa.String(length=50), nullable=True),
            sa.Column("extra_context", sa.JSON(), nullable=True),
            sa.Column("screenshot_mime_type", sa.String(length=64), nullable=True),
            sa.Column("screenshot_bytes", sa.LargeBinary(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=16),
                server_default="new",
                nullable=False,
            ),
            sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status_updated_by", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_feedback_entries_user_id",
            "feedback_entries",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            "ix_feedback_entries_community_key",
            "feedback_entries",
            ["community_key"],
            unique=False,
        )
        op.create_index(
            "ix_feedback_entries_community_status",
            "feedback_entries",
            ["community_key", "status"],
            unique=False,
        )
        return

    op.add_column(
        "feedback_entries", sa.Column("community_key", sa.String(length=255), nullable=True)
    )
    # The participant UI has recorded this diagnostic since feedback collection was
    # introduced. Promote it to ownership rather than guessing from user ids.
    op.execute(
        "UPDATE feedback_entries SET community_key = extra_context ->> 'community_key' "
        "WHERE community_key IS NULL AND extra_context ->> 'community_key' IS NOT NULL"
    )
    op.add_column(
        "feedback_entries",
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
    )
    op.add_column(
        "feedback_entries", sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "feedback_entries", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "feedback_entries", sa.Column("status_updated_by", sa.String(length=255), nullable=True)
    )
    op.create_index(
        "ix_feedback_entries_community_key", "feedback_entries", ["community_key"], unique=False
    )
    op.create_index(
        "ix_feedback_entries_community_status",
        "feedback_entries",
        ["community_key", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_entries_community_status", table_name="feedback_entries")
    op.drop_index("ix_feedback_entries_community_key", table_name="feedback_entries")
    op.drop_column("feedback_entries", "status_updated_by")
    op.drop_column("feedback_entries", "resolved_at")
    op.drop_column("feedback_entries", "seen_at")
    op.drop_column("feedback_entries", "status")
    op.drop_column("feedback_entries", "community_key")
