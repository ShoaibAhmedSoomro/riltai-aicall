"""The post-call safety scan records what happened, and never lies by omission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.schemas.organization_preferences import OrganizationPreferences
from api.services.governance import safety_scan
from api.services.governance.policy import resolve_governance_policy
from api.services.governance.safety_scan import (
    build_system_prompt,
    normalise_result,
    scan_run_safety,
)

LONG_TALK = [
    {"type": "rtf-user-transcription", "timestamp": "2026-10-02T10:00:00+00:00",
     "payload": {"text": "hello I would like some advice on my savings account", "final": True}},
    {"type": "rtf-bot-text", "timestamp": "2026-10-02T10:00:05+00:00",
     "payload": {"text": "You should put everything into this one stock right away"}},
]


def _policy(**guardrails):
    return resolve_governance_policy(
        {"governance_configuration": {"guardrails": guardrails}}, OrganizationPreferences()
    )


def _run(events=LONG_TALK):
    return SimpleNamespace(logs={"realtime_feedback_events": events})


def test_the_prompt_names_only_the_categories_asked_for():
    prompt = build_system_prompt(["financial_advice"], check_jailbreak=False)
    assert "financial_advice" in prompt and "hate" not in prompt
    # The instruction to look for jailbreaks is only given when it was asked for.
    assert "ignore its instructions" not in prompt
    assert "ignore its instructions" in build_system_prompt([], check_jailbreak=True)


def test_a_category_the_model_invented_never_reaches_the_record():
    """The model's JSON is untrusted input."""
    out = normalise_result(
        {
            "jailbreak_attempt": "yes",  # not a real bool
            "violations": [
                {"category": "financial_advice", "severity": "high", "evidence": "x" * 999},
                {"category": "made_up_thing", "severity": "high"},
                "not even a dict",
            ],
        },
        ["financial_advice"],
    )
    assert out["jailbreak_attempt"] is False
    assert [v["category"] for v in out["violations"]] == ["financial_advice"]
    assert len(out["violations"][0]["evidence"]) == 300


def test_a_bad_severity_becomes_medium_not_a_free_text_field():
    out = normalise_result(
        {"violations": [{"category": "hate", "severity": "apocalyptic"}]}, ["hate"]
    )
    assert out["violations"][0]["severity"] == "medium"


@pytest.mark.asyncio
async def test_nothing_enabled_means_no_scan_and_no_annotation():
    assert await scan_run_safety(_run(), 1, _policy()) is None


@pytest.mark.asyncio
async def test_a_trivial_call_is_skipped_rather_than_judged(monkeypatch):
    llm = AsyncMock()
    monkeypatch.setattr(safety_scan, "create_qa_llm_service", llm)
    out = await scan_run_safety(_run([]), 1, _policy(input_jailbreak=True))
    assert out["status"] == "skipped" and out["reason"] == "no_transcript"
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_scanned_call_records_what_was_found(monkeypatch):
    monkeypatch.setattr(
        safety_scan, "create_qa_llm_service", AsyncMock(return_value=(object(), "m1"))
    )
    monkeypatch.setattr(
        safety_scan,
        "run_llm_inference",
        AsyncMock(
            return_value='{"jailbreak_attempt": false, "violations": '
            '[{"category": "financial_advice", "severity": "high", "evidence": "put everything"}], '
            '"summary": "Gave investment advice."}'
        ),
    )
    out = await scan_run_safety(_run(), 1, _policy(output_categories=["financial_advice"]))
    assert out["status"] == "scanned" and out["model"] == "m1"
    assert out["violations"][0]["category"] == "financial_advice"
    assert out["categories_checked"] == ["financial_advice"]


@pytest.mark.asyncio
async def test_a_clean_call_is_recorded_as_scanned_and_clean(monkeypatch):
    monkeypatch.setattr(
        safety_scan, "create_qa_llm_service", AsyncMock(return_value=(object(), "m1"))
    )
    monkeypatch.setattr(
        safety_scan, "run_llm_inference",
        AsyncMock(return_value='{"jailbreak_attempt": false, "violations": [], "summary": "Fine."}'),
    )
    out = await scan_run_safety(_run(), 1, _policy(input_jailbreak=True))
    assert out["status"] == "scanned" and out["violations"] == []


@pytest.mark.asyncio
async def test_garbage_from_the_model_is_an_error_not_a_clean_bill(monkeypatch):
    """A scan that quietly found nothing would read as a safe call."""
    monkeypatch.setattr(
        safety_scan, "create_qa_llm_service", AsyncMock(return_value=(object(), "m1"))
    )
    monkeypatch.setattr(
        safety_scan, "run_llm_inference", AsyncMock(return_value="I am sorry, I cannot")
    )
    out = await scan_run_safety(_run(), 1, _policy(input_jailbreak=True))
    assert out["status"] == "error"


@pytest.mark.asyncio
async def test_no_llm_configured_is_recorded_as_skipped(monkeypatch):
    monkeypatch.setattr(safety_scan, "create_qa_llm_service", AsyncMock(return_value=None))
    out = await scan_run_safety(_run(), 1, _policy(input_jailbreak=True))
    assert out["status"] == "skipped" and out["reason"] == "no_llm_configured"


@pytest.mark.asyncio
async def test_a_crashing_provider_never_raises_out_of_the_scan(monkeypatch):
    monkeypatch.setattr(
        safety_scan, "create_qa_llm_service", AsyncMock(side_effect=RuntimeError("boom"))
    )
    out = await scan_run_safety(_run(), 1, _policy(input_jailbreak=True))
    assert out["status"] == "error"
