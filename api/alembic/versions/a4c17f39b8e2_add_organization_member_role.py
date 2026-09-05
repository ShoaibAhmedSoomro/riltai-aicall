"""give organization members a role

`organization_users` has carried exactly two columns since it was created —
user_id and organization_id — so there has never been an org-level permission
tier. Every authenticated member could read the org's provider credentials,
delete another member's agents, and change org-wide configuration, because
nothing in the codebase could express that one member differs from another. The
only privilege tier that existed was users.is_superuser, which is platform-wide
and spans every organization.

This adds the missing tier. "admin" is exactly the access everyone has today;
"member" is a lesser tier that exists so dangerous actions can be gated.

Two deliberate choices:

NOT NULL with server_default "admin" backfills every existing row to admin in
the same statement, so nobody loses an ability they have right now — the tier
ships inert and you demote people deliberately afterwards. It also keeps the
single production INSERT working: OrganizationClient.add_user_to_organization
does not pass a role and is ON CONFLICT DO NOTHING, so a row is written once
and never updated by that path.

A plain VARCHAR rather than a native enum, because the next tier ("owner") is
then a code change instead of a migration against a live table. The allowed
values are enforced at the API boundary, where the error can say something
useful.

Revision ID: a4c17f39b8e2
Revises: f3b8d47e01ca
Create Date: 2026-09-05 12:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4c17f39b8e2"
down_revision: Union[str, None] = "f3b8d47e01ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_users",
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default="admin",
        ),
    )
    # Index the lookup this column exists to serve: "what is this user's role in
    # this org", resolved on every admin-gated request. The composite primary key
    # already covers (user_id, organization_id) so the row is found by PK — this
    # is here for the reverse question, "who are the admins of this org", which
    # the members list and the last-admin guard both ask.
    op.create_index(
        "ix_organization_users_org_role",
        "organization_users",
        ["organization_id", "role"],
    )


def downgrade() -> None:
    op.drop_index("ix_organization_users_org_role", table_name="organization_users")
    op.drop_column("organization_users", "role")
