"""give users a profile blob for their own preferences

``users.name`` (e7c41a92b5d8) covered the one field the API already promised.
Everything else a person expects to set about themselves — job title, contact
number, the timezone their reports should be dated in, the colour of their
avatar — had nowhere to live, and the only per-user store in the product is the
onboarding-state row, which is a UI step tracker rather than a profile.

A single JSON column rather than a column per field, matching how the rest of
this schema already holds shaped-but-evolving data (organization_configurations
.value, user_configurations.configuration, workflow_runs.cost_info, telephony
credentials and settings). The shape is validated at the API boundary by
UserProfileFields, so the blob is not a free-for-all; this only avoids a
migration per preference.

NOT NULL with a server default so existing rows read as an empty object rather
than None, which keeps every reader from having to guard for null before
indexing into it.

Revision ID: f3b8d47e01ca
Revises: e7c41a92b5d8
Create Date: 2026-09-03 21:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b8d47e01ca"
down_revision: Union[str, None] = "e7c41a92b5d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "profile",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "profile")
