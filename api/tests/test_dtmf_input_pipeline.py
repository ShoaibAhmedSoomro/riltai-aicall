"""Caller keypresses: they open a turn, they reach the agent, and the agent can turn them off."""

from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import InputDTMFFrame, TextFrame
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.processors.aggregators.dtmf_aggregator import DTMFAggregator
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.turns.types import ProcessFrameResult

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.dtmf_turn_start import DTMFUserTurnStartStrategy
from api.services.pipecat.pipeline_builder import build_pipeline, build_realtime_pipeline
from api.services.pipecat.run_pipeline import _resolve_dtmf_input


@pytest.mark.asyncio
async def test_a_keypress_opens_a_user_turn():
    strategy = DTMFUserTurnStartStrategy()
    strategy.trigger_user_turn_started = AsyncMock()

    result = await strategy.process_frame(InputDTMFFrame(KeypadEntry.ONE))

    assert result == ProcessFrameResult.STOP
    strategy.trigger_user_turn_started.assert_awaited_once()


@pytest.mark.asyncio
async def test_anything_else_is_left_to_the_other_strategies():
    strategy = DTMFUserTurnStartStrategy()
    strategy.trigger_user_turn_started = AsyncMock()

    result = await strategy.process_frame(TextFrame("hello"))

    assert result == ProcessFrameResult.CONTINUE
    strategy.trigger_user_turn_started.assert_not_awaited()


class _Transport:
    def input(self):
        return FrameProcessor()

    def output(self):
        return FrameProcessor()


def _processors(pipeline):
    return pipeline.processors if hasattr(pipeline, "processors") else pipeline._processors


def _build(**kwargs):
    return build_pipeline(
        _Transport(), FrameProcessor(), FrameProcessor(), FrameProcessor(), FrameProcessor(),
        FrameProcessor(), FrameProcessor(), FrameProcessor(), FrameProcessor(), **kwargs,
    )


def _aggregators(pipeline):
    return [p for p in _processors(pipeline) if isinstance(p, DTMFAggregator)]


def test_the_keypad_is_on_by_default_as_it_has_always_been():
    (agg,) = _aggregators(_build())
    assert agg._idle_timeout == 2.0


def test_the_keypad_can_be_switched_off_per_agent():
    assert _aggregators(_build(dtmf_input_enabled=False)) == []


def test_the_idle_flush_is_adjustable():
    (agg,) = _aggregators(_build(dtmf_input_timeout_secs=4.5))
    assert agg._idle_timeout == 4.5


def test_the_aggregator_sits_right_after_the_transcriber():
    processors = _processors(_build())
    stt_index = 2  # pipeline source, transport.input(), stt
    assert isinstance(processors[stt_index + 1], DTMFAggregator)


def test_realtime_pipelines_honour_the_switch_too():
    def build(**kw):
        return build_realtime_pipeline(
            _Transport(), FrameProcessor(), FrameProcessor(), FrameProcessor(), FrameProcessor(),
            FrameProcessor(), FrameProcessor(), **kw,
        )

    assert len(_aggregators(build())) == 1
    assert _aggregators(build(dtmf_input_enabled=False)) == []


def test_the_dials_default_to_what_runs_today_and_are_bounded():
    cfg = WorkflowConfigurationDefaults()
    assert cfg.dtmf_input_enabled is True and cfg.dtmf_input_timeout_secs == 2.0
    for bad in (0.1, 99):
        with pytest.raises(Exception):
            WorkflowConfigurationDefaults(dtmf_input_timeout_secs=bad)


def test_a_malformed_stored_value_cannot_stop_a_call():
    assert _resolve_dtmf_input({}) == (True, 2.0)
    assert _resolve_dtmf_input({"dtmf_input_enabled": False}) == (False, 2.0)
    assert _resolve_dtmf_input({"dtmf_input_timeout_secs": "soon"}) == (True, 2.0)
    assert _resolve_dtmf_input({"dtmf_input_timeout_secs": 500}) == (True, 10.0)
    assert _resolve_dtmf_input({"dtmf_input_timeout_secs": 0}) == (True, 0.5)
