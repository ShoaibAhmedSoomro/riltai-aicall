"""governance: retention deadline on runs, and who edited/published a version

Two unrelated columns groups that ship together because both are governance and
both sit on top of the same single head.

workflow_runs.retention_expires_at / purged_at
    The deadline is STAMPED when a run is created rather than joined in at purge
    time, so the purge is one indexed scan with no join, and a later policy
    change does not re-age or resurrect runs that already exist. NULL means
    "never purge" -- the operator's standing decision, so the purge can only
    ever delete data somebody deliberately marked. purged_at records that a
    run's artifacts were removed; the row itself is kept so reports and cost
    figures do not change retroactively.

workflow_definitions.created_by / updated_by / published_by
    The version lifecycle plus the side-by-side diff already IS the change
    history for an agent. It was missing only an actor, so add columns rather
    than a parallel audit table. Nullable: every existing version predates this
    and nobody can honestly be named for it.

The partial index is built CONCURRENTLY for the reason d1a4f8c30b57 spells out:
migrations run in the api container's CMD before uvicorn starts, and a plain
CREATE INDEX on the biggest table would hold a lock on the call path.

Revision ID: c3f7a1d9e502
Revises: a7c2e91d5b34
Create Date: 2026-10-02 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f7a1d9e502"
down_revision: Union[str, None] = "a7c2e91d5b34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "idx_workflow_runs_retention_due"


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("created_by", "updated_by", "published_by"):
        op.add_column(
            "workflow_definitions",
            sa.Column(col, sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )

    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} "
            "ON workflow_runs (retention_expires_at) "
            "WHERE retention_expires_at IS NOT NULL AND purged_at IS NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
    for col in ("published_by", "updated_by", "created_by"):
        op.drop_column("workflow_definitions", col)
    op.drop_column("workflow_runs", "purged_at")
    op.drop_column("workflow_runs", "retention_expires_at")
