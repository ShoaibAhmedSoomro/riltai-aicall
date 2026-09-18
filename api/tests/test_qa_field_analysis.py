"""Post-call field extraction and checks — the parts that would silently lie.

No call has ever completed on this deployment, so none of this can be exercised
against a real transcript. Everything here is fixture-driven and runs today.

What is actually being pinned:

  1. A declared type that is never enforced is decoration. Until now the
     `type` on an extraction variable existed only as text inside the prompt
     (pipecat_engine_variable_extractor.py builds "- name (type): hint" and
     stores whatever JSON comes back), so a field declared `number` could be
     stored as "forty-two". These tests fail if coercion stops happening.

  2. Absent must not become a value. A field the model omitted, or returned
     unusably, has to disappear -- not arrive as "", 0 or None -- because a
     zero in a numeric column reads as a measurement and an empty string reads
     as an answered question.

  3. A legitimate False or 0 must survive. This is the mirror of (2) and the
     easy thing to break while fixing it: `if coerced` drops both.
"""

import json

import pytest

from api.services.workflow.dto import (
    ExtractionVariableDTO,
    QACheckDTO,
    QANodeData,
    VariableType,
)
from api.services.workflow.qa.fields import run_field_analysis

TRANSCRIPT = "Agent: How many tickets?\nUser: Two, and yes I consent to recording."


class _StubLLM:
    """Stands in for a pipecat LLM service. Counts calls so a per-node loop
    creeping back in is visible."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def run_inference(self, context, system_instruction=None):
        self.calls += 1
        self.last_context = context
        self.last_system = system_instruction
        if isinstance(self._payload, Exception):
            raise self._payload
        return (
            self._payload
            if isinstance(self._payload, str)
            else json.dumps(self._payload)
        )


def _node(fields=None, checks=None) -> QANodeData:
    return QANodeData(
        name="QA",
        qa_system_prompt="review",
        qa_extraction_fields=fields,
        qa_checks=checks,
    )


def _field(name, type_, prompt="hint"):
    return ExtractionVariableDTO(name=name, type=type_, prompt=prompt)


@pytest.mark.asyncio
async def test_nothing_configured_costs_nothing():
    """The overwhelmingly common case: a QA node with no fields or checks must
    not spend an LLM call on an empty question."""
    llm = _StubLLM({})
    assert await run_field_analysis(_node(), 1, llm, TRANSCRIPT) == {}
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_one_inference_for_the_whole_call_not_one_per_field():
    llm = _StubLLM({"extracted": {"a": "x", "b": "y", "c": "z"}})
    await run_field_analysis(
        _node(
            fields=[
                _field("a", VariableType.string),
                _field("b", VariableType.string),
                _field("c", VariableType.string),
            ]
        ),
        1,
        llm,
        TRANSCRIPT,
    )
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_values_are_coerced_to_the_declared_type():
    """The declared type had no runtime effect anywhere before this."""
    llm = _StubLLM(
        {
            "extracted": {
                "tickets": "2",  # declared number, arrives as a string
                "consented": "yes",  # declared boolean, arrives as a word
                "name": 42,  # declared string, arrives as a number
            }
        }
    )
    result = await run_field_analysis(
        _node(
            fields=[
                _field("tickets", VariableType.number),
                _field("consented", VariableType.boolean),
                _field("name", VariableType.string),
            ]
        ),
        1,
        llm,
        TRANSCRIPT,
    )
    assert result["extracted"] == {"tickets": 2.0, "consented": True, "name": "42"}


@pytest.mark.asyncio
async def test_a_value_that_will_not_coerce_is_dropped_not_defaulted():
    """Storing 0 for "forty-two" would put a number in a numeric column that
    nobody said, and it would survive into the CSV and any future average."""
    llm = _StubLLM({"extracted": {"tickets": "forty-two", "maybe": "perhaps"}})
    result = await run_field_analysis(
        _node(
            fields=[
                _field("tickets", VariableType.number),
                _field("maybe", VariableType.boolean),
            ]
        ),
        1,
        llm,
        TRANSCRIPT,
    )
    assert result["extracted"] == {}
    # But the reader still learns what was asked, so the UI can say
    # "not analysed" per field rather than showing nothing at all.
    assert [f["name"] for f in result["fields"]] == ["tickets", "maybe"]


@pytest.mark.asyncio
async def test_a_field_the_model_omitted_is_omitted_here_too():
    llm = _StubLLM({"extracted": {"present": "here"}})
    result = await run_field_analysis(
        _node(
            fields=[
                _field("present", VariableType.string),
                _field("absent", VariableType.string),
            ]
        ),
        1,
        llm,
        TRANSCRIPT,
    )
    assert result["extracted"] == {"present": "here"}
    assert "absent" not in result["extracted"]


@pytest.mark.asyncio
async def test_a_real_false_and_a_real_zero_survive():
    """The mirror of the drop rule, and the easy thing to break while writing
    it: `if value:` discards both of these, which are real answers."""
    llm = _StubLLM({"extracted": {"consented": False, "tickets": 0}})
    result = await run_field_analysis(
        _node(
            fields=[
                _field("consented", VariableType.boolean),
                _field("tickets", VariableType.number),
            ]
        ),
        1,
        llm,
        TRANSCRIPT,
    )
    assert result["extracted"] == {"consented": False, "tickets": 0}


@pytest.mark.asyncio
async def test_an_empty_string_is_not_an_answer():
    llm = _StubLLM({"extracted": {"name": "   "}})
    result = await run_field_analysis(
        _node(fields=[_field("name", VariableType.string)]), 1, llm, TRANSCRIPT
    )
    assert result["extracted"] == {}


@pytest.mark.asyncio
async def test_a_check_with_no_usable_verdict_is_omitted_not_failed():
    """Recording a missing verdict as a failure invents a problem, and it would
    tag the call check_failed:<name> and surface it as a real finding."""
    llm = _StubLLM(
        {
            "checks": {
                "greeted": {"passed": True, "reason": "said hello"},
                "disclosed": {"passed": "probably"},  # not a bool
                # "closed" absent entirely
            }
        }
    )
    result = await run_field_analysis(
        _node(
            checks=[
                QACheckDTO(name="greeted", criterion="agent greeted the caller"),
                QACheckDTO(name="disclosed", criterion="agent disclosed recording"),
                QACheckDTO(name="closed", criterion="agent closed politely"),
            ]
        ),
        1,
        llm,
        TRANSCRIPT,
    )
    assert [c["name"] for c in result["checks"]] == ["greeted"]
    # All three are still reported as configured, so the UI can distinguish
    # "passed", "failed" and "not analysed".
    assert result["checks_configured"] == ["greeted", "disclosed", "closed"]


@pytest.mark.asyncio
async def test_a_score_only_appears_when_it_was_asked_for_and_is_in_range():
    llm = _StubLLM(
        {
            "checks": {
                "scored": {"passed": True, "score": 87},
                "unscored": {"passed": True, "score": 91},
                "silly": {"passed": True, "score": 900},
            }
        }
    )
    result = await run_field_analysis(
        _node(
            checks=[
                QACheckDTO(name="scored", criterion="c", scored=True),
                QACheckDTO(name="unscored", criterion="c", scored=False),
                QACheckDTO(name="silly", criterion="c", scored=True),
            ]
        ),
        1,
        llm,
        TRANSCRIPT,
    )
    by_name = {c["name"]: c for c in result["checks"]}
    assert by_name["scored"]["score"] == 87
    # Not requested, so not recorded even though the model volunteered one.
    assert by_name["unscored"]["score"] is None
    # Out of range is dropped rather than clamped to 100, which would be a
    # number nobody produced.
    assert by_name["silly"]["score"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        "[1, 2, 3]",  # parse_llm_json returns a list for a top-level array
        '{"extracted": "a string, not an object"}',
    ],
)
async def test_unusable_model_output_degrades_to_an_error_not_a_crash(payload):
    result = await run_field_analysis(
        _node(fields=[_field("a", VariableType.string)]),
        1,
        _StubLLM(payload),
        TRANSCRIPT,
    )
    assert result.get("extracted", {}) == {}
    assert result["fields"] == [{"name": "a", "type": "string"}]


@pytest.mark.asyncio
async def test_an_llm_failure_is_reported_not_raised():
    """This runs inside the post-call job; raising here would take down the
    webhook and integration steps that follow it."""
    result = await run_field_analysis(
        _node(fields=[_field("a", VariableType.string)]),
        1,
        _StubLLM(RuntimeError("provider exploded")),
        TRANSCRIPT,
    )
    assert "error" in result
    assert result["checks_configured"] == []


@pytest.mark.asyncio
async def test_an_empty_transcript_is_not_analysed():
    llm = _StubLLM({"extracted": {"a": "x"}})
    result = await run_field_analysis(
        _node(fields=[_field("a", VariableType.string)]), 1, llm, ""
    )
    assert result == {"error": "empty_transcript"}
    assert llm.calls == 0
