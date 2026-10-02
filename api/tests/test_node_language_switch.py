"""A step can speak and listen in another language, switching once per change."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pipecat.frames.frames import STTUpdateSettingsFrame, TTSSpeakFrame, TTSUpdateSettingsFrame
from pipecat.transcriptions.language import Language

from api.services.configuration.options.deepgram import DEEPGRAM_LANGUAGES
from api.services.workflow.dto import AgentNodeData, EndCallNodeData, ReactFlowDTO
from api.services.workflow.node_language import language_to_apply, to_pipecat_language
from api.services.workflow.node_specs import get_spec
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.workflow_graph import WorkflowGraph


# -- pure ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [("ar", Language.AR), ("fr", Language.FR), ("ar-AE", Language.AR_AE), ("en-US", Language.EN_US)],
)
def test_picker_codes_map_to_pipecat_languages(code, expected):
    assert to_pipecat_language(code) is expected


@pytest.mark.parametrize("code", [None, "", "multi", "xx", "zz-ZZ"])
def test_codes_that_are_not_a_speakable_language_map_to_nothing(code):
    assert to_pipecat_language(code) is None


def test_a_regional_code_pipecat_lacks_falls_back_to_the_language():
    assert to_pipecat_language("en-ZZ") is Language.EN


def test_switch_only_when_the_target_differs_from_what_is_active():
    assert language_to_apply("ar", "en", "en") == "ar"
    assert language_to_apply("ar", "en", "ar") is None  # already there: a reconnect costs audio
    assert language_to_apply(None, "en", "ar") == "en"  # a step with none returns to the agent's own
    assert language_to_apply(None, "en", "en") is None
    assert language_to_apply(None, None, "ar") is None  # agent language unknown: don't guess


# -- the engine -------------------------------------------------------------------------------------


def _engine(*, enabled=True, base="en"):
    engine = SimpleNamespace(task=SimpleNamespace(queue_frame=AsyncMock()))
    PipecatEngine.configure_language_switching(engine, enabled=enabled, base_language=base)
    return engine


def _node(language, name="Step"):
    return SimpleNamespace(language=language, name=name)


async def _apply(engine, node):
    await PipecatEngine._apply_node_language(engine, node)


def _frames(engine):
    return [c.args[0] for c in engine.task.queue_frame.await_args_list]


@pytest.mark.asyncio
async def test_a_language_change_queues_exactly_the_transcriber_and_voice_frames():
    engine = _engine()
    await _apply(engine, _node("ar"))

    stt, tts = _frames(engine)
    assert isinstance(stt, STTUpdateSettingsFrame) and stt.delta.language is Language.AR
    assert isinstance(tts, TTSUpdateSettingsFrame) and tts.delta.language is Language.AR


@pytest.mark.asyncio
async def test_entering_another_step_in_the_same_language_queues_nothing():
    engine = _engine()
    await _apply(engine, _node("ar"))
    engine.task.queue_frame.reset_mock()

    await _apply(engine, _node("ar"))

    engine.task.queue_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_step_with_no_language_returns_the_call_to_the_agents_own():
    engine = _engine(base="en")
    await _apply(engine, _node("ar"))
    engine.task.queue_frame.reset_mock()

    await _apply(engine, _node(None))

    stt, tts = _frames(engine)
    assert stt.delta.language is Language.EN and tts.delta.language is Language.EN


@pytest.mark.asyncio
async def test_an_agent_that_never_uses_it_pays_nothing():
    engine = _engine()
    await _apply(engine, _node(None))
    engine.task.queue_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_it_does_nothing_where_switching_is_off():
    engine = _engine(enabled=False)
    await _apply(engine, _node("ar"))
    engine.task.queue_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unspeakable_language_is_ignored_and_not_remembered():
    engine = _engine()
    await _apply(engine, _node("multi"))
    engine.task.queue_frame.assert_not_awaited()
    await _apply(engine, _node("ar"))  # still switches afterwards
    assert len(_frames(engine)) == 2


@pytest.mark.asyncio
async def test_the_language_is_set_before_the_transition_line_is_queued():
    """The transition line must be spoken in the language of the step being entered."""
    order = []
    engine = SimpleNamespace(
        task=SimpleNamespace(queue_frame=AsyncMock(side_effect=lambda f: order.append(type(f).__name__))),
        workflow=SimpleNamespace(nodes={"n2": _node("ar")}),
        _current_node=_node(None),
        _perform_variable_extraction_if_needed=AsyncMock(),
        _run_transition_variable_extraction_in_background=False,
        set_node=AsyncMock(),
    )
    engine._apply_node_language = lambda node: PipecatEngine._apply_node_language(engine, node)
    PipecatEngine.configure_language_switching(engine, enabled=True, base_language="en")

    transition = await PipecatEngine._create_transition_func(
        engine, "go", "n2", transition_speech="Switching now", transition_speech_type="text"
    )
    await transition(SimpleNamespace(arguments={}, result_callback=AsyncMock()))

    assert order == ["STTUpdateSettingsFrame", "TTSUpdateSettingsFrame", "TTSSpeakFrame"]


# -- the node data and spec ---------------------------------------------------------------------------


def test_the_field_is_on_agent_and_end_nodes_with_every_picker_language_offered():
    for spec_name in ("agentNode", "endCall"):
        prop = next(p for p in get_spec(spec_name).properties if p.name == "language")
        assert [o.value for o in prop.options] == list(DEEPGRAM_LANGUAGES)
    assert "language" in AgentNodeData.model_fields and "language" in EndCallNodeData.model_fields


def test_start_and_global_nodes_do_not_offer_it():
    for spec_name in ("startCall", "globalNode"):
        assert all(p.name != "language" for p in get_spec(spec_name).properties)


def test_a_graph_node_exposes_its_language_and_older_graphs_have_none():
    def graph(data_extra):
        return WorkflowGraph(
            ReactFlowDTO.model_validate(
                {
                    "nodes": [
                        {"id": "s", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "S", "prompt": "hi"}},
                        {"id": "a", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"name": "A", "prompt": "x", **data_extra}},
                        {"id": "e", "type": "endCall", "position": {"x": 0, "y": 0}, "data": {"name": "E", "prompt": "bye"}},
                    ],
                    "edges": [
                        {"id": "1", "source": "s", "target": "a", "data": {"label": "go", "condition": "always"}},
                        {"id": "2", "source": "a", "target": "e", "data": {"label": "done", "condition": "always"}},
                    ],
                }
            )
        )

    assert graph({"language": "ar"}).nodes["a"].language == "ar"
    assert graph({}).nodes["a"].language is None
    assert graph({"language": ""}).nodes["a"].language is None
