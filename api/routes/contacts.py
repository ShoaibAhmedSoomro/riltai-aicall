"""Contacts, lists, imports and the do-not-call list.

Route order matters here: FastAPI matches in declaration order, so every literal
path (``/summary``, ``/lists``, ``/suppressions``, ``/import``, ``/imports``)
comes BEFORE the ``/{contact_uuid}`` routes. Declared after them they would be
swallowed as a contact id. api/tests/test_literal_routes_are_reachable.py guards it.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.db import db_client
from api.db.contacts_client import ContactAlreadyExistsError, ContactListNameTakenError
from api.db.models import ContactImportModel, ContactModel, UserModel
from api.schemas.contacts import (
    ContactBulkRequest,
    ContactBulkResult,
    ContactCreateRequest,
    ContactImportRequest,
    ContactImportResponse,
    ContactListCreateRequest,
    ContactListResponse,
    ContactListSummary,
    ContactListUpdateRequest,
    ContactPageResponse,
    ContactResponse,
    ContactRunResponse,
    ContactRunsResponse,
    ContactSummaryResponse,
    ContactUpdateRequest,
    ErrorReportUrlResponse,
    ImportPreviewResponse,
    SuppressionCreateRequest,
    SuppressionCreateResponse,
    SuppressionImportRequest,
    SuppressionPageResponse,
    SuppressionResponse,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.contacts.import_service import ContactImportError, preview_csv
from api.services.contacts.phone import to_e164
from api.services.storage import storage_fs
from api.tasks.arq import enqueue_job
from api.tasks.function_names import FunctionNames

router = APIRouter(prefix="/contacts", tags=["contacts"])

PHONE_HELP = "Enter a valid phone number, with its country code (for example +971501234567)."


# --------------------------------------------------------------------- helpers


def _owns_key(organization_id: int, key: str) -> bool:
    """Only files this organization uploaded. A storage key comes from the request,
    so it must be proved to be the caller's before the server reads it: otherwise
    anyone could import another tenant's file by guessing its path."""
    parts = key.split("/")
    return len(parts) >= 3 and parts[0] == "campaigns" and parts[1] == str(organization_id)


def _contact_response(
    contact: ContactModel, suppressed: bool, lists=None
) -> ContactResponse:
    return ContactResponse(
        contact_uuid=contact.contact_uuid,
        phone_number=contact.phone_number,
        phone_e164=contact.phone_e164,
        country_code=contact.country_code,
        first_name=contact.first_name,
        last_name=contact.last_name,
        email=contact.email,
        attributes=contact.attributes or {},
        last_called_at=contact.last_called_at,
        last_disposition=contact.last_disposition,
        call_count=contact.call_count or 0,
        suppressed=suppressed,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        lists=lists,
    )


def _list_response(row) -> ContactListResponse:
    return ContactListResponse(
        list_uuid=row.list_uuid,
        name=row.name,
        description=row.description,
        contact_count=row.contact_count or 0,
        created_at=row.created_at,
    )


def _import_response(row: ContactImportModel) -> ContactImportResponse:
    return ContactImportResponse(
        import_uuid=row.import_uuid,
        mode=(row.column_mapping or {}).get("mode", "contacts"),
        status=row.status,
        total_rows=row.total_rows or 0,
        created_count=row.created_count or 0,
        updated_count=row.updated_count or 0,
        skipped_count=row.skipped_count or 0,
        invalid_count=row.invalid_count or 0,
        has_error_report=bool(row.error_report_key),
        processing_error=row.processing_error,
        created_at=row.created_at,
    )


def _pages(total: int, limit: int) -> int:
    return (total + limit - 1) // limit


async def _get_list_or_404(user: UserModel, list_uuid: str):
    row = await db_client.get_contact_list_by_uuid(list_uuid, user.selected_organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="List not found")
    return row


async def _start_import(
    user: UserModel, *, source_key, mapping, strategy, list_id=None
) -> ContactImportResponse:
    org = user.selected_organization_id
    if not _owns_key(org, source_key):
        raise HTTPException(status_code=403, detail="That file does not belong to this organization")
    row = await db_client.create_contact_import(
        org,
        source_key=source_key,
        column_mapping=mapping,
        dedupe_strategy=strategy,
        contact_list_id=list_id,
        created_by=user.id,
    )
    try:
        await enqueue_job(FunctionNames.PROCESS_CONTACT_IMPORT, row.import_uuid)
    except Exception as exc:
        # Left "pending" forever would look like it is still coming.
        logger.error(f"Could not queue contact import {row.import_uuid}: {exc}")
        await db_client.update_contact_import(
            row.id, status="failed", processing_error="Could not start the import. Try again."
        )
        row = await db_client.get_contact_import(row.import_uuid, org)
    return _import_response(row)


# -------------------------------------------------------------------- summary


@router.get("/summary", response_model=ContactSummaryResponse)
async def get_contacts_summary(user: UserModel = Depends(get_user_with_selected_organization)):
    return ContactSummaryResponse(
        **await db_client.get_contacts_summary(user.selected_organization_id)
    )


# ----------------------------------------------------------------------- lists


@router.get("/lists", response_model=list[ContactListResponse])
async def list_contact_lists(user: UserModel = Depends(get_user_with_selected_organization)):
    rows = await db_client.list_contact_lists(user.selected_organization_id)
    return [_list_response(r) for r in rows]


@router.post("/lists", response_model=ContactListResponse, status_code=201)
async def create_contact_list(
    request: ContactListCreateRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        row = await db_client.create_contact_list(
            user.selected_organization_id,
            name=request.name,
            description=request.description,
            created_by=user.id,
        )
    except ContactListNameTakenError:
        raise HTTPException(status_code=409, detail="A list with that name already exists")
    return _list_response(row)


@router.patch("/lists/{list_uuid}", response_model=ContactListResponse)
async def update_contact_list(
    list_uuid: str,
    request: ContactListUpdateRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        row = await db_client.update_contact_list(
            list_uuid,
            user.selected_organization_id,
            name=request.name,
            description=request.description,
        )
    except ContactListNameTakenError:
        raise HTTPException(status_code=409, detail="A list with that name already exists")
    if row is None:
        raise HTTPException(status_code=404, detail="List not found")
    return _list_response(row)


@router.delete("/lists/{list_uuid}", status_code=204)
async def delete_contact_list(
    list_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
):
    if not await db_client.delete_contact_list(list_uuid, user.selected_organization_id):
        raise HTTPException(status_code=404, detail="List not found")


@router.post("/lists/{list_uuid}/members", response_model=ContactBulkResult)
async def add_list_members(
    list_uuid: str,
    request: ContactBulkRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    row = await _get_list_or_404(user, list_uuid)
    added = await db_client.add_contact_uuids_to_list(
        row.id, user.selected_organization_id, request.contact_uuids
    )
    return ContactBulkResult(affected=added)


@router.delete("/lists/{list_uuid}/members", response_model=ContactBulkResult)
async def remove_list_members(
    list_uuid: str,
    request: ContactBulkRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    row = await _get_list_or_404(user, list_uuid)
    removed = await db_client.remove_contact_uuids_from_list(
        row.id, user.selected_organization_id, request.contact_uuids
    )
    return ContactBulkResult(affected=removed)


# ---------------------------------------------------------------- suppressions


@router.get("/suppressions", response_model=SuppressionPageResponse)
async def list_suppressions(
    q: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    rows, total = await db_client.list_suppressions(
        user.selected_organization_id, q=q, limit=limit, offset=(page - 1) * limit
    )
    return SuppressionPageResponse(
        suppressions=[
            SuppressionResponse(
                phone_e164=r.phone_e164, reason=r.reason, source=r.source, created_at=r.created_at
            )
            for r in rows
        ],
        total_count=total,
        page=page,
        limit=limit,
        total_pages=_pages(total, limit),
    )


@router.post("/suppressions", response_model=SuppressionCreateResponse)
async def add_suppressions(
    request: SuppressionCreateRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    valid: list[str] = []
    invalid: list[str] = []
    for raw in request.phone_numbers:
        parsed = to_e164(raw, request.country_hint)
        (valid if parsed else invalid).append(parsed[0] if parsed else raw)
    added = await db_client.add_suppressions_batch(
        user.selected_organization_id,
        valid,
        source="manual",
        reason=request.reason,
        created_by=user.id,
    )
    return SuppressionCreateResponse(
        added=added, already_suppressed=len(set(valid)) - added, invalid=invalid
    )


@router.delete("/suppressions", status_code=204)
async def remove_suppression(
    phone_e164: str = Query(..., description="The number, in E.164 form, e.g. +971501234567"),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    parsed = to_e164(phone_e164)
    if not parsed or not await db_client.remove_suppression(
        user.selected_organization_id, parsed[0]
    ):
        raise HTTPException(status_code=404, detail="That number is not on the list")


@router.post("/suppressions/import", response_model=ContactImportResponse)
async def import_suppressions(
    request: SuppressionImportRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Bulk-load a do-not-call file. Runs as the same background job as a contact
    import, in suppression mode."""
    return await _start_import(
        user,
        source_key=request.source_key,
        mapping={
            "mode": "suppression",
            "phone_number": request.phone_column,
            "country_hint": request.country_hint,
            "reason": request.reason,
        },
        strategy="skip",
    )


# --------------------------------------------------------------------- imports


@router.get("/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    source_key: str = Query(..., description="The key returned by the CSV upload"),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """The file's column names and first rows, so the mapping step can offer them."""
    if not _owns_key(user.selected_organization_id, source_key):
        raise HTTPException(status_code=403, detail="That file does not belong to this organization")
    try:
        return ImportPreviewResponse(**await preview_csv(source_key))
    except ContactImportError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import", response_model=ContactImportResponse)
async def import_contacts(
    request: ContactImportRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    list_id = None
    if request.contact_list_uuid:
        list_id = (await _get_list_or_404(user, request.contact_list_uuid)).id
    return await _start_import(
        user,
        source_key=request.source_key,
        mapping={**request.column_mapping.model_dump(), "mode": "contacts"},
        strategy=request.dedupe_strategy,
        list_id=list_id,
    )


@router.get("/imports/{import_uuid}", response_model=ContactImportResponse)
async def get_import(
    import_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
):
    row = await db_client.get_contact_import(import_uuid, user.selected_organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return _import_response(row)


@router.get("/imports/{import_uuid}/error-report-url", response_model=ErrorReportUrlResponse)
async def get_import_error_report_url(
    import_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
):
    row = await db_client.get_contact_import(import_uuid, user.selected_organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Import not found")
    if not row.error_report_key:
        raise HTTPException(status_code=404, detail="Every row in this import was accepted")
    url = await storage_fs.aget_signed_url(row.error_report_key, expiration=3600)
    if not url:
        raise HTTPException(status_code=502, detail="Could not create the download link")
    return ErrorReportUrlResponse(url=url)


# -------------------------------------------------------------------- contacts


@router.post("/bulk-delete", response_model=ContactBulkResult)
async def bulk_delete_contacts(
    request: ContactBulkRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Delete contacts. Numbers on the do-not-call list stay on it."""
    deleted = await db_client.delete_contacts(
        user.selected_organization_id, request.contact_uuids
    )
    return ContactBulkResult(affected=deleted)


@router.get("", response_model=ContactPageResponse)
async def list_contacts(
    q: str | None = None,
    list_uuid: str | None = None,
    suppressed: bool | None = None,
    sort: str = Query("created_at", pattern="^(created_at|name|last_called_at|call_count)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    list_id = None
    if list_uuid:
        list_id = (await _get_list_or_404(user, list_uuid)).id
    rows, total = await db_client.list_contacts(
        user.selected_organization_id,
        q=q,
        list_id=list_id,
        suppressed=suppressed,
        sort=sort,
        limit=limit,
        offset=(page - 1) * limit,
    )
    return ContactPageResponse(
        contacts=[_contact_response(c, s) for c, s in rows],
        total_count=total,
        page=page,
        limit=limit,
        total_pages=_pages(total, limit),
    )


@router.post("", response_model=ContactResponse, status_code=201)
async def create_contact(
    request: ContactCreateRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    parsed = to_e164(request.phone_number, request.country_hint)
    if not parsed:
        raise HTTPException(status_code=422, detail=PHONE_HELP)
    e164, country = parsed
    try:
        contact = await db_client.create_contact(
            user.selected_organization_id,
            phone_number=request.phone_number.strip(),
            phone_e164=e164,
            country_code=country,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            attributes=request.attributes,
            created_by=user.id,
        )
    except ContactAlreadyExistsError:
        raise HTTPException(status_code=409, detail="A contact with that phone number already exists")
    suppressed = bool(
        await db_client.filter_suppressed_e164(user.selected_organization_id, [e164])
    )
    return _contact_response(contact, suppressed)


# --- everything below is `/{contact_uuid}`: keep it LAST (see the module docstring)


@router.get("/{contact_uuid}", response_model=ContactResponse)
async def get_contact(
    contact_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
):
    org = user.selected_organization_id
    contact = await db_client.get_contact_by_uuid(contact_uuid, org)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    suppressed = bool(await db_client.filter_suppressed_e164(org, [contact.phone_e164]))
    lists = await db_client.list_lists_for_contact(contact.id, org)
    return _contact_response(
        contact,
        suppressed,
        [ContactListSummary(list_uuid=l.list_uuid, name=l.name) for l in lists],
    )


@router.patch("/{contact_uuid}", response_model=ContactResponse)
async def update_contact(
    contact_uuid: str,
    request: ContactUpdateRequest,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    org = user.selected_organization_id
    # Only the fields the caller sent: an omitted field is left alone, an explicit
    # null clears it.
    contact = await db_client.update_contact(
        contact_uuid, org, request.model_dump(exclude_unset=True)
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    suppressed = bool(await db_client.filter_suppressed_e164(org, [contact.phone_e164]))
    return _contact_response(contact, suppressed)


@router.delete("/{contact_uuid}", status_code=204)
async def delete_contact(
    contact_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
):
    if not await db_client.delete_contacts(user.selected_organization_id, [contact_uuid]):
        raise HTTPException(status_code=404, detail="Contact not found")


@router.get("/{contact_uuid}/runs", response_model=ContactRunsResponse)
async def get_contact_runs(
    contact_uuid: str,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Calls placed to this contact's number, across every agent.

    The filter DSL stays on the server: the caller sends a contact id and gets runs
    back, and the exact-match-on-an-index detail is not theirs to know.
    """
    org = user.selected_organization_id
    contact = await db_client.get_contact_by_uuid(contact_uuid, org)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    runs, total, _charge, _duration = await db_client.get_usage_history(
        org,
        limit=limit,
        offset=(page - 1) * limit,
        filters=[
            {
                "attribute": "calledNumberExact",
                "type": "text",
                "value": {"value": contact.phone_e164},
            }
        ],
    )
    return ContactRunsResponse(
        runs=[
            ContactRunResponse(
                id=r["id"],
                workflow_id=r["workflow_id"],
                workflow_name=r.get("workflow_name"),
                created_at=str(r["created_at"]),
                call_duration_seconds=r.get("call_duration_seconds") or 0,
                disposition=r.get("disposition"),
                call_type=r.get("call_type"),
                charge_usd=r.get("charge_usd"),
            )
            for r in runs
        ],
        total_count=total,
        page=page,
        limit=limit,
        total_pages=_pages(total, limit),
    )
