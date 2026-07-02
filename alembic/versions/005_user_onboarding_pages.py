"""User onboarding pages table

Revision ID: 005
Revises: 004
Create Date: 2026-05-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_onboarding_views" not in inspector.get_table_names():
        op.create_table(
            "user_onboarding_views",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("page_key", sa.String(length=80), nullable=False),
            sa.Column(
                "seen_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "page_key", name="uq_user_onboarding_page"),
        )
        op.create_index(
            op.f("ix_user_onboarding_views_user_id"),
            "user_onboarding_views",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_user_onboarding_views_page_key"),
            "user_onboarding_views",
            ["page_key"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_onboarding_views_page_key"),
        table_name="user_onboarding_views",
    )
    op.drop_index(
        op.f("ix_user_onboarding_views_user_id"),
        table_name="user_onboarding_views",
    )
    op.drop_table("user_onboarding_views")
