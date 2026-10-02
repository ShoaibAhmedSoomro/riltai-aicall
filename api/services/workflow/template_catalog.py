"""The starter-template catalog: JSON files in ``templates/catalog/``, loaded into
``workflow_templates`` at boot.

Each file is ``{slug, name, description, category, definition}``. ``definition`` is a
real exported graph, so a template is exactly what the editor would have saved.
The slug is the identity (the name is display text and may be reworded), which makes
seeding an upsert: safe on every boot, and safe when two web processes boot at once
(the UNIQUE slug makes the loser's insert fail instead of duplicating).

Templates are organization-neutral. They never reference tools, documents,
recordings or credentials, because those belong to one organization and would dangle
for every other (see ORG_SCOPED_FIELDS and the catalog test).
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, ConfigDict

from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph

CATALOG_DIR = Path(__file__).parent / "templates" / "catalog"

CATEGORIES = (
    "receptionist",
    "outbound-sales",
    "appointment-booking",
    "lead-qualification",
    "customer-support",
)

# Node fields that point at rows owned by one organization.
ORG_SCOPED_FIELDS = (
    "tool_uuids",
    "document_uuids",
    "greeting_recording_id",
    "pre_call_fetch_credential_uuid",
)


class CatalogEntry(BaseModel):
    slug: str
    name: str
    description: str
    category: str
    definition: dict

    model_config = ConfigDict(extra="forbid")


def load_catalog(directory: Path = CATALOG_DIR) -> list[CatalogEntry]:
    """Read and validate every catalog file; raises on the first bad one.

    Validation is the same pair publish uses (DTO, then graph), so nothing can ship
    that the product would refuse to publish.
    """
    entries = []
    for path in sorted(directory.glob("*.json")):
        entry = CatalogEntry.model_validate(json.loads(path.read_text(encoding="utf-8")))
        WorkflowGraph(ReactFlowDTO.model_validate(entry.definition))
        entries.append(entry)
    return entries


async def seed_catalog() -> int:
    """Upsert the catalog by slug; returns how many entries were written.

    One bad file or one failed row is logged and skipped. Boot must never depend on
    this.
    """
    from api.db.workflow_template_client import WorkflowTemplateClient

    client = WorkflowTemplateClient()
    written = 0
    for path in sorted(CATALOG_DIR.glob("*.json")):
        try:
            entry = CatalogEntry.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            WorkflowGraph(ReactFlowDTO.model_validate(entry.definition))
            existing = await client.get_workflow_template_by_slug(entry.slug)
            if existing:
                await client.update_workflow_template(
                    existing.id,
                    template_name=entry.name,
                    template_json=entry.definition,
                    template_description=entry.description,
                    category=entry.category,
                )
            else:
                await client.create_workflow_template(
                    entry.name,
                    entry.description,
                    entry.definition,
                    slug=entry.slug,
                    category=entry.category,
                )
            written += 1
        except Exception as e:
            # Includes the lost race on the unique slug; the winner wrote it.
            logger.warning(f"Template catalog: skipped {path.name}: {e}")
    return written
