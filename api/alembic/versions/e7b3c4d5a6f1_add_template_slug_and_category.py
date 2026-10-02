"""workflow_templates: slug and category

``slug`` is the catalog seeder's idempotency key. ``template_name`` is display text
the catalog will want to reword, so it cannot be the identity. The UNIQUE
constraint is what makes the startup upsert safe when two web processes boot at
once: the loser gets an IntegrityError, not a duplicate row.

The table is empty in every deployment (nothing seeded it before), so NOT NULL is
safe, but a hand-inserted row still gets a slug (``template-<id>``) so the
migration is correct against any data.

Revision ID: e7b3c4d5a6f1
Revises: d6a2f93b1c84
Create Date: 2026-10-02 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3c4d5a6f1"
down_revision: Union[str, None] = "d6a2f93b1c84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workflow_templates", sa.Column("slug", sa.String(), nullable=True))
    op.execute("UPDATE workflow_templates SET slug = 'template-' || id WHERE slug IS NULL")
    op.alter_column("workflow_templates", "slug", nullable=False)
    op.create_unique_constraint(
        "uq_workflow_templates_slug", "workflow_templates", ["slug"]
    )
    # server_default so existing rows and any raw insert land in a real bucket.
    op.add_column(
        "workflow_templates",
        sa.Column(
            "category", sa.String(), nullable=False, server_default="general"
        ),
    )


def downgrade() -> None:
    op.drop_column("workflow_templates", "category")
    op.drop_constraint("uq_workflow_templates_slug", "workflow_templates", type_="unique")
    op.drop_column("workflow_templates", "slug")
