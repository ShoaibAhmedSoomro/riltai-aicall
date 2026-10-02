"""The starter templates must be publishable, organization-neutral, and on the handbook.

Pure: reads the JSON files, no database. A template that fails here is one a user
would clone and then be unable to publish.
"""

import json

import pytest

from api.services.voice_prompting_guide.topics.common_guideliines import (
    GLOBAL_NODE_STARTER,
)
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.template_catalog import (
    CATALOG_DIR,
    CATEGORIES,
    ORG_SCOPED_FIELDS,
    load_catalog,
)
from api.services.workflow.workflow_graph import (
    WorkflowGraph,
    validate_unique_transition_tool_names,
)

HANDBOOK_HEADINGS = ("## Rules", "## Speech Handling", "## Common Objections")

FILES = sorted(CATALOG_DIR.glob("*.json"))
ENTRIES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in FILES}


def test_there_is_one_template_per_category():
    assert sorted(ENTRIES) == sorted(CATEGORIES)


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_passes_the_same_gate_publish_uses(slug):
    # ReactFlowDTO then WorkflowGraph: what _validate_workflow_definition runs.
    WorkflowGraph(ReactFlowDTO.model_validate(ENTRIES[slug]["definition"]))


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_file_name_slug_and_category_agree(slug):
    assert ENTRIES[slug]["slug"] == slug
    assert ENTRIES[slug]["category"] in CATEGORIES


def test_slugs_and_names_are_unique():
    entries = load_catalog()
    assert len({e.slug for e in entries}) == len(entries)
    assert len({e.name for e in entries}) == len(entries)


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_nothing_organization_scoped(slug):
    for node in ENTRIES[slug]["definition"]["nodes"]:
        for field in ORG_SCOPED_FIELDS:
            assert not node["data"].get(field), f"{slug}/{node['id']}.{field}"


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_global_node_is_the_handbook(slug):
    """The drift guard between the catalog and common_guideliines.py."""
    globals_ = [n for n in ENTRIES[slug]["definition"]["nodes"] if n["type"] == "globalNode"]
    assert len(globals_) == 1
    prompt = globals_[0]["data"]["prompt"]
    for heading in HANDBOOK_HEADINGS:
        assert heading in prompt, heading
    # Only business details differ from the starter: every line that is not about
    # the persona, the example amounts or the objection replies is verbatim.
    verbatim = [
        line for line in GLOBAL_NODE_STARTER.splitlines()
        if line.startswith(("## ", "Keep responses short", "End almost every turn", "Accept variations"))
    ]
    assert verbatim and all(line in prompt for line in verbatim)


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_a_call_can_always_end(slug):
    types = [n["type"] for n in ENTRIES[slug]["definition"]["nodes"]]
    assert types.count("startCall") == 1
    assert types.count("endCall") >= 1


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_transition_names_do_not_collide(slug):
    edges = ENTRIES[slug]["definition"]["edges"]
    assert not validate_unique_transition_tool_names(
        [(e["id"], e["source"], e["data"]["label"]) for e in edges]
    )


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_no_placeholder_text_left_in_prompts(slug):
    # Blanks from the handbook ("just here to ....") must all have been filled.
    for node in ENTRIES[slug]["definition"]["nodes"]:
        assert "...." not in node["data"]["prompt"], node["id"]
        assert "Acme" not in node["data"]["prompt"], node["id"]
