"""contacts: people, lists, imports and a do-not-call list

Five tables, plus the index a contact's call history needs.

``contacts`` is unique on (organization_id, phone_e164): that is the dedupe key,
and the whole import design leans on it. ``contact_suppressions`` is a table and
not a flag on contacts on purpose -- see ContactModel.

ix_workflow_runs_called_number is built CONCURRENTLY for the reason d1a4f8c30b57
spells out: migrations run in the api container's CMD before uvicorn starts, and a
plain CREATE INDEX on the biggest table holds a lock on the call path. The
expression is ``initial_context ->> 'called_number'`` and the history query uses
that exact form, so the index can actually be used.

Revision ID: d6a2f93b1c84
Revises: c3f7a1d9e502
Create Date: 2026-10-02 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6a2f93b1c84"
down_revision: Union[str, None] = "c3f7a1d9e502"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CALLED_NUMBER_INDEX = "ix_workflow_runs_called_number"


def _now():
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_uuid", sa.String(36), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column(
            "attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")
        ),
        sa.Column("last_called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_disposition", sa.String(), nullable=True),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.UniqueConstraint("organization_id", "phone_e164", name="uq_contacts_org_phone"),
    )
    op.create_index("ix_contacts_id", "contacts", ["id"])
    op.create_index("ix_contacts_contact_uuid", "contacts", ["contact_uuid"], unique=True)
    op.create_index(
        "ix_contacts_org_created", "contacts", ["organization_id", "created_at"]
    )

    op.create_table(
        "contact_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("list_uuid", sa.String(36), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.UniqueConstraint("organization_id", "name", name="uq_contact_lists_org_name"),
    )
    op.create_index("ix_contact_lists_id", "contact_lists", ["id"])
    op.create_index(
        "ix_contact_lists_list_uuid", "contact_lists", ["list_uuid"], unique=True
    )

    op.create_table(
        "contact_list_members",
        sa.Column(
            "contact_list_id",
            sa.Integer(),
            sa.ForeignKey("contact_lists.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "contact_id",
            sa.Integer(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=_now()),
    )
    op.create_index(
        "ix_contact_list_members_contact", "contact_list_members", ["contact_id"]
    )

    op.create_table(
        "contact_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_uuid", sa.String(36), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_list_id",
            sa.Integer(),
            sa.ForeignKey("contact_lists.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column(
            "column_mapping", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")
        ),
        sa.Column(
            "dedupe_strategy",
            sa.Enum("skip", "update", name="contact_dedupe_strategy"),
            nullable=False,
            server_default=sa.text("'skip'::contact_dedupe_strategy"),
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "failed",
                name="contact_import_status",
            ),
            nullable=False,
            server_default=sa.text("'pending'::contact_import_status"),
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_report_key", sa.String(), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now()),
    )
    op.create_index("ix_contact_imports_id", "contact_imports", ["id"])
    op.create_index(
        "ix_contact_imports_import_uuid", "contact_imports", ["import_uuid"], unique=True
    )

    op.create_table(
        "contact_suppressions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "manual", "csv", "call_disposition", "api", name="contact_suppression_source"
            ),
            nullable=False,
            server_default=sa.text("'manual'::contact_suppression_source"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.UniqueConstraint(
            "organization_id", "phone_e164", name="uq_suppression_org_phone"
        ),
    )
    op.create_index("ix_contact_suppressions_id", "contact_suppressions", ["id"])

    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {CALLED_NUMBER_INDEX} "
            "ON workflow_runs ((initial_context ->> 'called_number'))"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {CALLED_NUMBER_INDEX}")

    op.drop_table("contact_suppressions")
    op.drop_table("contact_imports")
    op.drop_table("contact_list_members")
    op.drop_table("contact_lists")
    op.drop_table("contacts")
    for enum in (
        "contact_suppression_source",
        "contact_import_status",
        "contact_dedupe_strategy",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum}")
