"""A saved contact list as a campaign's data source.

``campaigns.source_id`` carries the list's uuid. Unlike the CSV source, a person
here has a stable identity: ``source_uuid`` is ``contact_{contact_uuid}``, so the
same person is the same queued row however many times the list is re-synced,
where the CSV path's row-index uuid changes if a row moves.

The do-not-call list is applied at sync as well as at dial time. The dialler is
the authoritative gate (a number can be suppressed after it was queued), so this is
about not queueing, and counting, rows that would only be refused later.
"""

from typing import List, Optional

from loguru import logger

from api.db import db_client
from api.services.campaign.source_sync import (
    CampaignSourceSyncService,
    ValidationError,
    ValidationResult,
)

STANDARD_FIELDS = ["phone_number", "first_name", "last_name", "email"]
PAGE_SIZE = 500
# How many members the template-variable check reads. ponytail: a sample, not the
# whole list -- a list larger than this could hold an empty value past the sample
# that the campaign then renders blank. Page the check if that ever matters.
VALIDATION_SAMPLE = 5000


def _context_for(contact) -> dict:
    """The variables a call to this person starts with.

    Standard fields are written AFTER the custom attributes, so an attribute can
    never overwrite the number being dialled (the API also refuses those names).
    """
    return {
        **(contact.attributes or {}),
        "phone_number": contact.phone_e164,
        "first_name": contact.first_name or "",
        "last_name": contact.last_name or "",
        "email": contact.email or "",
        "contact_uuid": contact.contact_uuid,
    }


class ContactListSyncService(CampaignSourceSyncService):
    async def validate_source(
        self, source_id: str, organization_id: Optional[int] = None
    ) -> ValidationResult:
        if organization_id is None:
            return ValidationResult(
                is_valid=False, error=ValidationError(message="No organization selected")
            )
        contact_list = await db_client.get_contact_list_by_uuid(source_id, organization_id)
        if contact_list is None:
            return ValidationResult(
                is_valid=False, error=ValidationError(message="Contact list not found")
            )
        if not contact_list.contact_count:
            return ValidationResult(
                is_valid=False,
                error=ValidationError(message="That contact list has no contacts in it"),
            )

        keys = await db_client.get_list_attribute_keys(contact_list.id, organization_id)
        headers = [*STANDARD_FIELDS, *keys]
        members = await db_client.page_list_contacts(
            contact_list.id, organization_id, limit=VALIDATION_SAMPLE
        )
        rows: List[List[str]] = []
        for member in members:
            ctx = _context_for(member)
            rows.append([str(ctx[h]) if ctx.get(h) is not None else "" for h in headers])
        # Same shape the CSV source hands back, so the existing template-variable
        # pre-flight in campaign creation fails fast on a missing field.
        return ValidationResult(is_valid=True, headers=headers, rows=rows)

    async def sync_source_data(self, campaign_id: int) -> int:
        campaign = await db_client.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        org = campaign.organization_id
        contact_list = await db_client.get_contact_list_by_uuid(campaign.source_id, org)
        if contact_list is None:
            raise ValueError(f"Contact list {campaign.source_id} not found")

        queued = 0
        suppressed_count = 0
        after_id = 0
        while True:
            page = await db_client.page_list_contacts(
                contact_list.id, org, after_id=after_id, limit=PAGE_SIZE
            )
            if not page:
                break
            after_id = page[-1].id

            suppressed = await db_client.filter_suppressed_e164(
                org, [c.phone_e164 for c in page]
            )
            runs = []
            for contact in page:
                if contact.phone_e164 in suppressed:
                    suppressed_count += 1
                    continue
                runs.append(
                    {
                        "campaign_id": campaign_id,
                        "source_uuid": f"contact_{contact.contact_uuid}",
                        "context_variables": _context_for(contact),
                        "state": "queued",
                    }
                )
            if runs:
                await db_client.bulk_create_queued_runs(runs)
                queued += len(runs)

        if suppressed_count:
            await db_client.append_campaign_log(
                campaign_id,
                "info",
                "numbers_suppressed_at_sync",
                f"{suppressed_count} contact(s) on the do-not-call list were not queued",
                {"count": suppressed_count},
            )
        logger.info(
            f"Campaign {campaign_id}: queued {queued} from list {contact_list.list_uuid}, "
            f"{suppressed_count} suppressed"
        )

        await db_client.update_campaign(
            campaign_id=campaign_id, total_rows=queued, source_sync_status="completed"
        )
        return queued
