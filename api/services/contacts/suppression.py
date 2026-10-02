"""The do-not-call check.

One definition of "suppressed", used by every path that can start an outbound
call: the campaign dispatcher, the public trigger API, test calls, and the
list-sourced campaign. They all end in ``filter_suppressed_e164``.

A number that is not a dialable phone number (a SIP address) cannot be on a
phone do-not-call list, so it is never reported suppressed.
"""

from typing import Iterable

from api.db import db_client
from api.services.contacts.phone import to_e164


async def suppressed_among(organization_id: int, numbers: Iterable[str]) -> set[str]:
    """Which of these numbers, AS GIVEN, are suppressed. One query for the lot."""
    given = [n for n in numbers if n]
    by_e164: dict[str, list[str]] = {}
    for original in given:
        parsed = to_e164(original)
        if parsed:
            by_e164.setdefault(parsed[0], []).append(original)
    if not by_e164:
        return set()
    hits = await db_client.filter_suppressed_e164(organization_id, by_e164)
    return {original for e164 in hits for original in by_e164[e164]}


async def is_suppressed(organization_id: int, phone_number: str | None) -> bool:
    if not phone_number:
        return False
    return bool(await suppressed_among(organization_id, [phone_number]))


async def record_suppression(
    organization_id: int,
    phone_number: str,
    *,
    source: str,
    reason: str | None = None,
    created_by: int | None = None,
) -> bool:
    """Suppress one number. False if it was not a dialable number, or was already
    suppressed (so a repeat opt-out is not an error)."""
    parsed = to_e164(phone_number)
    if not parsed:
        return False
    added = await db_client.add_suppressions_batch(
        organization_id, [parsed[0]], source=source, reason=reason, created_by=created_by
    )
    return added > 0
