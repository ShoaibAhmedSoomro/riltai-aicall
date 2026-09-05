import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from api.constants import ORG_INVITE_TTL_DAYS
from api.db.base_client import BaseDBClient
from api.db.models import OrganizationInviteModel
from api.enums import OrgRole


class InviteConflictError(Exception):
    """A live invite for this address already exists in this organization."""


def normalize_invite_email(email: str) -> str:
    """Lowercase and strip.

    Every email lookup in this codebase is an exact match, so an invite stored
    as "A@x.com" would never be found by someone signing up as "a@x.com". The
    normalisation has to happen on the way in, once, or the two sides drift.
    """
    return email.strip().lower()


class OrganizationInviteClient(BaseDBClient):
    async def create_invite(
        self,
        organization_id: int,
        email: str,
        role: str = OrgRole.MEMBER.value,
        invited_by: Optional[int] = None,
    ) -> OrganizationInviteModel:
        """Record an invitation. Does NOT send anything -- nothing can, yet.

        Raises InviteConflictError when a live invite already exists for this
        address, which the partial unique index enforces at the database level
        rather than trusting a read-then-write.
        """
        invite = OrganizationInviteModel(
            organization_id=organization_id,
            email=normalize_invite_email(email),
            role=role,
            # Prefixed like the embed tokens so a leaked string is identifiable
            # at a glance. Generated even though nothing transmits it: an invite
            # without a token cannot be accepted later without a migration.
            token=f"inv_{secrets.token_urlsafe(32)}",
            invited_by=invited_by,
            expires_at=datetime.now(UTC) + timedelta(days=ORG_INVITE_TTL_DAYS),
        )
        async with self.async_session() as session:
            session.add(invite)
            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                raise InviteConflictError(
                    "There is already a pending invite for this email address."
                ) from e
            await session.refresh(invite)
            return invite

    async def list_invites(
        self, organization_id: int, pending_only: bool = True
    ) -> list[OrganizationInviteModel]:
        async with self.async_session() as session:
            query = select(OrganizationInviteModel).where(
                OrganizationInviteModel.organization_id == organization_id
            )
            if pending_only:
                query = query.where(
                    OrganizationInviteModel.accepted_at.is_(None),
                    OrganizationInviteModel.revoked_at.is_(None),
                )
            result = await session.execute(
                query.order_by(OrganizationInviteModel.created_at.desc())
            )
            return list(result.scalars().all())

    async def revoke_invite(self, invite_id: int, organization_id: int) -> bool:
        """Mark an invite revoked. Scoped by org: the id comes from a URL.

        Only affects a still-pending invite, so revoking twice, or revoking one
        that was already accepted, changes nothing and reports False.
        """
        async with self.async_session() as session:
            result = await session.execute(
                update(OrganizationInviteModel)
                .where(
                    OrganizationInviteModel.id == invite_id,
                    OrganizationInviteModel.organization_id == organization_id,
                    OrganizationInviteModel.accepted_at.is_(None),
                    OrganizationInviteModel.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
            await session.commit()
            return result.rowcount > 0

    async def get_acceptable_invite(
        self, token: str
    ) -> Optional[OrganizationInviteModel]:
        """The invite this token can still be used to accept, if any.

        Every reason an invite is unusable -- unknown, revoked, already used,
        expired -- resolves to None here, so callers cannot accidentally honour
        one of them by checking only some of the conditions.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationInviteModel).where(
                    OrganizationInviteModel.token == token,
                    OrganizationInviteModel.accepted_at.is_(None),
                    OrganizationInviteModel.revoked_at.is_(None),
                    OrganizationInviteModel.expires_at > datetime.now(UTC),
                )
            )
            return result.scalars().first()

    async def mark_invite_accepted(self, invite_id: int) -> bool:
        """Consume an invite. False if something already consumed it.

        Conditional on it still being pending so two concurrent accepts cannot
        both succeed -- the loser gets False rather than a second membership.
        """
        async with self.async_session() as session:
            result = await session.execute(
                update(OrganizationInviteModel)
                .where(
                    OrganizationInviteModel.id == invite_id,
                    OrganizationInviteModel.accepted_at.is_(None),
                    OrganizationInviteModel.revoked_at.is_(None),
                )
                .values(accepted_at=datetime.now(UTC))
            )
            await session.commit()
            return result.rowcount > 0
