"""Caller keypad presses reach the conversation instead of being dropped.

Every telephony serializer in the tree already decodes carrier DTMF into an
``InputDTMFFrame``, and pipecat ships a ``DTMFAggregator`` that turns a run of
them into one ``TranscriptionFrame`` ("DTMF: 12#") and interrupts the bot on
the first digit. Neither was wired to the other, so the digits went nowhere: a
caller pressing "1 to confirm" was silently ignored, with no error, no log and
no transcript entry to show it had happened — indistinguishable from the caller
saying nothing at all.

These tests assert the WIRING, not the aggregator. The aggregator is pipecat's
and has its own tests; what was missing was the one line that puts it in the
pipeline, and this repo has a documented habit of capabilities that are present
in the tree and reachable by nobody. So the assertion is that both builders
include it, in a position where its output can still reach the LLM — which is
what was wrong, and what a refactor would quietly undo.
"""

import pytest
from pipecat.processors.frame_processor import FrameProcessor

from api.services.pipecat.pipeline_builder import (
    build_pipeline,
    build_realtime_pipeline,
)


class _Transport:
    """Only the two methods the builders call on a transport."""

    def __init__(self):
        self._in = FrameProcessor(name="transport_in")
        self._out = FrameProcessor(name="transport_out")

    def input(self):
        return self._in

    def output(self):
        return self._out


def _stub(name):
    """A real FrameProcessor: Pipeline links its processors on construction,
    so a duck-typed stand-in raises before the assertion is reached. Named, so
    position can be asserted rather than only presence."""
    return FrameProcessor(name=name)


def _names(pipeline):
    return [p.name for p in pipeline.processors]


def _kinds(pipeline):
    return [type(p).__name__ for p in pipeline.processors]


@pytest.mark.asyncio
async def test_the_voice_pipeline_consumes_caller_keypresses():
    pipeline = build_pipeline(
        transport=_Transport(),
        stt=_stub("stt"),
        audio_buffer=_stub("audio_buffer"),
        llm=_stub("llm"),
        tts=_stub("tts"),
        user_context_aggregator=_stub("user_ctx"),
        assistant_context_aggregator=_stub("assistant_ctx"),
        pipeline_engine_callback_processor=_stub("engine_cb"),
        pipeline_metrics_aggregator=_stub("metrics"),
    )
    assert "DTMFAggregator" in _kinds(pipeline)

    # Position is load-bearing, not cosmetic. The aggregator's output is a
    # TranscriptionFrame, and a TranscriptionFrame only reaches the LLM if it
    # is produced UPSTREAM of the user context aggregator. Placed below it,
    # the digits would be consumed by nothing all over again -- the same bug,
    # reintroduced by a plausible-looking reordering.
    names = _names(pipeline)
    dtmf = next(i for i, p in enumerate(pipeline.processors) if type(p).__name__ == "DTMFAggregator")
    assert dtmf < names.index("user_ctx")


@pytest.mark.asyncio
async def test_the_realtime_pipeline_consumes_them_too():
    """Speech-to-speech runs drop the caller's digits just as readily, and a
    change made only to the voice pipeline would skip every one of them."""
    pipeline = build_realtime_pipeline(
        transport=_Transport(),
        realtime_llm=_stub("realtime_llm"),
        audio_buffer=_stub("audio_buffer"),
        user_context_aggregator=_stub("user_ctx"),
        assistant_context_aggregator=_stub("assistant_ctx"),
        pipeline_engine_callback_processor=_stub("engine_cb"),
        pipeline_metrics_aggregator=_stub("metrics"),
    )
    assert "DTMFAggregator" in _kinds(pipeline)

    names = _names(pipeline)
    dtmf = next(i for i, p in enumerate(pipeline.processors) if type(p).__name__ == "DTMFAggregator")
    assert dtmf < names.index("user_ctx")
