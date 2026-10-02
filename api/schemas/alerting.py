import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from api.enums import AlertChannelType, AlertComparator, AlertSeverity

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HTTP_METHODS = {"POST", "PUT", "PATCH"}
MAX_RECIPIENTS = 20


class AlertMetricResponse(BaseModel):
    key: str
    label: str
    description: str
    trigger: str
    # "number" (comparator + threshold), "text" (match value) or "flag" (fires when true)
    value_type: str
    unit: Optional[str] = None


class AlertMetricsResponse(BaseModel):
    metrics: list[AlertMetricResponse]
    comparators: list[str]
    severities: list[str]


# -- channels -----------------------------------------------------------------------


class AlertChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: AlertChannelType
    # email: {"recipients": ["a@b.co"]}
    # webhook: {"endpoint_url": "https://...", "http_method": "POST", "credential_uuid": "..."}
    config: dict[str, Any]
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class AlertChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class AlertChannelResponse(BaseModel):
    channel_uuid: str
    name: str
    type: str
    config: dict[str, Any]
    is_active: bool
    created_at: Optional[datetime] = None


class AlertChannelTestResponse(BaseModel):
    # "succeeded", "dead_letter" (failed for good) or "pending" (still being tried)
    status: str
    error: Optional[str] = None
    attempts: int = 0


def clean_channel_config(channel_type: str, config: dict) -> dict:
    """Validate and normalise a channel's config; raises ValueError with a message
    the user can act on. Only known keys are kept."""
    if channel_type == AlertChannelType.EMAIL.value:
        raw = config.get("recipients")
        if not isinstance(raw, list) or not raw:
            raise ValueError("Add at least one recipient email address")
        recipients = []
        for item in raw:
            address = str(item).strip()
            if not _EMAIL.match(address):
                raise ValueError(f"'{address}' is not a valid email address")
            if address.lower() not in [r.lower() for r in recipients]:
                recipients.append(address)
        if len(recipients) > MAX_RECIPIENTS:
            raise ValueError(f"At most {MAX_RECIPIENTS} recipients per channel")
        return {"recipients": recipients}

    url = str(config.get("endpoint_url") or "").strip()
    if not re.match(r"^https?://[^\s/]+", url):
        raise ValueError("The webhook URL must start with http:// or https://")
    method = str(config.get("http_method") or "POST").upper()
    if method not in _HTTP_METHODS:
        raise ValueError("The webhook method must be POST, PUT or PATCH")
    out = {"endpoint_url": url, "http_method": method}
    if config.get("credential_uuid"):
        out["credential_uuid"] = str(config["credential_uuid"])
    return out


# -- rules ----------------------------------------------------------------------------


class AlertRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True
    # None = every agent
    scope_workflow_id: Optional[int] = None
    metric: str
    comparator: AlertComparator = AlertComparator.GT
    threshold: Optional[float] = None
    match_value: Optional[str] = Field(None, max_length=200)
    window_minutes: Optional[int] = Field(None, ge=5, le=1440)
    severity: AlertSeverity = AlertSeverity.MEDIUM
    cooldown_minutes: int = Field(60, ge=1, le=10080)
    channel_uuids: list[str] = Field(default_factory=list, max_length=20)


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    scope_workflow_id: Optional[int] = None
    clear_scope: bool = False
    metric: Optional[str] = None
    comparator: Optional[AlertComparator] = None
    threshold: Optional[float] = None
    match_value: Optional[str] = Field(None, max_length=200)
    window_minutes: Optional[int] = Field(None, ge=5, le=1440)
    severity: Optional[AlertSeverity] = None
    cooldown_minutes: Optional[int] = Field(None, ge=1, le=10080)
    channel_uuids: Optional[list[str]] = Field(None, max_length=20)


class AlertRuleResponse(BaseModel):
    rule_uuid: str
    name: str
    is_active: bool
    scope_workflow_id: Optional[int] = None
    trigger: str
    metric: str
    comparator: str
    threshold: Optional[float] = None
    match_value: Optional[str] = None
    window_minutes: Optional[int] = None
    severity: str
    cooldown_minutes: int
    channel_uuids: list[str]
    last_fired_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# -- events ---------------------------------------------------------------------------


class AlertEventResponse(BaseModel):
    event_uuid: str
    severity: str
    title: str
    detail: dict[str, Any]
    workflow_run_id: Optional[int] = None
    observed_value: Optional[float] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None


class AlertEventsResponse(BaseModel):
    events: list[AlertEventResponse]
