"""Request and response schemas for the contacts API."""

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Names a caller can give a custom field. A safe identifier: it becomes a template
# variable ({{company}}) in campaign prompts.
ATTRIBUTE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

# The standard fields. A custom attribute must not reuse one, or it could silently
# override the phone number when a campaign merges attributes into its context.
RESERVED_ATTRIBUTE_NAMES = frozenset(
    {"phone_number", "first_name", "last_name", "email", "contact_uuid"}
)

MAX_BULK = 1000


def validate_attributes(value: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for name, val in (value or {}).items():
        if not ATTRIBUTE_NAME_RE.match(name):
            raise ValueError(
                f'"{name}" is not a valid field name: use letters, digits and underscores, '
                "starting with a letter"
            )
        if name in RESERVED_ATTRIBUTE_NAMES:
            raise ValueError(f'"{name}" is a standard field and cannot be a custom field')
        if val is not None and not isinstance(val, (str, int, float, bool)):
            raise ValueError(f'The value of "{name}" must be text, a number or true/false')
        cleaned[name] = val
    return cleaned


# --------------------------------------------------------------------- contacts


class ContactCreateRequest(BaseModel):
    phone_number: str = Field(min_length=1, max_length=64)
    # For a number written without its country code ("050 123 4567").
    country_hint: str | None = Field(default=None, min_length=2, max_length=2)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)

    _attrs = field_validator("attributes")(validate_attributes)


class ContactUpdateRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] | None = None

    @field_validator("attributes")
    @classmethod
    def _attrs(cls, value):
        return None if value is None else validate_attributes(value)


class ContactListSummary(BaseModel):
    list_uuid: str
    name: str


class ContactResponse(BaseModel):
    contact_uuid: str
    phone_number: str
    phone_e164: str
    country_code: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_called_at: datetime | None = None
    last_disposition: str | None = None
    call_count: int = 0
    suppressed: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    lists: list[ContactListSummary] | None = Field(
        default=None, description="Only on the detail view."
    )


class ContactPageResponse(BaseModel):
    contacts: list[ContactResponse]
    total_count: int
    page: int
    limit: int
    total_pages: int


class ContactBulkRequest(BaseModel):
    contact_uuids: list[str] = Field(min_length=1, max_length=MAX_BULK)


class ContactBulkResult(BaseModel):
    affected: int


class ContactSummaryResponse(BaseModel):
    total: int
    suppressed: int
    never_called: int
    added_this_month: int
    list_count: int
    last_import_at: datetime | None = None


class ContactRunResponse(BaseModel):
    id: int
    workflow_id: int
    workflow_name: str | None = None
    created_at: str
    call_duration_seconds: int = 0
    disposition: str | None = None
    call_type: str | None = None
    charge_usd: float | None = None


class ContactRunsResponse(BaseModel):
    runs: list[ContactRunResponse]
    total_count: int
    page: int
    limit: int
    total_pages: int


# ----------------------------------------------------------------------- lists


class ContactListCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give the list a name")
        return value


class ContactListUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class ContactListResponse(BaseModel):
    list_uuid: str
    name: str
    description: str | None = None
    contact_count: int = 0
    created_at: datetime | None = None


# ---------------------------------------------------------------- suppressions


class SuppressionCreateRequest(BaseModel):
    phone_numbers: list[str] = Field(min_length=1, max_length=MAX_BULK)
    country_hint: str | None = Field(default=None, min_length=2, max_length=2)
    reason: str | None = Field(default=None, max_length=255)


class SuppressionCreateResponse(BaseModel):
    added: int
    already_suppressed: int
    invalid: list[str] = Field(
        default_factory=list, description="Entries that are not phone numbers."
    )


class SuppressionResponse(BaseModel):
    phone_e164: str
    reason: str | None = None
    source: str
    created_at: datetime | None = None


class SuppressionPageResponse(BaseModel):
    suppressions: list[SuppressionResponse]
    total_count: int
    page: int
    limit: int
    total_pages: int


# --------------------------------------------------------------------- imports


class ImportPreviewResponse(BaseModel):
    headers: list[str]
    rows: list[list[str]]


class ColumnMapping(BaseModel):
    """Which CSV column holds what. Values are CSV header names."""

    phone_number: str = Field(min_length=1)
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    # Custom field name -> CSV header.
    attributes: dict[str, str] = Field(default_factory=dict)
    country_hint: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("attributes")
    @classmethod
    def _names(cls, value: dict[str, str]) -> dict[str, str]:
        validate_attributes({k: "" for k in value})
        return value


class ContactImportRequest(BaseModel):
    source_key: str = Field(min_length=1)
    column_mapping: ColumnMapping
    contact_list_uuid: str | None = None
    dedupe_strategy: Literal["skip", "update"] = "skip"


class SuppressionImportRequest(BaseModel):
    source_key: str = Field(min_length=1)
    phone_column: str = Field(min_length=1)
    country_hint: str | None = Field(default=None, min_length=2, max_length=2)
    reason: str | None = Field(default=None, max_length=255)


class ContactImportResponse(BaseModel):
    import_uuid: str
    mode: Literal["contacts", "suppression"] = "contacts"
    status: Literal["pending", "processing", "completed", "failed"]
    total_rows: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    invalid_count: int = 0
    has_error_report: bool = False
    processing_error: str | None = None
    created_at: datetime | None = None


class ErrorReportUrlResponse(BaseModel):
    url: str
