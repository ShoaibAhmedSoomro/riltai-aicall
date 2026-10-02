"""workflow_runs: a partial index for "which calls are live right now"

The live-calls page asks this on a timer. workflow_runs is the largest table and has
no index on state, so without this each poll would scan it. The index holds only
rows in state 'running' -- a handful at any moment -- so it costs nothing to keep.

Built CONCURRENTLY, for the reason d1a4f8c30b57 spells out: migrations run in the api
container's CMD before uvicorn starts, and a plain CREATE INDEX on this table would
hold a lock on the call path.

Revision ID: f4c8d1e9a2b7
Revises: e7b3c4d5a6f1
Create Date: 2026-10-02 21:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "f4c8d1e9a2b7"
down_revision: Union[str, None] = "e7b3c4d5a6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "idx_workflow_runs_live"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} "
            "ON workflow_runs (workflow_id, created_at DESC) WHERE state = 'running'"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
