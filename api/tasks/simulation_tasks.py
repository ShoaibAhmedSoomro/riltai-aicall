"""Background entry for a simulated text chat (see services/workflow/simulation_runner)."""

from loguru import logger
from pipecat.utils.run_context import set_current_org_id, set_current_run_id

from api.db import db_client
from api.services.configuration.ai_model_configuration import (
    get_effective_ai_model_configuration_for_workflow,
)
from api.services.pipecat.service_factory import create_llm_service
from api.services.workflow.simulation_runner import run_simulated_text_chat


async def simulate_text_chat(
    _ctx,
    workflow_id: int,
    run_id: int,
    organization_id: int,
    persona_prompt: str,
    max_turns: int,
) -> None:
    """Play a persona against the agent until it ends, then end the session.

    The persona is voiced by the agent's own LLM (its model and key), so a simulation
    needs no extra provider setup.
    """
    set_current_run_id(run_id)
    set_current_org_id(organization_id)
    try:
        text_session = await db_client.get_workflow_run_text_session(
            run_id, organization_id=organization_id
        )
        run_configs = (
            (text_session.workflow_run.definition.workflow_configurations or {})
            if text_session and text_session.workflow_run.definition
            else {}
        )
        user_config = await get_effective_ai_model_configuration_for_workflow(
            organization_id=organization_id, workflow_configurations=run_configs
        )
        llm = create_llm_service(user_config, usage_context="simulation")
    except Exception as e:
        # Without a persona model there is nothing to run; close the session so it
        # does not sit open until the inactivity sweeper finds it.
        logger.error(f"Simulation of run {run_id} could not start: {e}")
        from api.services.workflow.simulation_runner import _end_session

        await _end_session(run_id, organization_id)
        return

    await run_simulated_text_chat(
        workflow_id=workflow_id,
        run_id=run_id,
        organization_id=organization_id,
        persona_prompt=persona_prompt,
        max_turns=max_turns,
        llm=llm,
    )
