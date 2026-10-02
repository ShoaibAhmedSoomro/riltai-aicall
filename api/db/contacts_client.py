"""Database access for contacts, lists, imports and the do-not-call list.

All SQLAlchemy for the contacts domain lives here (api/AGENTS.md): routes, services
and tasks call these methods and never open a session.

The one place a person is deduplicated is ``upsert_contacts_batch``. Everything
else that needs "is this the same person" matches on
``(organization_id, phone_e164)`` through the unique constraint.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy import JSON, cast, delete, exists, func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from api.db.base_client import BaseDBClient
from api.db.models import (
    ContactImportModel,
    ContactListMemberModel,
    ContactListModel,
    ContactModel,
    ContactSuppressionModel,
)

# Sort keys the list endpoint accepts. An allowlist, not a column name from the
# request: the value goes into an ORDER BY.
CONTACT_SORTS = {
    "created_at": ContactModel.created_at.desc(),
    "name": func.lower(func.coalesce(ContactModel.first_name, "")).asc(),
    "last_called_at": ContactModel.last_called_at.desc().nulls_last(),
    "call_count": ContactModel.call_count.desc(),
}


class ContactAlreadyExistsError(Exception):
    """A contact with this phone number already exists in the organization."""


class ContactListNameTakenError(Exception):
    """A list with this name already exists in the organization."""


def _merge_row(into: dict, row: dict) -> dict:
    """Fold a later duplicate of the same number into the earlier one.

    Non-empty fields from the later row win; attributes are unioned.
    """
    merged = dict(into)
    for key in ("first_name", "last_name", "email", "country_code"):
        if row.get(key):
            merged[key] = row[key]
    merged["attributes"] = {**(into.get("attributes") or {}), **(row.get("attributes") or {})}
    return merged


class ContactsClient(BaseDBClient):
    # ------------------------------------------------------------------ contacts

    async def create_contact(
        self,
        organization_id: int,
        *,
        phone_number: str,
        phone_e164: str,
        country_code: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        attributes: dict | None = None,
        created_by: int | None = None,
    ) -> ContactModel:
        async with self.async_session() as session:
            contact = ContactModel(
                organization_id=organization_id,
                phone_number=phone_number,
                phone_e164=phone_e164,
                country_code=country_code,
                first_name=first_name,
                last_name=last_name,
                email=email,
                attributes=attributes or {},
                created_by=created_by,
            )
            session.add(contact)
            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                raise ContactAlreadyExistsError(phone_e164) from e
            await session.refresh(contact)
            return contact

    async def get_contact_by_uuid(
        self, contact_uuid: str, organization_id: int
    ) -> ContactModel | None:
        async with self.async_session() as session:
            result = await session.execute(
                select(ContactModel).where(
                    ContactModel.contact_uuid == contact_uuid,
                    ContactModel.organization_id == organization_id,
                )
            )
            return result.scalars().first()

    def _suppressed_exists(self):
        return exists().where(
            ContactSuppressionModel.organization_id == ContactModel.organization_id,
            ContactSuppressionModel.phone_e164 == ContactModel.phone_e164,
        )

    async def list_contacts(
        self,
        organization_id: int,
        *,
        q: str | None = None,
        list_id: int | None = None,
        suppressed: bool | None = None,
        sort: str = "created_at",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[tuple[ContactModel, bool]], int]:
        """A page of contacts with whether each is suppressed, and the total.

        ``suppressed`` is computed from the suppression table, never stored on
        the contact, so it cannot disagree with what the dialler enforces.
        """
        is_suppressed = self._suppressed_exists()
        conditions = [ContactModel.organization_id == organization_id]
        if q and q.strip():
            like = f"%{q.strip()}%"
            conditions.append(
                or_(
                    ContactModel.phone_e164.ilike(like),
                    ContactModel.phone_number.ilike(like),
                    ContactModel.first_name.ilike(like),
                    ContactModel.last_name.ilike(like),
                    ContactModel.email.ilike(like),
                )
            )
        if list_id is not None:
            conditions.append(
                exists().where(
                    ContactListMemberModel.contact_id == ContactModel.id,
                    ContactListMemberModel.contact_list_id == list_id,
                )
            )
        if suppressed is True:
            conditions.append(is_suppressed)
        elif suppressed is False:
            conditions.append(~is_suppressed)

        order = CONTACT_SORTS.get(sort, CONTACT_SORTS["created_at"])
        async with self.async_session() as session:
            total = (
                await session.execute(select(func.count(ContactModel.id)).where(*conditions))
            ).scalar_one()
            rows = (
                await session.execute(
                    select(ContactModel, is_suppressed.label("suppressed"))
                    .where(*conditions)
                    .order_by(order, ContactModel.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [(r[0], bool(r[1])) for r in rows], total

    async def update_contact(
        self, contact_uuid: str, organization_id: int, fields: dict[str, Any]
    ) -> ContactModel | None:
        """Change a contact's details. The phone number is not editable: it is the
        identity, so a different number is a different contact."""
        allowed = {"first_name", "last_name", "email", "attributes"}
        async with self.async_session() as session:
            contact = (
                await session.execute(
                    select(ContactModel).where(
                        ContactModel.contact_uuid == contact_uuid,
                        ContactModel.organization_id == organization_id,
                    )
                )
            ).scalars().first()
            if contact is None:
                return None
            for key, value in fields.items():
                if key in allowed:
                    setattr(contact, key, value)
            await session.commit()
            await session.refresh(contact)
            return contact

    async def delete_contacts(self, organization_id: int, contact_uuids: list[str]) -> int:
        """Delete contacts. Their suppressions are NOT touched: a number someone
        asked not to be called stays that way even if the row is gone."""
        async with self.async_session() as session:
            ids = (
                await session.execute(
                    select(ContactModel.id).where(
                        ContactModel.organization_id == organization_id,
                        ContactModel.contact_uuid.in_(contact_uuids),
                    )
                )
            ).scalars().all()
            if not ids:
                return 0
            list_ids = (
                await session.execute(
                    select(ContactListMemberModel.contact_list_id)
                    .where(ContactListMemberModel.contact_id.in_(ids))
                    .distinct()
                )
            ).scalars().all()
            await session.execute(delete(ContactModel).where(ContactModel.id.in_(ids)))
            for list_id in list_ids:
                await self._recount(session, list_id)
            await session.commit()
            return len(ids)

    async def upsert_contacts_batch(
        self,
        organization_id: int,
        rows: list[dict],
        dedupe_strategy: str,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """Insert or merge a batch, deduplicating on (organization, E.164).

        THE place dedupe happens. Each row needs ``phone_number`` and
        ``phone_e164``; ``first_name``, ``last_name``, ``email``, ``country_code``
        and ``attributes`` are optional.

        ``skip``   an existing contact is left exactly as it is.
        ``update`` an existing contact takes the new non-empty names/email and has
                   the new attributes merged over its own.

        Two rows for the same number inside one batch would make PostgreSQL refuse
        the statement ("cannot affect row a second time"), so they are folded here
        first: under ``update`` the later row's values win; under ``skip`` the first
        row wins and the repeat is counted as skipped.

        Returns ``{created, updated, skipped, id_by_e164}``.
        """
        if dedupe_strategy not in ("skip", "update"):
            raise ValueError(f"Unknown dedupe strategy: {dedupe_strategy}")

        folded: dict[str, dict] = {}
        in_batch_duplicates = 0
        for row in rows:
            e164 = row["phone_e164"]
            if e164 in folded:
                in_batch_duplicates += 1
                if dedupe_strategy == "update":
                    folded[e164] = _merge_row(folded[e164], row)
            else:
                folded[e164] = dict(row)
        if not folded:
            return {"created": 0, "updated": 0, "skipped": 0, "id_by_e164": {}}

        values = [
            {
                "organization_id": organization_id,
                "contact_uuid": str(uuid.uuid4()),
                "phone_number": r["phone_number"],
                "phone_e164": e164,
                "country_code": r.get("country_code"),
                "first_name": r.get("first_name"),
                "last_name": r.get("last_name"),
                "email": r.get("email"),
                "attributes": r.get("attributes") or {},
                "created_by": created_by,
            }
            for e164, r in folded.items()
        ]

        async with self.async_session() as session:
            stmt = pg_insert(ContactModel).values(values)
            index = ["organization_id", "phone_e164"]
            if dedupe_strategy == "skip":
                result = await session.execute(
                    stmt.on_conflict_do_nothing(index_elements=index).returning(
                        ContactModel.phone_e164
                    )
                )
                created = len(result.all())
                updated = 0
                skipped = (len(values) - created) + in_batch_duplicates
            else:
                ex = stmt.excluded
                result = await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=index,
                        set_={
                            "first_name": func.coalesce(
                                func.nullif(ex.first_name, ""), ContactModel.first_name
                            ),
                            "last_name": func.coalesce(
                                func.nullif(ex.last_name, ""), ContactModel.last_name
                            ),
                            "email": func.coalesce(
                                func.nullif(ex.email, ""), ContactModel.email
                            ),
                            "attributes": cast(
                                cast(ContactModel.attributes, JSONB).op("||")(
                                    cast(ex.attributes, JSONB)
                                ),
                                JSON,
                            ),
                            "updated_at": func.now(),
                        },
                    ).returning(literal_column("(xmax = 0)").label("inserted"))
                )
                flags = [bool(r[0]) for r in result.all()]
                created = sum(flags)
                updated = len(flags) - created
                skipped = 0

            # Every number in the batch, new or existing, so the caller can put
            # them in a list without a second pass.
            id_rows = (
                await session.execute(
                    select(ContactModel.phone_e164, ContactModel.id).where(
                        ContactModel.organization_id == organization_id,
                        ContactModel.phone_e164.in_(list(folded)),
                    )
                )
            ).all()
            await session.commit()
            return {
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "id_by_e164": {e164: cid for e164, cid in id_rows},
            }

    async def record_contact_call(
        self,
        organization_id: int,
        phone_e164: str,
        *,
        disposition: str | None,
        called_at: datetime | None = None,
    ) -> bool:
        """Note that a call to this number happened. A number that is not a
        contact is simply not a contact: there is nothing to update."""
        async with self.async_session() as session:
            result = await session.execute(
                update(ContactModel)
                .where(
                    ContactModel.organization_id == organization_id,
                    ContactModel.phone_e164 == phone_e164,
                )
                .values(
                    call_count=ContactModel.call_count + 1,
                    last_called_at=called_at or datetime.now(UTC),
                    last_disposition=disposition,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def get_contacts_summary(self, organization_id: int) -> dict[str, Any]:
        month_start = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        org = ContactModel.organization_id == organization_id
        async with self.async_session() as session:
            total = (
                await session.execute(select(func.count(ContactModel.id)).where(org))
            ).scalar_one()
            suppressed = (
                await session.execute(
                    select(func.count(ContactModel.id)).where(org, self._suppressed_exists())
                )
            ).scalar_one()
            never_called = (
                await session.execute(
                    select(func.count(ContactModel.id)).where(org, ContactModel.call_count == 0)
                )
            ).scalar_one()
            added_this_month = (
                await session.execute(
                    select(func.count(ContactModel.id)).where(
                        org, ContactModel.created_at >= month_start
                    )
                )
            ).scalar_one()
            list_count = (
                await session.execute(
                    select(func.count(ContactListModel.id)).where(
                        ContactListModel.organization_id == organization_id
                    )
                )
            ).scalar_one()
            last_import_at = (
                await session.execute(
                    select(func.max(ContactImportModel.created_at)).where(
                        ContactImportModel.organization_id == organization_id
                    )
                )
            ).scalar_one()
            return {
                "total": total,
                "suppressed": suppressed,
                "never_called": never_called,
                "added_this_month": added_this_month,
                "list_count": list_count,
                "last_import_at": last_import_at,
            }

    # -------------------------------------------------------------------- lists

    async def create_contact_list(
        self,
        organization_id: int,
        *,
        name: str,
        description: str | None = None,
        created_by: int | None = None,
    ) -> ContactListModel:
        async with self.async_session() as session:
            contact_list = ContactListModel(
                organization_id=organization_id,
                name=name.strip(),
                description=description,
                created_by=created_by,
            )
            session.add(contact_list)
            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                raise ContactListNameTakenError(name) from e
            await session.refresh(contact_list)
            return contact_list

    async def get_contact_list_by_uuid(
        self, list_uuid: str, organization_id: int
    ) -> ContactListModel | None:
        async with self.async_session() as session:
            result = await session.execute(
                select(ContactListModel).where(
                    ContactListModel.list_uuid == list_uuid,
                    ContactListModel.organization_id == organization_id,
                )
            )
            return result.scalars().first()

    async def list_contact_lists(self, organization_id: int) -> list[ContactListModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(ContactListModel)
                .where(ContactListModel.organization_id == organization_id)
                .order_by(func.lower(ContactListModel.name))
            )
            return list(result.scalars().all())

    async def update_contact_list(
        self,
        list_uuid: str,
        organization_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ContactListModel | None:
        async with self.async_session() as session:
            contact_list = (
                await session.execute(
                    select(ContactListModel).where(
                        ContactListModel.list_uuid == list_uuid,
                        ContactListModel.organization_id == organization_id,
                    )
                )
            ).scalars().first()
            if contact_list is None:
                return None
            if name is not None:
                contact_list.name = name.strip()
            if description is not None:
                contact_list.description = description
            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                raise ContactListNameTakenError(name) from e
            await session.refresh(contact_list)
            return contact_list

    async def delete_contact_list(self, list_uuid: str, organization_id: int) -> bool:
        """Delete the list and its memberships. The contacts themselves stay."""
        async with self.async_session() as session:
            result = await session.execute(
                delete(ContactListModel).where(
                    ContactListModel.list_uuid == list_uuid,
                    ContactListModel.organization_id == organization_id,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def _recount(self, session, list_id: int) -> None:
        count = (
            await session.execute(
                select(func.count()).where(ContactListMemberModel.contact_list_id == list_id)
            )
        ).scalar_one()
        await session.execute(
            update(ContactListModel)
            .where(ContactListModel.id == list_id)
            .values(contact_count=count)
        )

    async def add_contacts_to_list(
        self, list_id: int, organization_id: int, contact_ids: Iterable[int]
    ) -> int:
        """Add members, ignoring any already in the list. Only contacts that belong
        to this organization are added, so an id from another tenant is dropped
        rather than trusted."""
        ids = list(dict.fromkeys(contact_ids))
        if not ids:
            return 0
        async with self.async_session() as session:
            owned = (
                await session.execute(
                    select(ContactModel.id).where(
                        ContactModel.organization_id == organization_id,
                        ContactModel.id.in_(ids),
                    )
                )
            ).scalars().all()
            if not owned:
                return 0
            result = await session.execute(
                pg_insert(ContactListMemberModel)
                .values([{"contact_list_id": list_id, "contact_id": cid} for cid in owned])
                .on_conflict_do_nothing()
                .returning(ContactListMemberModel.contact_id)
            )
            added = len(result.all())
            await self._recount(session, list_id)
            await session.commit()
            return added

    async def add_contact_uuids_to_list(
        self, list_id: int, organization_id: int, contact_uuids: list[str]
    ) -> int:
        async with self.async_session() as session:
            ids = (
                await session.execute(
                    select(ContactModel.id).where(
                        ContactModel.organization_id == organization_id,
                        ContactModel.contact_uuid.in_(contact_uuids),
                    )
                )
            ).scalars().all()
        return await self.add_contacts_to_list(list_id, organization_id, ids)

    async def remove_contact_uuids_from_list(
        self, list_id: int, organization_id: int, contact_uuids: list[str]
    ) -> int:
        async with self.async_session() as session:
            ids = (
                await session.execute(
                    select(ContactModel.id).where(
                        ContactModel.organization_id == organization_id,
                        ContactModel.contact_uuid.in_(contact_uuids),
                    )
                )
            ).scalars().all()
            if not ids:
                return 0
            result = await session.execute(
                delete(ContactListMemberModel).where(
                    ContactListMemberModel.contact_list_id == list_id,
                    ContactListMemberModel.contact_id.in_(ids),
                )
            )
            await self._recount(session, list_id)
            await session.commit()
            return result.rowcount

    async def list_lists_for_contact(
        self, contact_id: int, organization_id: int
    ) -> list[ContactListModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(ContactListModel)
                .join(
                    ContactListMemberModel,
                    ContactListMemberModel.contact_list_id == ContactListModel.id,
                )
                .where(
                    ContactListMemberModel.contact_id == contact_id,
                    ContactListModel.organization_id == organization_id,
                )
                .order_by(func.lower(ContactListModel.name))
            )
            return list(result.scalars().all())

    async def page_list_contacts(
        self, list_id: int, organization_id: int, *, after_id: int = 0, limit: int = 500
    ) -> list[ContactModel]:
        """Members in id order, for streaming a whole list without OFFSET."""
        async with self.async_session() as session:
            result = await session.execute(
                select(ContactModel)
                .join(
                    ContactListMemberModel,
                    ContactListMemberModel.contact_id == ContactModel.id,
                )
                .where(
                    ContactListMemberModel.contact_list_id == list_id,
                    ContactModel.organization_id == organization_id,
                    ContactModel.id > after_id,
                )
                .order_by(ContactModel.id)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_list_attribute_keys(self, list_id: int, organization_id: int) -> list[str]:
        """The custom attribute names present on any member, for the campaign
        template-variable check."""
        async with self.async_session() as session:
            keys = (
                await session.execute(
                    select(func.json_object_keys(ContactModel.attributes))
                    .select_from(ContactModel)
                    .join(
                        ContactListMemberModel,
                        ContactListMemberModel.contact_id == ContactModel.id,
                    )
                    .where(
                        ContactListMemberModel.contact_list_id == list_id,
                        ContactModel.organization_id == organization_id,
                    )
                    .distinct()
                )
            ).scalars().all()
            return sorted(keys)

    # ------------------------------------------------------------------ imports

    async def create_contact_import(
        self,
        organization_id: int,
        *,
        source_key: str,
        column_mapping: dict,
        dedupe_strategy: str,
        contact_list_id: int | None = None,
        created_by: int | None = None,
    ) -> ContactImportModel:
        async with self.async_session() as session:
            row = ContactImportModel(
                organization_id=organization_id,
                source_key=source_key,
                column_mapping=column_mapping,
                dedupe_strategy=dedupe_strategy,
                contact_list_id=contact_list_id,
                created_by=created_by,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def get_contact_import(
        self, import_uuid: str, organization_id: int | None = None
    ) -> ContactImportModel | None:
        async with self.async_session() as session:
            query = select(ContactImportModel).where(
                ContactImportModel.import_uuid == import_uuid
            )
            if organization_id is not None:
                query = query.where(ContactImportModel.organization_id == organization_id)
            return (await session.execute(query)).scalars().first()

    async def update_contact_import(self, import_id: int, **fields: Any) -> None:
        async with self.async_session() as session:
            await session.execute(
                update(ContactImportModel)
                .where(ContactImportModel.id == import_id)
                .values(**fields)
            )
            await session.commit()

    async def bump_contact_import_counts(self, import_id: int, **deltas: int) -> None:
        """Add to the progress counters in SQL, so a polling UI sees movement and
        two writers cannot overwrite each other's total."""
        async with self.async_session() as session:
            await session.execute(
                update(ContactImportModel)
                .where(ContactImportModel.id == import_id)
                .values(
                    **{k: getattr(ContactImportModel, k) + v for k, v in deltas.items()}
                )
            )
            await session.commit()

    # ------------------------------------------------------------- suppressions

    async def list_suppressions(
        self,
        organization_id: int,
        *,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContactSuppressionModel], int]:
        conditions = [ContactSuppressionModel.organization_id == organization_id]
        if q and q.strip():
            conditions.append(ContactSuppressionModel.phone_e164.ilike(f"%{q.strip()}%"))
        async with self.async_session() as session:
            total = (
                await session.execute(
                    select(func.count(ContactSuppressionModel.id)).where(*conditions)
                )
            ).scalar_one()
            rows = (
                await session.execute(
                    select(ContactSuppressionModel)
                    .where(*conditions)
                    .order_by(ContactSuppressionModel.created_at.desc(), ContactSuppressionModel.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars().all()
            return list(rows), total

    async def add_suppressions_batch(
        self,
        organization_id: int,
        e164_numbers: Iterable[str],
        *,
        source: str = "manual",
        reason: str | None = None,
        notes: str | None = None,
        created_by: int | None = None,
    ) -> int:
        """Suppress numbers. Re-adding one that is already suppressed is a no-op,
        not an error. Returns how many were newly added."""
        unique = list(dict.fromkeys(e164_numbers))
        if not unique:
            return 0
        async with self.async_session() as session:
            result = await session.execute(
                pg_insert(ContactSuppressionModel)
                .values(
                    [
                        {
                            "organization_id": organization_id,
                            "phone_e164": e164,
                            "source": source,
                            "reason": reason,
                            "notes": notes,
                            "created_by": created_by,
                        }
                        for e164 in unique
                    ]
                )
                .on_conflict_do_nothing(index_elements=["organization_id", "phone_e164"])
                .returning(ContactSuppressionModel.id)
            )
            added = len(result.all())
            await session.commit()
            return added

    async def remove_suppression(self, organization_id: int, phone_e164: str) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                delete(ContactSuppressionModel).where(
                    ContactSuppressionModel.organization_id == organization_id,
                    ContactSuppressionModel.phone_e164 == phone_e164,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def filter_suppressed_e164(
        self, organization_id: int, e164_numbers: Iterable[str]
    ) -> set[str]:
        """Which of these numbers are suppressed. THE single batch query the
        dispatcher, the public trigger and the list-sourced campaign all call, so
        there is one definition of "suppressed"."""
        numbers = list({n for n in e164_numbers if n})
        if not numbers:
            return set()
        async with self.async_session() as session:
            rows = (
                await session.execute(
                    select(ContactSuppressionModel.phone_e164).where(
                        ContactSuppressionModel.organization_id == organization_id,
                        ContactSuppressionModel.phone_e164.in_(numbers),
                    )
                )
            ).scalars().all()
            return set(rows)
