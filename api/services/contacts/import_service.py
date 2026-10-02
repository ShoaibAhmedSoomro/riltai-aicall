"""CSV contact import.

The file is streamed to disk and read back row by row, then upserted in batches, so
a 100,000-row file is never held in memory. An unparseable phone number rejects
THAT ROW into a downloadable report; it never fails the import. A duplicate is
merged (or skipped), never fatal -- unlike the campaign CSV path, which rejects
duplicates and is left untouched.

``column_mapping`` shape::

    {"phone_number": "Mobile",            # required: the CSV header holding the number
     "first_name": "First", "last_name": "Last", "email": "Email",   # optional
     "attributes": {"company": "Employer"},   # custom field name -> CSV header
     "country_hint": "AE",                # optional: for numbers written locally
     "mode": "contacts" | "suppression"}  # "suppression" turns it into a DNC import
"""

import asyncio
import csv
import io
import tempfile
from typing import Any

import httpx
from loguru import logger

from api.db import db_client
from api.services.contacts.phone import to_e164
from api.services.storage import storage_fs

BATCH_SIZE = 500
# A 10MB upload is ~100k rows; this is the ceiling, not a target.
MAX_ROWS = 200_000
PREVIEW_BYTES = 64 * 1024
PREVIEW_ROWS = 5
ERROR_REPORT_KEY = "campaigns/{org}/contact-import-errors/{uuid}.csv"


class ContactImportError(Exception):
    """The import cannot run at all (as opposed to a row being rejected)."""


def _norm(header: str) -> str:
    return (header or "").strip().lower()


def resolve_columns(headers: list[str], mapping: dict) -> dict[str, Any]:
    """Turn header NAMES in the mapping into column positions.

    Raises ContactImportError if the phone column, or any mapped column, is not in the
    file: a mapping that points at nothing would import every row blank.
    """
    index = {_norm(h): i for i, h in enumerate(headers)}

    def pos(header: str | None, what: str) -> int | None:
        if not header:
            return None
        if _norm(header) not in index:
            raise ContactImportError(f"Column \"{header}\" ({what}) is not in the file")
        return index[_norm(header)]

    phone = pos(mapping.get("phone_number"), "phone number")
    if phone is None:
        raise ContactImportError("Choose which column holds the phone number")
    return {
        "phone": phone,
        "first_name": pos(mapping.get("first_name"), "first name"),
        "last_name": pos(mapping.get("last_name"), "last name"),
        "email": pos(mapping.get("email"), "email"),
        "attributes": {
            name: pos(header, name)
            for name, header in (mapping.get("attributes") or {}).items()
            if name and header
        },
    }


def _cell(row: list[str], i: int | None) -> str | None:
    if i is None or i >= len(row):
        return None
    value = row[i].strip()
    return value or None


def build_contact(row: list[str], cols: dict, country_hint: str | None) -> tuple[dict | None, str | None]:
    """``(contact, None)`` or ``(None, reason)``."""
    raw_phone = _cell(row, cols["phone"])
    if not raw_phone:
        return None, "Missing phone number"
    parsed = to_e164(raw_phone, country_hint)
    if not parsed:
        return None, "Not a valid phone number"
    e164, country = parsed
    attributes = {
        name: value
        for name, i in cols["attributes"].items()
        if (value := _cell(row, i)) is not None
    }
    return {
        "phone_number": raw_phone,
        "phone_e164": e164,
        "country_code": country,
        "first_name": _cell(row, cols["first_name"]),
        "last_name": _cell(row, cols["last_name"]),
        "email": _cell(row, cols["email"]),
        "attributes": attributes,
    }, None


async def _signed_url(source_key: str) -> str:
    url = await storage_fs.aget_signed_url(source_key, expiration=3600, use_internal_endpoint=True)
    if not url:
        raise ContactImportError("Could not read the uploaded file")
    return url


async def preview_csv(source_key: str) -> dict[str, Any]:
    """Headers and the first few rows, from the first 64KB only."""
    url = await _signed_url(source_key)
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                head = b""
                async for chunk in response.aiter_bytes():
                    head += chunk
                    if len(head) >= PREVIEW_BYTES:
                        break
    except httpx.HTTPError as e:
        raise ContactImportError(f"Could not download the file: {e}") from e

    text = head.decode("utf-8-sig", errors="replace")
    # The last line may be cut off mid-row; drop it unless it is all there is.
    lines = text.splitlines()
    if len(head) >= PREVIEW_BYTES and len(lines) > 1:
        lines = lines[:-1]
    rows = list(csv.reader(lines))
    if not rows:
        raise ContactImportError("The file is empty")
    return {"headers": rows[0], "rows": rows[1 : 1 + PREVIEW_ROWS]}


async def _download_to_tempfile(source_key: str):
    """Stream the object to a spooled temp file so memory stays bounded."""
    url = await _signed_url(source_key)
    tmp = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode="w+b")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    tmp.write(chunk)
        tmp.seek(0)
        return tmp
    except Exception:
        tmp.close()
        raise


async def run_contact_import(import_uuid: str) -> None:
    """Process one import to completion. Never raises: failure is recorded on the
    import row, where the UI is polling for it."""
    imp = await db_client.get_contact_import(import_uuid)
    if imp is None:
        logger.warning(f"Contact import {import_uuid} not found")
        return
    if imp.status != "pending":
        # A retried job must not run an import twice: counters would double.
        logger.info(f"Contact import {import_uuid} is {imp.status}; not re-running")
        return

    await db_client.update_contact_import(imp.id, status="processing")
    try:
        await _process(imp)
    except ContactImportError as e:
        await db_client.update_contact_import(imp.id, status="failed", processing_error=str(e)[:500])
    except Exception as e:
        logger.exception(f"Contact import {import_uuid} failed")
        await db_client.update_contact_import(
            imp.id, status="failed", processing_error=f"Unexpected error: {e}"[:500]
        )


async def _process(imp) -> None:
    mapping = imp.column_mapping or {}
    suppression_mode = mapping.get("mode") == "suppression"
    country_hint = mapping.get("country_hint")
    org = imp.organization_id

    tmp = await _download_to_tempfile(imp.source_key)
    rejected: list[list[str]] = []
    batch: list[dict] = []
    seen = 0

    async def flush() -> None:
        nonlocal batch
        if not batch:
            return
        if suppression_mode:
            added = await db_client.add_suppressions_batch(
                org,
                [c["phone_e164"] for c in batch],
                source="csv",
                reason=mapping.get("reason"),
                created_by=imp.created_by,
            )
            await db_client.bump_contact_import_counts(
                imp.id, created_count=added, skipped_count=len(batch) - added
            )
        else:
            result = await db_client.upsert_contacts_batch(
                org, batch, imp.dedupe_strategy, created_by=imp.created_by
            )
            if imp.contact_list_id:
                await db_client.add_contacts_to_list(
                    imp.contact_list_id, org, result["id_by_e164"].values()
                )
            await db_client.bump_contact_import_counts(
                imp.id,
                created_count=result["created"],
                updated_count=result["updated"],
                skipped_count=result["skipped"],
            )
        batch = []
        # Let other work on this worker run between batches.
        await asyncio.sleep(0)

    try:
        text = io.TextIOWrapper(tmp, encoding="utf-8-sig", errors="replace", newline="")
        reader = csv.reader(text)
        headers = next(reader, None)
        if not headers:
            raise ContactImportError("The file is empty")
        cols = resolve_columns(headers, mapping)

        for line_no, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                continue  # a blank line is not a row
            seen += 1
            if seen > MAX_ROWS:
                raise ContactImportError(f"The file has more than {MAX_ROWS:,} rows. Split it and import the parts.")
            contact, reason = build_contact(row, cols, country_hint)
            if contact is None:
                rejected.append([str(line_no), reason or "", *row])
                continue
            batch.append(contact)
            if len(batch) >= BATCH_SIZE:
                await flush()
        await flush()
    finally:
        tmp.close()

    error_key = None
    if rejected:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["line", "reason", *headers])
        writer.writerows(rejected)
        error_key = ERROR_REPORT_KEY.format(org=org, uuid=imp.import_uuid)
        if not await storage_fs.acreate_file_from_bytes(error_key, out.getvalue().encode("utf-8")):
            logger.error(f"Could not store the rejected-rows report for import {imp.import_uuid}")
            error_key = None

    await db_client.update_contact_import(
        imp.id,
        status="completed",
        total_rows=seen,
        invalid_count=len(rejected),
        error_report_key=error_key,
    )
