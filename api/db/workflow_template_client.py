from uuid import uuid4

from sqlalchemy.future import select

from api.db.base_client import BaseDBClient
from api.db.models import WorkflowTemplates


class WorkflowTemplateClient(BaseDBClient):
    async def get_workflow_template(self, template_id: int) -> WorkflowTemplates | None:
        """Get a workflow template by ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowTemplates).where(WorkflowTemplates.id == template_id)
            )
            return result.scalars().first()

    async def get_workflow_template_by_name(
        self, template_name: str
    ) -> WorkflowTemplates | None:
        """Get a workflow template by name."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowTemplates).where(
                    WorkflowTemplates.template_name == template_name
                )
            )
            return result.scalars().first()

    async def get_workflow_template_by_slug(
        self, slug: str
    ) -> WorkflowTemplates | None:
        """Get a workflow template by its catalog slug."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowTemplates).where(WorkflowTemplates.slug == slug)
            )
            return result.scalars().first()

    async def get_all_workflow_templates(
        self, category: str | None = None
    ) -> list[WorkflowTemplates]:
        """Get all workflow templates, optionally one category (filtered in SQL)."""
        query = select(WorkflowTemplates).order_by(WorkflowTemplates.id)
        if category:
            query = query.where(WorkflowTemplates.category == category)
        async with self.async_session() as session:
            result = await session.execute(query)
            return result.scalars().all()

    async def create_workflow_template(
        self,
        template_name: str,
        template_description: str,
        template_json: dict,
        slug: str | None = None,
        category: str = "general",
    ) -> WorkflowTemplates:
        """Create a new workflow template."""
        async with self.async_session() as session:
            try:
                new_template = WorkflowTemplates(
                    template_name=template_name,
                    template_description=template_description,
                    template_json=template_json,
                    # Callers without a catalog slug still get a unique one.
                    slug=slug or f"template-{uuid4().hex[:12]}",
                    category=category,
                )
                session.add(new_template)
                await session.commit()
                await session.refresh(new_template)
                return new_template
            except Exception as e:
                await session.rollback()
                raise e

    async def update_workflow_template(
        self,
        template_id: int,
        template_name: str | None = None,
        template_json: dict | None = None,
        template_description: str | None = None,
        category: str | None = None,
    ) -> WorkflowTemplates:
        """Update an existing workflow template."""
        async with self.async_session() as session:
            try:
                result = await session.execute(
                    select(WorkflowTemplates).where(WorkflowTemplates.id == template_id)
                )
                template = result.scalars().first()
                if not template:
                    raise ValueError(
                        f"Workflow template with ID {template_id} not found"
                    )

                if template_name is not None:
                    template.template_name = template_name
                if template_json is not None:
                    template.template_json = template_json
                if template_description is not None:
                    template.template_description = template_description
                if category is not None:
                    template.category = category

                await session.commit()
                await session.refresh(template)
                return template
            except Exception as e:
                await session.rollback()
                raise e

    async def delete_workflow_template(self, template_id: int) -> bool:
        """Delete a workflow template by ID."""
        async with self.async_session() as session:
            try:
                result = await session.execute(
                    select(WorkflowTemplates).where(WorkflowTemplates.id == template_id)
                )
                template = result.scalars().first()
                if not template:
                    return False

                await session.delete(template)
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                raise e
