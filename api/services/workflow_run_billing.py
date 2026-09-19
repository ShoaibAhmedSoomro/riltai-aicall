"""Workflow-run billing hooks.

AICall does not rate or deduct credits locally on the hosted path. MPS owns
credit accounting, and for hosted deployments AICall reports completed platform
usage to MPS. When a server-minted MPS correlation id exists, MPS uses
model-service usage as the canonical duration. Otherwise AICall reports the
completed run duration.

What this module now also does is *persist* the resulting charge onto the run.
Before that, the MPS pricing response was logged and thrown away, so every cost
figure in the product — the usage page, the call-history cost column, the
dashboard's spend panels — had nothing to read and rendered null or a sample
number.

Self-hosted deployments never reach MPS at all (`DEPLOYMENT_MODE == "oss"`, the
default), so they price minutes locally against an org-level rate card. No rate
card configured means no cost_info is written and every money surface shows its
empty state. That is deliberate: a zero is a claim that the call was free, and
an operator who has not set a price has not made that claim.
"""

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.constants import DEPLOYMENT_MODE
from api.db import db_client
from api.enums import OrganizationConfigurationKey, WorkflowRunMode
from api.services.managed_model_services import get_mps_correlation_id
from api.services.mps_service_key_client import mps_service_key_client

# Written into cost_info.source so a reader can tell a metered charge from a
# locally-priced estimate without inspecting the other keys.
COST_SOURCE_MPS = "mps_platform_usage"
COST_SOURCE_LOCAL_RATE_CARD = "local_rate_card"

SECONDS_PER_MINUTE = 60.0


def _workflow_run_organization_id(workflow_run) -> int | None:
    workflow = getattr(workflow_run, "workflow", None)
    return getattr(workflow, "organization_id", None)


def _duration_seconds_from_usage_info(workflow_run) -> float | None:
    usage_info: dict[str, Any] = getattr(workflow_run, "usage_info", None) or {}
    duration = usage_info.get("call_duration_seconds")
    try:
        duration_seconds = float(duration)
    except (TypeError, ValueError):
        return None

    return duration_seconds if duration_seconds > 0 else None


def _is_usage_not_ready_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) != 409:
        return False
    return "usage_not_ready" in (getattr(response, "text", "") or "")


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _charge_usd_from_mps_result(result: dict) -> float | None:
    """The dollar charge MPS reported, or None when it did not report one.

    NOT derived from ``credits_delta``. Credits are MPS's own unit and the
    credit-to-currency rate is owned there, so converting one into the other
    here would invent a number and put it in a column labelled USD.

    ``amount_minor`` is only used when the accompanying currency actually says
    USD -- the field is minor units of whatever currency the account bills in.
    """
    explicit = _coerce_float(result.get("charge_usd"))
    if explicit is None:
        explicit = _coerce_float(result.get("amount_usd"))
    if explicit is not None:
        return abs(explicit)

    currency = (result.get("amount_currency") or result.get("currency") or "").upper()
    if currency == "USD":
        minor = _coerce_float(result.get("amount_minor"))
        if minor is not None:
            return abs(minor) / 100.0

    return None


def _cost_info_from_mps_result(result: Any) -> dict | None:
    """Normalise an MPS platform-usage response into the stored cost shape.

    Returns None when the response carries nothing worth storing, so a run is
    left with an empty cost_info rather than a row that looks priced.

    The field names come from the MPS ledger-entry shape this codebase already
    parses in api/routes/organization_usage.py. They are NOT verified against a
    live MPS response: this deployment runs in OSS mode and never calls it. So
    every field is optional and absence is tolerated rather than assumed away.
    """
    if not isinstance(result, dict):
        return None

    charge_usd = _charge_usd_from_mps_result(result)
    cost_info: dict[str, Any] = {
        "source": COST_SOURCE_MPS,
        "priced_at": datetime.now(UTC).isoformat(),
    }

    if charge_usd is not None:
        cost_info["charge_usd"] = charge_usd
        # total_cost_usd is the key the rest of the product already reads --
        # api/db/filters.py's tokenUsage filter and run_usage_response.py. That
        # reader does float() on it, so the key is written ONLY when there is a
        # real number: an explicit None would raise on every usage response.
        cost_info["total_cost_usd"] = charge_usd

    # amount_minor/amount_currency are copied even when they are not USD.
    # Without them a charge MPS made in another currency would be discarded
    # entirely -- charge_usd cannot hold it, so the run would look unpriced
    # when it was in fact billed.
    for key in (
        "currency",
        "amount_minor",
        "amount_currency",
        "metric_code",
        "billable_quantity",
        "quantity_unit",
        "credits_delta",
    ):
        value = result.get(key)
        if value is not None:
            cost_info[key] = value

    # Nothing but the two bookkeeping keys means MPS told us nothing useful.
    if len(cost_info) == 2:
        return None
    return cost_info


async def _rate_card_for_organization(organization_id: int) -> dict | None:
    """The org's local rate card, or None when the operator has not set one."""
    try:
        config = await db_client.get_configuration(
            organization_id,
            OrganizationConfigurationKey.USAGE_RATE_CARD.value,
        )
    except Exception as e:
        logger.warning(
            "Could not read the usage rate card for organization {}: {}",
            organization_id,
            e,
        )
        return None

    value = getattr(config, "value", None) or {}
    rate = _coerce_float(value.get("price_per_minute_usd"))
    if rate is None or rate <= 0:
        return None
    return {
        "price_per_minute_usd": rate,
        "currency": str(value.get("currency") or "USD").upper(),
    }


def _cost_info_from_rate_card(duration_seconds: float, rate_card: dict) -> dict:
    rate = float(rate_card["price_per_minute_usd"])
    charge = round(duration_seconds / SECONDS_PER_MINUTE * rate, 6)
    return {
        "source": COST_SOURCE_LOCAL_RATE_CARD,
        "priced_at": datetime.now(UTC).isoformat(),
        "charge_usd": charge,
        "total_cost_usd": charge,
        "currency": rate_card["currency"],
        "rate_per_minute_usd": rate,
        "billable_quantity": round(duration_seconds / SECONDS_PER_MINUTE, 6),
        "quantity_unit": "minute",
    }


async def _persist_cost_info(workflow_run_id: int, cost_info: dict) -> None:
    """Store the charge, and never let storing it fail the completion job.

    Same isolation as the pricing call itself: a run that is finished and
    reported is finished whether or not we managed to write what it cost.
    """
    try:
        await db_client.update_workflow_run(run_id=workflow_run_id, cost_info=cost_info)
        logger.info(
            "Persisted cost_info for workflow run {}: {}", workflow_run_id, cost_info
        )
    except Exception as e:
        logger.error(
            "Failed to persist cost_info for workflow run {}: {}", workflow_run_id, e
        )


async def _price_from_local_rate_card(workflow_run, organization_id: int) -> None:
    """Price a self-hosted run against the org's rate card, if it has one."""
    rate_card = await _rate_card_for_organization(organization_id)
    if rate_card is None:
        logger.debug(
            "No usage rate card for organization {}; leaving workflow run {} unpriced",
            organization_id,
            workflow_run.id,
        )
        return

    duration_seconds = _duration_seconds_from_usage_info(workflow_run)
    if duration_seconds is None:
        logger.warning(
            "Skipping local pricing for workflow run {}: no billable duration",
            workflow_run.id,
        )
        return

    await _persist_cost_info(
        workflow_run.id, _cost_info_from_rate_card(duration_seconds, rate_card)
    )


async def report_workflow_run_platform_usage(workflow_run) -> None:
    """Report hosted platform usage for a completed workflow run, and store the charge."""
    if getattr(workflow_run, "mode", None) == WorkflowRunMode.TEXTCHAT.value:
        # This skips LOCAL rate-card pricing too, not just the MPS report --
        # _price_from_local_rate_card is called below this line. That is
        # intended: the rate card is priced per minute of TALK TIME, and a text
        # chat's duration is wall-clock typing time, so billing it at a voice
        # rate would invent spend. The overview's Spend panel says so rather
        # than leaving the reader to wonder why a completed run has no cost.
        #
        # To price chats, move the _price_from_local_rate_card call above this
        # guard -- but give them their own rate first, because per-minute is
        # the wrong unit for a conversation nobody spoke in.
        logger.info(
            "Skipping platform usage report and local pricing for text chat "
            "workflow run {}",
            workflow_run.id,
        )
        return

    if not getattr(workflow_run, "is_completed", False):
        logger.warning(
            "Workflow run is not completed in report_workflow_run_platform_usage"
        )
        return

    organization_id = _workflow_run_organization_id(workflow_run)
    if organization_id is None:
        logger.warning(
            "Skipping platform usage report for workflow run {}: no organization_id",
            workflow_run.id,
        )
        return

    # Self-hosted: MPS is unreachable by design (report_platform_usage raises
    # for oss), so price locally instead of leaving every cost figure null.
    if DEPLOYMENT_MODE == "oss":
        await _price_from_local_rate_card(workflow_run, organization_id)
        return

    correlation_id = get_mps_correlation_id(
        getattr(workflow_run, "initial_context", None)
    )
    duration_seconds = (
        None if correlation_id else _duration_seconds_from_usage_info(workflow_run)
    )
    if not correlation_id and duration_seconds is None:
        logger.warning(
            "Skipping platform usage report for workflow run {}: no billable duration",
            workflow_run.id,
        )
        return

    try:
        result = await mps_service_key_client.report_platform_usage(
            organization_id=organization_id,
            correlation_id=correlation_id,
            duration_seconds=duration_seconds,
            workflow_run_id=workflow_run.id,
            metadata={
                "source": "workflow_run_completion",
                "workflow_id": getattr(workflow_run, "workflow_id", None),
                "duration_source": (
                    "mps_correlation" if correlation_id else "rilt_usage_info"
                ),
            },
        )
        logger.info(
            "Reported platform usage for workflow run {} to MPS: {}",
            workflow_run.id,
            result,
        )
    except Exception as e:
        if _is_usage_not_ready_error(e):
            # A run can start and receive an MPS correlation id, then fail or end
            # before billable STT usage is recorded. MPS returns usage_not_ready
            # for that no-platform-fee path, so keep it out of error alerts. No
            # cost_info is written: there is no charge, not a charge of zero.
            logger.warning(
                "Failed to report platform usage for workflow run {}: {}",
                workflow_run.id,
                e,
            )
        else:
            logger.error(
                "Failed to report platform usage for workflow run {}: {}",
                workflow_run.id,
                e,
            )
        return

    cost_info = _cost_info_from_mps_result(result)
    if cost_info is None:
        logger.warning(
            "MPS reported usage for workflow run {} with no priceable fields; "
            "leaving cost_info unwritten",
            workflow_run.id,
        )
        return

    await _persist_cost_info(workflow_run.id, cost_info)


async def report_completed_workflow_run_platform_usage(workflow_run_id: int) -> None:
    """Load a completed workflow run and report platform usage to MPS."""
    workflow_run = await db_client.get_workflow_run_by_id(workflow_run_id)
    if not workflow_run:
        logger.warning(
            "Skipping platform usage report: workflow run {} not found",
            workflow_run_id,
        )
        return

    await report_workflow_run_platform_usage(workflow_run)
