"""The handbook the editor inserts is the one the MCP tool shows, served over HTTP.

No database: the route reads a static registry.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import prompting_guide as routes
from api.services.voice_prompting_guide import get_topic
from api.services.voice_prompting_guide.topics.common_guidelines import (
    GLOBAL_NODE_STARTER,
)

USER = SimpleNamespace(id=1)

# The headings the product tells every builder to keep. The template catalog's
# drift test pins the same four; this one pins the source they are copied from.
HANDBOOK_HEADINGS = ("#goal", "## Rules", "## Speech Handling", "## Common Objections")


def test_starter_keeps_the_handbook_headings():
    for heading in HANDBOOK_HEADINGS:
        assert heading in GLOBAL_NODE_STARTER, heading


def test_starter_keeps_its_runtime_placeholders_literal():
    # An f-string would have collapsed these to single braces and the agent would
    # tell callers the time is "{current_time}".
    assert "{{current_time}}" in GLOBAL_NODE_STARTER
    assert "{{current_weekday}}" in GLOBAL_NODE_STARTER


def test_mcp_content_is_the_explanation_plus_the_starter_not_a_second_copy():
    topic = get_topic("common_guidelines")
    assert topic.content.endswith(GLOBAL_NODE_STARTER)
    assert topic.content.count("## Speech Handling") == 1
    assert topic.starter_template == GLOBAL_NODE_STARTER


def test_topic_route_returns_the_starter():
    out = asyncio.run(routes.get_prompting_guide_topic("common_guidelines", USER))
    assert out["starter_template"] == GLOBAL_NODE_STARTER
    assert out["content"].endswith(GLOBAL_NODE_STARTER)


def test_topics_without_a_starter_do_not_grow_the_key():
    other = next(t for t in routes.list_topic_index() if t["id"] != "common_guidelines")
    out = asyncio.run(routes.get_prompting_guide_topic(other["id"], USER))
    assert "starter_template" not in out


def test_index_lists_the_handbook():
    ids = [t["id"] for t in asyncio.run(routes.list_prompting_guide(USER))]
    assert "common_guidelines" in ids


def test_unknown_topic_is_a_404():
    with pytest.raises(HTTPException) as e:
        asyncio.run(routes.get_prompting_guide_topic("nope", USER))
    assert e.value.status_code == 404
