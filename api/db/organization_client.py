from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, exists, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.future import select

from api.db.base_client import BaseDBClient
from api.db.models import (
    APIKeyModel,
    OrganizationModel,
    UserModel,
    organization_users_association,
)
from api.enums import OrgRole
from api.utils.api_key import generate_api_key


class OrganizationClient(BaseDBClient):
    async def get_organization_by_id(
        self, organization_id: int
    ) -> Optional[OrganizationModel]:
        """Get an organization by its ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationModel).where(OrganizationModel.id == organization_id)
            )
            return result.scalars().first()

    async def get_organization_users(self, organization_id: int) -> list[UserModel]:
        """Get all users linked to an organization (many-to-many)."""
        async with self.async_session() as session:
            result = await session.execute(
                select(UserModel)
                .join(
                    organization_users_association,
                    organization_users_association.c.user_id == UserModel.id,
                )
                .where(
                    organization_users_association.c.organization_id == organization_id
                )
                .order_by(UserModel.id)
            )
            return list(result.scalars().all())

    async def get_or_create_organization_by_provider_id(
        self, org_provider_id: str, user_id: int
    ) -> tuple[OrganizationModel, bool]:
        """Get an existing organization by provider_id or create a new one.

        Returns:
            A tuple of (organization, was_created) where was_created is True if the organization
            was created in this call, False if it already existed.
        """
        async with self.async_session() as session:
            # First try to get existing organization
            result = await session.execute(
                select(OrganizationModel).where(
                    OrganizationModel.provider_id == org_provider_id
                )
            )
            organization = result.scalars().first()

            if organization is None:
                # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING
                # This is atomic and handles race conditions at the database level

                stmt = insert(OrganizationModel.__table__).values(
                    provider_id=org_provider_id, created_at=datetime.now(timezone.utc)
                )
                # ON CONFLICT DO NOTHING - if another request already inserted, this becomes a no-op
                stmt = stmt.on_conflict_do_nothing(index_elements=["provider_id"])

                result = await session.execute(stmt)
                await session.commit()

                # Check if we actually inserted (rowcount > 0) or if there was a conflict (rowcount == 0)
                was_created = result.rowcount > 0

                # Now fetch the organization (either the one we just created or the one that existed)
                result = await session.execute(
                    select(OrganizationModel).where(
                        OrganizationModel.provider_id == org_provider_id
                    )
                )
                organization = result.scalars().first()

                if organization is None:
                    # This should never happen, but handle it just in case
                    error_msg = f"Failed to create or fetch organization with provider_id {org_provider_id}"
                    raise ValueError(error_msg)

                # Only create API key if we actually created the organization
                if was_created:
                    # Create a default API key for the new organization
                    _, key_hash, key_prefix = generate_api_key()

                    api_key = APIKeyModel(
                        organization_id=organization.id,
                        name="Default API Key",
                        key_hash=key_hash,
                        key_prefix=key_prefix,
                        is_active=True,
                        created_by=user_id,
                    )
                    session.add(api_key)
                    await session.commit()

                await session.refresh(organization)
                return organization, was_created
            return organization, False

    async def is_user_member_of_organization(
        self, user_id: int, organization_id: int
    ) -> bool:
        """Return True if the user belongs to the given organization."""
        async with self.async_session() as session:
            result = await session.execute(
                select(
                    exists().where(
                        (organization_users_association.c.user_id == user_id)
                        & (
                            organization_users_association.c.organization_id
                            == organization_id
                        )
                    )
                )
            )
            return bool(result.scalar())

    async def add_user_to_organization(
        self, user_id: int, organization_id: int, role: str = OrgRole.ADMIN.value
    ) -> None:
        """Ensure that a user is linked to an organization (many-to-many).

        The association is created only if it does not already exist.
        Uses INSERT ... ON CONFLICT DO NOTHING to handle race conditions.

        `role` defaults to admin because that is the access every member has had
        since before roles existed; changing the default would silently demote
        every future teammate on the hosted path, where the invite happens inside
        the auth provider and there is no endpoint here to override it. Demote
        deliberately via set_user_role instead.

        Note ON CONFLICT DO NOTHING makes this write-once: calling it again for an
        existing pair does NOT change that row's role.
        """
        async with self.async_session() as session:
            # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING
            # This handles race conditions at the database level

            stmt = insert(organization_users_association).values(
                user_id=user_id, organization_id=organization_id, role=role
            )
            # ON CONFLICT DO NOTHING - if another request already inserted, this becomes a no-op
            # The primary key constraint on (user_id, organization_id) will trigger the conflict
            stmt = stmt.on_conflict_do_nothing()

            await session.execute(stmt)
            await session.commit()

    async def get_user_role(self, user_id: int, organization_id: int) -> Optional[str]:
        """This user's role in this org, or None when no membership row exists.

        None is a real and expected answer, not only an error case: API-key auth
        sets ``selected_organization_id`` on the user in memory without requiring
        a membership row, and the hosted path skips its INSERT whenever the
        selected org already matches. Callers must decide what a missing row
        means rather than assuming one is always present.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(organization_users_association.c.role).where(
                    organization_users_association.c.user_id == user_id,
                    organization_users_association.c.organization_id == organization_id,
                )
            )
            return result.scalar_one_or_none()

    async def get_organization_members(
        self, organization_id: int
    ) -> list[tuple[UserModel, str]]:
        """Every user in the org paired with their role.

        Separate from get_organization_users because that returns bare
        UserModels through a ``secondary=`` relationship, which cannot carry a
        column from the association table.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(UserModel, organization_users_association.c.role)
                .join(
                    organization_users_association,
                    organization_users_association.c.user_id == UserModel.id,
                )
                .where(
                    organization_users_association.c.organization_id == organization_id
                )
                .order_by(UserModel.id)
            )
            return [(row[0], row[1]) for row in result.all()]

    async def count_admins(self, organization_id: int) -> int:
        """How many admins the org has. Guards against removing the last one."""
        async with self.async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(organization_users_association)
                .where(
                    organization_users_association.c.organization_id == organization_id,
                    organization_users_association.c.role == OrgRole.ADMIN.value,
                )
            )
            return int(result.scalar() or 0)

    async def set_user_role(
        self, user_id: int, organization_id: int, role: str
    ) -> bool:
        """Change a member's role. False when there is no such membership row."""
        async with self.async_session() as session:
            result = await session.execute(
                update(organization_users_association)
                .where(
                    organization_users_association.c.user_id == user_id,
                    organization_users_association.c.organization_id == organization_id,
                )
                .values(role=role)
            )
            await session.commit()
            return result.rowcount > 0

    async def remove_user_from_organization(
        self, user_id: int, organization_id: int
    ) -> bool:
        """Take a user out of an organization. False when they were not in it.

        Deleting the association row is NOT on its own enough to remove access,
        and doing only that would hand the removed user MORE power than they had:

        * ``get_user_with_selected_organization`` only checks that
          ``users.selected_organization_id`` is set. It never consults this
          table, so every org-scoped handler would keep serving them.
        * ``get_org_role`` resolves a missing row to ADMIN by design, because
          API-key auth legitimately has no row. So a removed *member* would come
          back as an *admin*.

        Both are fixed by moving them off the org in the same transaction:
        another org they still belong to if there is one, otherwise NULL, which
        makes every org-scoped route 400 until they pick one.

        Not fixed here, and worth knowing: API keys belong to the organization
        rather than to the person who minted one, so a key this user has already
        copied keeps working. Removing someone who had a key means rotating it.
        """
        async with self.async_session() as session:
            deleted = await session.execute(
                delete(organization_users_association).where(
                    organization_users_association.c.user_id == user_id,
                    organization_users_association.c.organization_id == organization_id,
                )
            )
            if deleted.rowcount == 0:
                return False

            # Only touch the field when it points at the org they just left --
            # a user removed from an org they were not currently working in
            # must not be knocked out of the one they are.
            fallback = await session.execute(
                select(organization_users_association.c.organization_id)
                .where(organization_users_association.c.user_id == user_id)
                .order_by(organization_users_association.c.organization_id)
                .limit(1)
            )
            await session.execute(
                update(UserModel)
                .where(
                    UserModel.id == user_id,
                    UserModel.selected_organization_id == organization_id,
                )
                .values(selected_organization_id=fallback.scalar_one_or_none())
            )
            await session.commit()
            return True
