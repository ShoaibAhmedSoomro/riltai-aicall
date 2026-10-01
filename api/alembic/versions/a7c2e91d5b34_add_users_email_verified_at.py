"""add users.email_verified_at

Nullable, no default, no backfill. NULL means "never verified", which is the
honest state for every account created before verification existed: nobody has
proved they control those mailboxes, and stamping them verified here would be
asserting something this migration has no way of knowing.

Nothing gates on it. Login, API keys and every existing route behave exactly as
before, so this cannot lock out the accounts that predate it or a deployment
that has no email configured. It only records a fact.

Adding a nullable column with no default is a metadata-only change in
PostgreSQL, so unlike the index migration before it this takes no long lock.

Revision ID: a7c2e91d5b34
Revises: d1a4f8c30b57
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c2e91d5b34"
down_revision: Union[str, None] = "d1a4f8c30b57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
