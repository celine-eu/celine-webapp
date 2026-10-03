"""Policy acceptance per document: which community, which document, which text.

Until now a row said only "this user accepted the global `POLICY_VERSION`". With a legal
host (`LEGAL_BASE_URL`) each community has its own terms and privacy notice, each with its
own versions, so a row records what was accepted:

- `community_key`: the user's community;
- `document`: the slot (`terms`, `privacy`); NULL on a row of the old global policy;
- `locale`, `document_url` and `document_sha256`: the page as shown.

`policy_version` becomes nullable: before the legal host has ever answered, the version is
not known, and the acceptance's date says which one it was (the host's dated history).

Existing rows are kept as they are, with `document` NULL: they keep meaning "the global
policy at that version".

Revision ID: 008
Revises: 007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = (
    sa.Column("community_key", sa.String(length=255), nullable=True),
    sa.Column("document", sa.String(length=64), nullable=True),
    sa.Column("locale", sa.String(length=16), nullable=True),
    sa.Column("document_url", sa.Text(), nullable=True),
    sa.Column("document_sha256", sa.String(length=64), nullable=True),
)


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("policy_acceptance")}
    for column in NEW:
        if column.name not in have:
            op.add_column("policy_acceptance", column.copy())
    op.alter_column("policy_acceptance", "policy_version", existing_type=sa.String(length=50), nullable=True)
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("policy_acceptance")}
    if "ix_policy_acceptance_user_document" not in indexes:
        op.create_index(
            "ix_policy_acceptance_user_document",
            "policy_acceptance",
            ["user_id", "community_key", "document"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_policy_acceptance_user_document", table_name="policy_acceptance")
    op.execute("DELETE FROM policy_acceptance WHERE policy_version IS NULL")
    op.alter_column("policy_acceptance", "policy_version", existing_type=sa.String(length=50), nullable=False)
    for column in reversed(NEW):
        op.drop_column("policy_acceptance", column.name)
