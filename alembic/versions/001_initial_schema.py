"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-06 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # Policy acceptance table
    op.create_table(
        "policy_acceptance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_from_ip", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_policy_acceptance_user_id"),
        "policy_acceptance",
        ["user_id"],
        unique=False,
    )

    # Settings table
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("simple_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("font_scale", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "email_notifications", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_settings_user_id"), "settings", ["user_id"], unique=True)

    # WebPush subscriptions table
    op.create_table(
        "webpush_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("subscription_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_webpush_subscriptions_user_id"),
        "webpush_subscriptions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_webpush_subscriptions_user_id"), table_name="webpush_subscriptions"
    )
    op.drop_table("webpush_subscriptions")
    op.drop_index(op.f("ix_settings_user_id"), table_name="settings")
    op.drop_table("settings")
    op.drop_index(op.f("ix_policy_acceptance_user_id"), table_name="policy_acceptance")
    op.drop_table("policy_acceptance")
