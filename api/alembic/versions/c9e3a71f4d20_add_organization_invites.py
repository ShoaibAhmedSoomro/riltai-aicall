"""let an admin invite someone into an organization

There is no invite, remove-member or leave-org path anywhere in this codebase.
On the hosted path the auth provider owns invites; on OSS an organization can
never gain a second person at all, which makes the admin/member tier real in the
database and unusable in the product.

This adds the record. Delivery is deliberately NOT part of it: nothing in the
codebase can send email, so the token is generated and stored but never
transmitted yet. Building the row and the token now means adding email later is
the sending step rather than a redesign.

The pending-uniqueness index is partial on purpose. A plain unique constraint on
(organization_id, email) would mean a revoked or expired invite blocks ever
re-inviting that person, which is the first thing someone hits when an invite
times out. Partial on "still pending" allows exactly one live invite per address
while keeping the history.

Revoked and accepted invites are kept rather than deleted, because "who invited
whom, and what happened" is the first question asked when access is disputed.

Revision ID: c9e3a71f4d20
Revises: b8d5e2f14c73
Create Date: 2026-09-05 14:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e3a71f4d20"
down_revision: Union[str, None] = "b8d5e2f14c73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        # 320 = the maximum length of an email address per RFC 3696 errata.
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role", sa.String(length=32), nullable=False, server_default="member"
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        # invited_by is NOT cascaded: deleting the inviter must not erase the
        # record of who was invited. It goes null instead.
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organization_invites_organization_id",
        "organization_invites",
        ["organization_id"],
    )
    op.create_index("ix_organization_invites_email", "organization_invites", ["email"])
    op.create_index(
        "ix_organization_invites_token", "organization_invites", ["token"], unique=True
    )
    op.create_index(
        "uq_org_invite_pending_email",
        "organization_invites",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_org_invite_pending_email", table_name="organization_invites")
    op.drop_index("ix_organization_invites_token", table_name="organization_invites")
    op.drop_index("ix_organization_invites_email", table_name="organization_invites")
    op.drop_index(
        "ix_organization_invites_organization_id", table_name="organization_invites"
    )
    op.drop_table("organization_invites")
