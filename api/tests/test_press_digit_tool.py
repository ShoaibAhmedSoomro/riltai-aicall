"""The Press Digit tool: valid keys only, fixed per tool, dispatched to its own handler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pipecat.frames.frames import OutputDTMFFrame, OutputDTMFUrgentFrame
from pydantic import ValidationError

from api.enums import ToolCategory
from api.schemas.tool import CreateToolRequest, PressDigitConfig
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.services.workflow.tools.custom_tool import tool_to_function_schema


def _tool(digits="1", urgent=False, name="Press one"):
    return SimpleNamespace(
        name=name,
        description="Press 1 to reach billing",
        category=ToolCategory.PRESS_DIGIT.value,
        tool_uuid="t-1",
        definition={"schema_version": 1, "type": "press_digit", "config": {"digits": digits, "urgent": urgent}},
    )


def _manager():
    engine = MagicMock()
    engine._transport_output.queue_frame = AsyncMock()
    return CustomToolManager(engine), engine


# -- schema -----------------------------------------------------------------------------


@pytest.mark.parametrize("digits", ["1", "0", "123#", "*9#", "  5  "])
def test_real_keys_are_accepted(digits):
    assert PressDigitConfig(digits=digits).digits == digits.strip()


@pytest.mark.parametrize("digits", ["", "   ", "12x", "one", "1 2", "1" * 33])
def test_anything_else_is_refused(digits):
    with pytest.raises(ValidationError):
        PressDigitConfig(digits=digits)


def test_a_tool_is_created_from_its_definition_and_category_must_match():
    ok = CreateToolRequest(
        name="Press one",
        definition={"type": "press_digit", "config": {"digits": "1"}},
    )
    assert ok.category == "press_digit"
    with pytest.raises(ValidationError):
        CreateToolRequest(
            name="x", category="http_api",
            definition={"type": "press_digit", "config": {"digits": "1"}},
        )


def test_the_model_is_given_no_parameters_so_it_cannot_choose_the_keys():
    schema = tool_to_function_schema(_tool("123#"))
    assert schema["function"]["parameters"].get("properties", {}) == {}
    assert "123#" not in str(schema)  # the keys are not even revealed to the prompt


# -- handler ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_handler_queues_the_configured_keys():
    manager, engine = _manager()
    handler, _ = manager._create_handler(_tool("12#"), "press_one")
    params = SimpleNamespace(arguments={}, result_callback=AsyncMock())

    await handler(params)

    (frame,), _ = engine._transport_output.queue_frame.await_args
    assert isinstance(frame, OutputDTMFFrame) and not isinstance(frame, OutputDTMFUrgentFrame)
    assert frame.to_string() == "12#"
    result, = params.result_callback.await_args.args
    assert result == {"status": "success", "pressed": "12#"}
    assert params.result_callback.await_args.kwargs["properties"].run_llm is True


@pytest.mark.asyncio
async def test_urgent_sends_the_immediate_frame():
    manager, engine = _manager()
    handler, _ = manager._create_handler(_tool("0", urgent=True), "press_zero")

    await handler(SimpleNamespace(arguments={}, result_callback=AsyncMock()))

    (frame,), _ = engine._transport_output.queue_frame.await_args
    assert isinstance(frame, OutputDTMFUrgentFrame)


@pytest.mark.asyncio
async def test_a_failure_is_reported_to_the_model_not_raised():
    manager, engine = _manager()
    engine._transport_output.queue_frame.side_effect = RuntimeError("transport gone")
    handler, _ = manager._create_handler(_tool("1"), "press_one")
    params = SimpleNamespace(arguments={}, result_callback=AsyncMock())

    await handler(params)

    assert params.result_callback.await_args.args[0]["status"] == "error"


def test_the_category_has_its_own_handler_and_is_not_mistaken_for_http():
    """The failure this guards: the dispatch falls through to the HTTP handler, which
    would try to call a URL that does not exist."""
    manager, _ = _manager()
    handler, timeout = manager._create_handler(_tool(), "press_one")
    assert handler.__name__ == "press_digit_handler"
