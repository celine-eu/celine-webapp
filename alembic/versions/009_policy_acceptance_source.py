"""Policy acceptance source: an acceptance copied from the member's application.

The terms gate copies, on a miss, an acceptance the member gave in onboarding's form when
its version and sha256 match the text served now (`celine.webapp.legal`). Such a row says
where it came from:

- `source`: `onboarding`; NULL on a row accepted in this app's gate;
- `source_ref`: the onboarding submission id.

Existing rows were all accepted here: NULL.

Revision ID: 009
Revises: 008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = (
    sa.Column("source", sa.String(length=32), nullable=True),
    sa.Column("source_ref", sa.String(length=64), nullable=True),
)


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("policy_acceptance")}
    for column in NEW:
        if column.name not in have:
            op.add_column("policy_acceptance", column.copy())


def downgrade() -> None:
    for column in reversed(NEW):
        op.drop_column("policy_acceptance", column.name)
