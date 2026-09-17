"""Offer set recorded with the data-sharing view

`user_onboarding_views.offer_set` holds, for the `data-sharing` row only, the
decidable offers (id and version) the member was shown when they last decided
or dismissed. With it the banner asks about an offer that is new or whose
version moved, and not about one the member already saw and left off.

Existing rows stay NULL: what they were shown was not recorded. Those members
are asked once more, and the set is recorded when they answer.

Revision ID: 006
Revises: 005
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_onboarding_views",
        sa.Column("offer_set", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_onboarding_views", "offer_set")
