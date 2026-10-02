"""Hanging up on a phone menu, without ever delaying or hanging up on a person."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import StartFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from api.services.pipecat import ivr_detector as mod
from api.services.pipecat.ivr_detector import IVRDetectionProcessor, classify_is_ivr
from api.services.workflow.disposition_codes import (
    IVR_DETECTED_DISPOSITION,
    SYSTEM_DISPOSITION_CODES,
)

MENU = "Thank you for calling Acme. For billing, press 1. For support, press 2."
HUMAN = "Hello, this is Sarah speaking, how can I help you?"


def _frame(text):
    return TranscriptionFrame(text, "caller", "2026-10-02T00:00:00Z")


@pytest.fixture
def make(monkeypatch):
    """A processor with pipecat's frame plumbing stubbed, so this tests the decision."""
    monkeypatch.setattr(FrameProcessor, "process_frame", AsyncMock())

    def build(verdicts, *, clock=None, **kwargs):
        calls = []

        async def classify(_llm, text):
            calls.append(text)
            outcome = verdicts[text] if isinstance(verdicts, dict) else verdicts
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        proc = IVRDetectionProcessor(
            llm=object(), classify=classify, **({"clock": clock} if clock else {}), **kwargs
        )
        proc.push_frame = AsyncMock()
        fired = AsyncMock()
        proc.event_handler("on_ivr_detected")(fired)
        return proc, fired, calls

    return build


async def _feed(proc, *texts):
    await proc.process_frame(StartFrame(), FrameDirection.DOWNSTREAM)
    for t in texts:
        await proc.process_frame(_frame(t), FrameDirection.DOWNSTREAM)
    await asyncio.sleep(0.05)  # let the side checks finish


@pytest.mark.asyncio
async def test_a_menu_fires_the_handler_once(make):
    proc, fired, _ = make({MENU: True, "press 1": True})
    await _feed(proc, MENU, "press 1")
    assert fired.await_count == 1


@pytest.mark.asyncio
async def test_a_person_is_left_alone(make):
    proc, fired, _ = make({HUMAN: False})
    await _feed(proc, HUMAN)
    fired.assert_not_awaited()


@pytest.mark.asyncio
async def test_every_transcript_reaches_the_agent_untouched_and_unwaited(make):
    proc, _, _ = make(True)
    await _feed(proc, MENU, HUMAN)
    pushed = [c.args[0] for c in proc.push_frame.await_args_list if isinstance(c.args[0], TranscriptionFrame)]
    assert [f.text for f in pushed] == [MENU, HUMAN]


@pytest.mark.asyncio
async def test_only_the_first_few_transcripts_are_judged(make):
    proc, _, calls = make(False, max_checks=2)
    await _feed(proc, "a", "b", "c", "d")
    assert calls == ["a", "b"]


@pytest.mark.asyncio
async def test_a_person_who_speaks_late_is_never_classified(make):
    now = [100.0]
    proc, fired, calls = make(True, clock=lambda: now[0], window_secs=30.0)
    await proc.process_frame(StartFrame(), FrameDirection.DOWNSTREAM)
    now[0] += 45  # the window has closed
    await proc.process_frame(_frame(MENU), FrameDirection.DOWNSTREAM)
    await asyncio.sleep(0.05)
    assert calls == [] and fired.await_count == 0


@pytest.mark.asyncio
async def test_a_classifier_that_fails_never_ends_a_call(make):
    proc, fired, _ = make(RuntimeError("llm down"))
    await _feed(proc, MENU)
    fired.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_transcripts_cost_nothing(make):
    proc, _, calls = make(True)
    await _feed(proc, "")
    assert calls == []


@pytest.mark.asyncio
async def test_the_classifier_reply_is_parsed_not_trusted_loosely():
    class Llm:
        def __init__(self, reply):
            self.reply = reply

        async def run_inference(self, context, **kwargs):
            assert kwargs["system_instruction"] == mod.IVR_CLASSIFIER_PROMPT
            return self.reply

    assert await classify_is_ivr(Llm("<mode>ivr</mode>"), MENU) is True
    assert await classify_is_ivr(Llm("<MODE> IVR </MODE>"), MENU) is True
    assert await classify_is_ivr(Llm("<mode>conversation</mode>"), HUMAN) is False
    assert await classify_is_ivr(Llm(None), HUMAN) is False
    assert await classify_is_ivr(Llm("it might be an ivr"), HUMAN) is False


def test_the_disposition_exists_for_the_report_and_filter():
    assert IVR_DETECTED_DISPOSITION == "ivr_detected"
    assert "ivr_detected" in SYSTEM_DISPOSITION_CODES
