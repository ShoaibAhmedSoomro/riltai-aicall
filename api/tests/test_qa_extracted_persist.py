"""What post-call analysis writes back onto the run, and what it must not clobber.

Two separate writers touch the same two keys, which is the whole risk here:

  `gathered_context["extracted_variables"]` is written DURING the call by the
  in-call extractor (pipecat_engine.py), and now again AFTER the call by QA
  field analysis. `update_workflow_run` merges gathered_context only one level
  deep, so writing {"extracted_variables": {...}} without reading first
  replaces everything the call itself extracted.

  `gathered_context["call_tags"]` is written at end-of-call by the pipeline
  (event_handlers.py) and now again by QA. Same one-level merge, same hazard.

These are the tests that fail if either read-before-write is dropped.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.tasks import run_integrations


def _run(gathered_context):
    return SimpleNamespace(
        id=7,
        campaign_id=None,
        gathered_context=gathered_context,
        annotations={},
        usage_info={},
        logs={},
        initial_context={},
        workflow=SimpleNamespace(id=1),
        definition=SimpleNamespace(
            id=1, workflow_json={"nodes": [{"id": "q1", "type": "qa"}]}
        ),
    )


async def _invoke(*, existing_context, qa_results):
    """Run the integrations task with everything but the write path stubbed.

    Returns the kwargs handed to update_workflow_run.
    """
    workflow_run = _run(existing_context)
    update = AsyncMock()

    db = SimpleNamespace(
        get_workflow_run_with_context=AsyncMock(return_value=(workflow_run, 42)),
        get_configuration_value=AsyncMock(return_value=None),
        ensure_public_access_token=AsyncMock(return_value="tok"),
        update_workflow_run=update,
    )

    with (
        patch.object(run_integrations, "db_client", db),
        patch.object(
            run_integrations, "_run_qa_nodes", new=AsyncMock(return_value=qa_results)
        ),
        patch.object(
            run_integrations, "run_completion_handlers", new=AsyncMock(return_value={})
        ),
        patch.object(run_integrations, "has_completion_handlers", return_value=False),
        patch.object(run_integrations, "set_current_org_id"),
        patch.object(run_integrations, "set_current_run_id"),
    ):
        await run_integrations.run_integrations_post_workflow_run(None, 7)

    assert update.await_count >= 1
    return update.await_args_list[0].kwargs


@pytest.mark.asyncio
async def test_post_call_extraction_does_not_erase_in_call_extraction():
    """The one-level merge makes a naive write destructive: the in-call
    extractor's values would vanish the moment a QA node extracted anything."""
    kwargs = await _invoke(
        existing_context={"extracted_variables": {"from_call": "kept"}},
        qa_results={
            "qa_q1": {
                "analysis": {"extracted": {"from_qa": "added"}},
                "node_results": {},
            }
        },
    )
    assert kwargs["gathered_context"]["extracted_variables"] == {
        "from_call": "kept",
        "from_qa": "added",
    }


@pytest.mark.asyncio
async def test_qa_tags_land_where_the_filter_actually_looks():
    """These used to go to annotations["tags"] under a comment saying "for
    top-level filtering", but every filter and the CSV read
    gathered_context.call_tags, so nothing could ever read them."""
    kwargs = await _invoke(
        existing_context={"call_tags": ["user_speech"]},
        qa_results={
            "qa_q1": {
                "node_results": {"n1": {"tags": ["angry"]}},
                "analysis": {"checks": [{"name": "disclosed", "passed": False}]},
            }
        },
    )
    assert kwargs["gathered_context"]["call_tags"] == [
        "angry",
        "check_failed:disclosed",
        "user_speech",
    ]


@pytest.mark.asyncio
async def test_a_check_with_no_verdict_does_not_tag_the_call_as_failed():
    """Omitted verdicts are dropped upstream; tagging on falsiness rather than
    `is False` would resurrect them as findings that nobody's model produced."""
    kwargs = await _invoke(
        existing_context={},
        qa_results={
            "qa_q1": {
                "node_results": {},
                "analysis": {
                    "checks": [
                        {"name": "passed_one", "passed": True},
                        {"name": "failed_one", "passed": False},
                        # No verdict at all. run_field_analysis omits these,
                        # but annotations written by an earlier version -- or
                        # by anything else that merges into this column --
                        # are not bound by that, and `not passed` would
                        # report this as a failed check nobody assessed.
                        {"name": "unassessed"},
                    ]
                },
            }
        },
    )
    assert kwargs["gathered_context"]["call_tags"] == ["check_failed:failed_one"]


@pytest.mark.asyncio
async def test_nothing_extracted_and_no_tags_writes_no_context_at_all():
    """A QA node that only writes prose must not touch gathered_context, or
    every run acquires an empty key that later code has to special-case."""
    kwargs = await _invoke(
        existing_context={"extracted_variables": {"from_call": "kept"}},
        qa_results={"qa_q1": {"node_results": {}, "analysis": {}}},
    )
    assert "gathered_context" not in kwargs
    assert kwargs["annotations"]["qa_q1"]["analysis"] == {}
