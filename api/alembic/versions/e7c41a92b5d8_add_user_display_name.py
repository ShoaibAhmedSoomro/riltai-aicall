"""give users a display name that actually persists

``UserResponse`` has always declared ``name``, ``SignupRequest`` has always
accepted it, and ``/auth/signup`` echoes it straight back in its response — but
there was nowhere to put it. ``create_user_with_email`` took the argument and
dropped it on the floor (api/db/user_client.py), because ``users`` had no such
column. So a self-hosted user typed a name at signup, saw it in the response,
and it was gone by the next request.

This adds the column so the existing contract becomes true, and so profile
editing has something to edit: the local auth provider had no way to change any
user detail at all, since the table held only credentials and bookkeeping.

Nullable with no backfill on purpose. Existing rows genuinely have no name to
restore — it was never stored — and the API falls back to the email local part
for display, so a NULL renders sensibly rather than blank.

Revision ID: e7c41a92b5d8
Revises: d4b83a1f6c27
Create Date: 2026-09-03 19:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7c41a92b5d8"
down_revision: Union[str, None] = "d4b83a1f6c27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "name")
