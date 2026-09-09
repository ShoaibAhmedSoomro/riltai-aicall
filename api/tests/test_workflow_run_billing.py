from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.enums import WorkflowRunMode
from api.services import workflow_run_billing as workflow_run_billing_mod
from api.services.workflow_run_billing import (
    _is_usage_not_ready_error,
    report_completed_workflow_run_platform_usage,
    report_workflow_run_platform_usage,
)


def _make_workflow_run():
    return SimpleNamespace(
        id=123,
        workflow_id=456,
        is_completed=True,
        initial_context={"mps_correlation_id": "mps-corr-123"},
        usage_info={"call_duration_seconds": 87},
        workflow=SimpleNamespace(
            organization_id=42,
            user=SimpleNamespace(selected_organization_id=42),
        ),
    )


def test_is_usage_not_ready_error_detects_mps_409():
    exc = Exception("Failed to report platform usage")
    exc.response = SimpleNamespace(
        status_code=409,
        text='{"detail":"usage_not_ready"}',
    )

    assert _is_usage_not_ready_error(exc) is True


@pytest.mark.asyncio
async def test_report_workflow_run_platform_usage_reports_hosted_completion(
    monkeypatch,
):
    workflow_run = _make_workflow_run()
    report_usage = AsyncMock(return_value={"metered": True})

    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )

    await report_workflow_run_platform_usage(workflow_run)

    report_usage.assert_awaited_once_with(
        organization_id=42,
        correlation_id="mps-corr-123",
        duration_seconds=None,
        workflow_run_id=workflow_run.id,
        metadata={
            "source": "workflow_run_completion",
            "workflow_id": workflow_run.workflow_id,
            "duration_source": "mps_correlation",
        },
    )


@pytest.mark.asyncio
async def test_report_workflow_run_platform_usage_reports_duration_without_correlation(
    monkeypatch,
):
    workflow_run = _make_workflow_run()
    workflow_run.initial_context = {}
    report_usage = AsyncMock(return_value={"metered": True})

    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )

    await report_workflow_run_platform_usage(workflow_run)

    report_usage.assert_awaited_once_with(
        organization_id=42,
        correlation_id=None,
        duration_seconds=87.0,
        workflow_run_id=workflow_run.id,
        metadata={
            "source": "workflow_run_completion",
            "workflow_id": workflow_run.workflow_id,
            "duration_source": "rilt_usage_info",
        },
    )


@pytest.mark.asyncio
async def test_report_workflow_run_platform_usage_skips_missing_duration_without_correlation(
    monkeypatch,
):
    workflow_run = _make_workflow_run()
    workflow_run.initial_context = {}
    workflow_run.usage_info = {}
    report_usage = AsyncMock()

    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )

    await report_workflow_run_platform_usage(workflow_run)

    report_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_workflow_run_platform_usage_skips_oss(monkeypatch):
    """OSS must never reach MPS -- report_platform_usage raises for it outright.

    This path now prices locally instead of returning immediately, so the
    no-MPS guarantee is worth keeping asserted rather than assuming it still
    holds by virtue of an early return that is no longer there.
    """
    workflow_run = _make_workflow_run()
    report_usage = AsyncMock()

    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "oss")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )
    monkeypatch.setattr(
        workflow_run_billing_mod.db_client,
        "get_configuration",
        AsyncMock(return_value=None),
    )

    await report_workflow_run_platform_usage(workflow_run)

    report_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_workflow_run_platform_usage_skips_text_chat(monkeypatch):
    workflow_run = _make_workflow_run()
    workflow_run.mode = WorkflowRunMode.TEXTCHAT.value
    report_usage = AsyncMock()

    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )

    await report_workflow_run_platform_usage(workflow_run)

    report_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_workflow_run_platform_usage_skips_incomplete(monkeypatch):
    workflow_run = _make_workflow_run()
    workflow_run.is_completed = False
    report_usage = AsyncMock()

    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )

    await report_workflow_run_platform_usage(workflow_run)

    report_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_completed_workflow_run_platform_usage_loads_run(monkeypatch):
    workflow_run = _make_workflow_run()
    get_run = AsyncMock(return_value=workflow_run)
    report_usage = AsyncMock(return_value={"metered": True})

    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr(
        workflow_run_billing_mod.db_client,
        "get_workflow_run_by_id",
        get_run,
    )
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )

    await report_completed_workflow_run_platform_usage(workflow_run.id)

    get_run.assert_awaited_once_with(workflow_run.id)
    report_usage.assert_awaited_once()


# ── persisting the charge ───────────────────────────────────────────────────
#
# Until this existed the MPS pricing response was logged and discarded, so
# every cost figure in the product had nothing to read. The risk in fixing it
# is the opposite of the original bug: writing a number that is not a real
# charge. A zero, a credit count relabelled as dollars, or a null that blows up
# the usage response are all worse than the empty column that was there before.


def _mps_result(**overrides):
    """An MPS platform-usage response in the ledger-entry shape."""
    result = {
        "charge_usd": 0.42,
        "currency": "USD",
        "metric_code": "platform_minutes",
        "billable_quantity": 1.45,
        "quantity_unit": "minute",
        "credits_delta": -42.0,
    }
    result.update(overrides)
    return result


def _patch_hosted(monkeypatch, *, report_result=None, report_error=None):
    report_usage = AsyncMock(
        return_value=report_result if report_error is None else None,
        side_effect=report_error,
    )
    update_run = AsyncMock()
    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )
    monkeypatch.setattr(
        workflow_run_billing_mod.db_client, "update_workflow_run", update_run
    )
    return report_usage, update_run


@pytest.mark.asyncio
async def test_the_mps_charge_is_persisted_onto_the_run(monkeypatch):
    workflow_run = _make_workflow_run()
    _, update_run = _patch_hosted(monkeypatch, report_result=_mps_result())

    await report_workflow_run_platform_usage(workflow_run)

    update_run.assert_awaited_once()
    cost_info = update_run.await_args.kwargs["cost_info"]
    assert update_run.await_args.kwargs["run_id"] == workflow_run.id
    assert cost_info["charge_usd"] == 0.42
    # The key the rest of the product already reads.
    assert cost_info["total_cost_usd"] == 0.42
    assert cost_info["source"] == "mps_platform_usage"
    assert cost_info["metric_code"] == "platform_minutes"


@pytest.mark.asyncio
async def test_a_usage_not_ready_409_writes_no_cost(monkeypatch):
    """No charge is not a charge of zero.

    A run can pick up a correlation id and then end before billable usage is
    recorded. Writing 0.00 there would report the call as free rather than as
    unpriced, and it would be indistinguishable from a genuinely free call.
    """
    workflow_run = _make_workflow_run()
    error = Exception("boom")
    error.response = SimpleNamespace(status_code=409, text="usage_not_ready")
    _, update_run = _patch_hosted(monkeypatch, report_error=error)

    await report_workflow_run_platform_usage(workflow_run)

    update_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_any_reporting_failure_writes_no_cost(monkeypatch):
    workflow_run = _make_workflow_run()
    _, update_run = _patch_hosted(monkeypatch, report_error=RuntimeError("mps down"))

    await report_workflow_run_platform_usage(workflow_run)

    update_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failure_to_persist_does_not_fail_the_completion_job(monkeypatch):
    # The run is finished and reported whether or not we managed to record what
    # it cost. Raising here would retry the whole completion job for a number.
    workflow_run = _make_workflow_run()
    _, update_run = _patch_hosted(monkeypatch, report_result=_mps_result())
    update_run.side_effect = RuntimeError("db gone")

    await report_workflow_run_platform_usage(workflow_run)  # must not raise

    update_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_credits_are_never_relabelled_as_dollars(monkeypatch):
    """The credit-to-currency rate is MPS's, not ours.

    A response with credits but no dollar figure must not produce a USD number.
    Deriving one would put an invented value in a column labelled USD.
    """
    workflow_run = _make_workflow_run()
    _, update_run = _patch_hosted(
        monkeypatch,
        report_result={"credits_delta": -42.0, "metric_code": "platform_minutes"},
    )

    await report_workflow_run_platform_usage(workflow_run)

    cost_info = update_run.await_args.kwargs["cost_info"]
    assert "charge_usd" not in cost_info
    # And critically NOT present as None: run_usage_response.py does float() on
    # this key when it exists, so a null would raise on every usage response.
    assert "total_cost_usd" not in cost_info
    assert cost_info["credits_delta"] == -42.0


@pytest.mark.asyncio
async def test_minor_units_are_only_read_as_usd_when_the_currency_says_so(monkeypatch):
    workflow_run = _make_workflow_run()
    _, update_run = _patch_hosted(
        monkeypatch,
        report_result={"amount_minor": 1234, "amount_currency": "USD"},
    )
    await report_workflow_run_platform_usage(workflow_run)
    assert update_run.await_args.kwargs["cost_info"]["charge_usd"] == 12.34

    workflow_run = _make_workflow_run()
    _, update_run = _patch_hosted(
        monkeypatch,
        report_result={"amount_minor": 1234, "amount_currency": "AED"},
    )
    await report_workflow_run_platform_usage(workflow_run)
    # No USD figure is invented for a non-USD charge...
    cost_info = update_run.await_args.kwargs["cost_info"]
    assert "charge_usd" not in cost_info
    assert "total_cost_usd" not in cost_info
    # ...but the charge itself is still recorded, rather than the run
    # being left looking unpriced when it was actually billed.
    assert cost_info["amount_minor"] == 1234
    assert cost_info["amount_currency"] == "AED"


@pytest.mark.asyncio
async def test_an_empty_mps_response_writes_nothing(monkeypatch):
    workflow_run = _make_workflow_run()
    _, update_run = _patch_hosted(monkeypatch, report_result={})

    await report_workflow_run_platform_usage(workflow_run)

    update_run.assert_not_awaited()


# ── the self-hosted rate card ───────────────────────────────────────────────


def _patch_oss(monkeypatch, rate_card_value):
    config = (
        SimpleNamespace(value=rate_card_value) if rate_card_value is not None else None
    )
    report_usage = AsyncMock()
    update_run = AsyncMock()
    monkeypatch.setattr(workflow_run_billing_mod, "DEPLOYMENT_MODE", "oss")
    monkeypatch.setattr(
        workflow_run_billing_mod.mps_service_key_client,
        "report_platform_usage",
        report_usage,
    )
    monkeypatch.setattr(
        workflow_run_billing_mod.db_client,
        "get_configuration",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        workflow_run_billing_mod.db_client, "update_workflow_run", update_run
    )
    return report_usage, update_run


@pytest.mark.asyncio
async def test_self_hosted_prices_minutes_from_the_rate_card(monkeypatch):
    workflow_run = _make_workflow_run()  # 87 seconds
    report_usage, update_run = _patch_oss(
        monkeypatch, {"price_per_minute_usd": 0.10, "currency": "USD"}
    )

    await report_workflow_run_platform_usage(workflow_run)

    # MPS is unreachable in OSS and must not be called even now that this path
    # does real work.
    report_usage.assert_not_awaited()
    cost_info = update_run.await_args.kwargs["cost_info"]
    assert cost_info["charge_usd"] == pytest.approx(87 / 60 * 0.10, abs=1e-9)
    assert cost_info["total_cost_usd"] == cost_info["charge_usd"]
    assert cost_info["source"] == "local_rate_card"
    assert cost_info["rate_per_minute_usd"] == 0.10
    assert cost_info["quantity_unit"] == "minute"


@pytest.mark.asyncio
async def test_no_rate_card_means_no_cost_rather_than_zero(monkeypatch):
    """THE rule for this path.

    An operator who has not set a price has not claimed calls are free. Writing
    0.00 would make every money surface show a total of zero dollars, which
    reads as a measurement rather than as an absence.
    """
    workflow_run = _make_workflow_run()
    _, update_run = _patch_oss(monkeypatch, None)

    await report_workflow_run_platform_usage(workflow_run)

    update_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_zero_or_junk_rate_is_treated_as_unset(monkeypatch):
    for value in ({"price_per_minute_usd": 0}, {"price_per_minute_usd": "abc"}, {}):
        workflow_run = _make_workflow_run()
        _, update_run = _patch_oss(monkeypatch, value)
        await report_workflow_run_platform_usage(workflow_run)
        update_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_hosted_without_a_duration_writes_nothing(monkeypatch):
    workflow_run = _make_workflow_run()
    workflow_run.usage_info = {}
    _, update_run = _patch_oss(
        monkeypatch, {"price_per_minute_usd": 0.10, "currency": "USD"}
    )

    await report_workflow_run_platform_usage(workflow_run)

    update_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_hosted_still_skips_text_chat_and_incomplete_runs(monkeypatch):
    # The OSS branch moved BELOW these guards, so they have to still apply.
    for mutate in (
        lambda r: setattr(r, "mode", WorkflowRunMode.TEXTCHAT.value),
        lambda r: setattr(r, "is_completed", False),
        lambda r: setattr(r, "workflow", SimpleNamespace(organization_id=None)),
    ):
        workflow_run = _make_workflow_run()
        mutate(workflow_run)
        _, update_run = _patch_oss(
            monkeypatch, {"price_per_minute_usd": 0.10, "currency": "USD"}
        )
        await report_workflow_run_platform_usage(workflow_run)
        update_run.assert_not_awaited()
