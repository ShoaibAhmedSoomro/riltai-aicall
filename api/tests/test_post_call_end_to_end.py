"""The post-call chain, run for real against a database.

Everything else covering this work is fixture-driven: it stubs the task, the
DB client, or both. That leaves the join between the pieces untested, and the
join is where this kind of change actually breaks — a key written under the
wrong name, a merge that clobbers, a tag that lands somewhere no query reads.

No call has ever completed on this deployment, so a real transcript is not
available. This is the closest substitute: a genuine workflow_run row carrying
genuine realtime_feedback_events, the real `run_integrations_post_workflow_run`
task, the real DB client, and only the LLM replaced. It ends by querying the
run back through the real filter stack, because "the tag is filterable" is a
claim about a SQL query, not about a dict.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.db.models import (
    OrganizationModel,
    UserModel,
    WorkflowDefinitionModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.enums import WorkflowRunMode
from api.tasks import run_integrations

# What the model is pretending to return. Deliberately awkward: `ticket_count`
# arrives as a STRING for a field declared `number`, which is exactly what the
# unenforced declared type used to let through into storage.
LLM_RESPONSE = """{
  "extracted": {"caller_email": "sam@example.com", "ticket_count": "2"},
  "checks": {
    "disclosed_recording": {"passed": false, "reason": "never mentioned it"},
    "greeted_caller": {"passed": true, "reason": "said good morning"}
  }
}"""

QA_NODE = {
    "id": "qa1",
    "type": "qa",
    "position": {"x": 0, "y": 0},
    "data": {
        "name": "Compliance",
        "qa_enabled": True,
        "qa_system_prompt": "Review the call and return JSON.",
        "qa_min_call_duration": 0,
        "qa_extraction_fields": [
            {"name": "caller_email", "type": "string", "prompt": "their email"},
            {"name": "ticket_count", "type": "number", "prompt": "how many tickets"},
        ],
        "qa_checks": [
            {
                "name": "disclosed_recording",
                "criterion": "the agent said the call is recorded",
                "scored": False,
            },
            {
                "name": "greeted_caller",
                "criterion": "the agent greeted the caller",
                "scored": False,
            },
        ],
    },
}


def _events():
    """A transcript in the shape build_conversation_structure consumes.

    No node_id on any event, so this takes the WHOLE-CALL FALLBACK path --
    which is the path every text-chat run takes, and the one a change made only
    to the per-node loop would silently skip.
    """
    start = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
    return [
        {
            "type": "rtf-bot-text",
            "timestamp": start.isoformat(),
            "payload": {"text": "Good morning, how can I help?"},
        },
        {
            "type": "rtf-user-transcription",
            "timestamp": (start + timedelta(seconds=4)).isoformat(),
            "payload": {
                "text": "I need two tickets, I'm sam@example.com",
                "final": True,
            },
        },
    ]


async def _seed(async_session):
    suffix = datetime.now(UTC).microsecond
    org = OrganizationModel(provider_id=f"e2e-org-{suffix}")
    async_session.add(org)
    await async_session.flush()

    user = UserModel(provider_id=f"e2e-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()

    workflow = WorkflowModel(name="e2e", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()

    definition = WorkflowDefinitionModel(
        workflow_id=workflow.id,
        workflow_json={"nodes": [QA_NODE], "edges": []},
        is_current=True,
    )
    async_session.add(definition)
    await async_session.flush()

    run = WorkflowRunModel(
        workflow_id=workflow.id,
        definition_id=definition.id,
        name="e2e-run",
        mode=WorkflowRunMode.TWILIO.value,
        is_completed=True,
        logs={"realtime_feedback_events": _events()},
        usage_info={"call_duration_seconds": 42},
        # The in-call extractor already wrote one. Post-call analysis must add
        # to it, not replace it.
        gathered_context={
            "extracted_variables": {"from_in_call": "already here"},
            "call_tags": ["user_speech"],
        },
    )
    async_session.add(run)
    await async_session.flush()
    return org, run


@pytest.mark.asyncio
async def test_the_whole_post_call_chain_lands_in_the_database(
    db_session, async_session
):
    org, run = await _seed(async_session)

    llm = SimpleNamespace(run_inference=AsyncMock(return_value=LLM_RESPONSE))

    # Only the LLM is replaced. The task, the DB client and every query below
    # are the real ones.
    with patch(
        "api.services.workflow.qa.analysis.create_qa_llm_service",
        new=AsyncMock(return_value=(llm, "test-model")),
    ):
        await run_integrations.run_integrations_post_workflow_run(None, run.id)

    await async_session.refresh(run)

    # 1. Extraction landed, coerced, and did NOT erase the in-call value.
    extracted = run.gathered_context["extracted_variables"]
    assert extracted["from_in_call"] == "already here"
    assert extracted["caller_email"] == "sam@example.com"
    # Declared `number`, returned as the string "2".
    assert extracted["ticket_count"] == 2.0

    # 2. Verdicts landed in the annotations wrapper.
    analysis = run.annotations["qa_qa1"]["analysis"]
    verdicts = {c["name"]: c["passed"] for c in analysis["checks"]}
    assert verdicts == {"disclosed_recording": False, "greeted_caller": True}

    # 3. The failed check tagged the call, unioned with the pipeline's tag.
    assert "user_speech" in run.gathered_context["call_tags"]
    assert "check_failed:disclosed_recording" in run.gathered_context["call_tags"]
    assert "check_failed:greeted_caller" not in run.gathered_context["call_tags"]

    # 4. THE ONE THAT MATTERS: the tag is reachable by the real filter. Every
    #    other assertion here is about a dict; this is about a SQL query, and
    #    it is the claim the old annotations["tags"] destination silently
    #    failed for years.
    runs, total, _, _ = await db_session.get_usage_history(
        org.id,
        filters=[
            {
                "attribute": "callTags",
                "type": "tags",
                "value": {"codes": ["check_failed:disclosed_recording"]},
            }
        ],
    )
    assert total == 1
    assert runs[0]["id"] == run.id

    # And a tag nobody emitted finds nothing, so the filter is not a no-op.
    _, none_total, _, _ = await db_session.get_usage_history(
        org.id,
        filters=[
            {
                "attribute": "callTags",
                "type": "tags",
                "value": {"codes": ["check_failed:greeted_caller"]},
            }
        ],
    )
    assert none_total == 0


@pytest.mark.asyncio
async def test_one_llm_call_for_the_whole_analysis(db_session, async_session):
    """The QA review pass and the field pass are separate inferences, but the
    field pass must not become one call per field or per node."""
    _, run = await _seed(async_session)
    llm = SimpleNamespace(run_inference=AsyncMock(return_value=LLM_RESPONSE))

    with patch(
        "api.services.workflow.qa.analysis.create_qa_llm_service",
        new=AsyncMock(return_value=(llm, "test-model")),
    ):
        await run_integrations.run_integrations_post_workflow_run(None, run.id)

    # One whole-call review + one field analysis. Four configured items, two
    # calls: the count must not scale with the configuration.
    assert llm.run_inference.await_count == 2
