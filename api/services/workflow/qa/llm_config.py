"""QA LLM service creation and one-shot inference.

run_llm_inference lives here rather than in analysis.py because both the QA
review pass and the field-analysis pass need it, and analysis.py imports
fields.py -- keeping it there would make that a cycle.
"""

import asyncio
from typing import Any

from pipecat.processors.aggregators.llm_context import LLMContext

from api.errors.failure import (
    classify_exception,
    failure_metadata_for_processor,
    log_failure,
    mark_failure_reported,
)

from api.db.models import WorkflowRunModel
from api.services.configuration.ai_model_configuration import (
    get_effective_ai_model_configuration_for_workflow,
)
from api.services.managed_model_services import get_mps_correlation_id
from api.services.pipecat.service_factory import (
    create_llm_service_from_provider,
    create_llm_service_with_model_override,
)
from api.services.workflow.dto import QANodeData

QA_USAGE_CONTEXT = "qa_analysis"


async def create_qa_llm_service(
    qa_data: QANodeData, workflow_run: WorkflowRunModel | None
) -> tuple[Any, str] | None:
    """Create the LLM service used for QA analysis.

    If the QA node has its own LLM configuration (qa_use_workflow_llm=False),
    create the service from those explicit settings. Otherwise, resolve the
    workflow/org configuration and delegate service creation to the central factory.
    """
    correlation_id = get_mps_correlation_id(
        getattr(workflow_run, "initial_context", None)
    )

    if not qa_data.qa_use_workflow_llm:
        provider = qa_data.qa_provider or "openai"
        model = qa_data.qa_model or "default"
        api_key = qa_data.qa_api_key
        if not api_key:
            return None

        kwargs = {}
        if provider == "azure":
            kwargs["endpoint"] = qa_data.qa_endpoint or ""
        # Custom OpenAI-compatible endpoints are supported only when QA reuses
        # the workflow LLM; the QA-specific endpoint field is Azure-only.
        llm = create_llm_service_from_provider(
            provider,
            model,
            api_key,
            correlation_id=correlation_id,
            usage_context=QA_USAGE_CONTEXT,
            **kwargs,
        )
        return llm, model

    if workflow_run is None or workflow_run.workflow is None:
        return None

    if workflow_run.definition:
        workflow_configurations = workflow_run.definition.workflow_configurations or {}
    else:
        workflow_configurations = workflow_run.workflow.workflow_configurations or {}

    user_configuration = await get_effective_ai_model_configuration_for_workflow(
        organization_id=workflow_run.workflow.organization_id,
        workflow_configurations=workflow_configurations,
    )
    if user_configuration.llm is None:
        return None

    model_override = (
        qa_data.qa_model if qa_data.qa_model and qa_data.qa_model != "default" else None
    )
    model = model_override or user_configuration.llm.model
    llm = create_llm_service_with_model_override(
        user_configuration,
        model_override,
        correlation_id=correlation_id,
        usage_context=QA_USAGE_CONTEXT,
    )
    return llm, model


_QA_LLM_ATTEMPTS = 3


async def run_llm_inference(
    llm,
    messages: list[dict],
    system_prompt: str,
    *,
    workflow_run_id: int | None = None,
    failure_log_level: str = "ERROR",
) -> str | None:
    """Run a one-shot LLM inference using the pipecat service.

    Transient provider failures (capacity 503s, timeouts) are retried with
    backoff — QA runs post-call, so latency is cheap and a retry usually
    erases the failure entirely. The final failure is classified and reported
    here, once, so callers only note how they degraded.
    """
    context = LLMContext()
    context.set_messages(messages)
    for attempt in range(1, _QA_LLM_ATTEMPTS + 1):
        try:
            return await llm.run_inference(context, system_instruction=system_prompt)
        except Exception as exc:
            metadata = failure_metadata_for_processor(llm)
            failure = classify_exception(
                exc,
                source=metadata.source,
                provider=metadata.provider,
                error_owner=metadata.error_owner,
            )
            if failure.retryable and attempt < _QA_LLM_ATTEMPTS:
                await asyncio.sleep(2**attempt)
                continue
            log_failure(
                failure,
                level=failure_log_level,
                workflow_run_id=workflow_run_id,
                qa_attempts=attempt,
            )
            mark_failure_reported(exc)
            raise
