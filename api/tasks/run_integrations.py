"""Execute integrations (QA analysis, webhooks) after workflow run completion."""

import random
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from loguru import logger
from pipecat.utils.enums import EndTaskReason
from pipecat.utils.run_context import set_current_org_id, set_current_run_id
from pydantic import ValidationError

from api.constants import BACKEND_API_ENDPOINT, DEFAULT_WEBHOOK_DELIVERY_CONFIG
from api.db import db_client
from api.db.models import WorkflowRunModel
from api.enums import OrganizationConfigurationKey
from api.errors.failure import (
    ErrorSource,
    ErrorType,
    RiltFailure,
    classify_exception,
    log_failure,
)
from api.services.integrations import (
    IntegrationCompletionContext,
    has_completion_handlers,
    run_completion_handlers,
)
from api.services.pipecat.tracing_config import register_org_langfuse_credentials
from api.services.workflow.dto import (
    QANodeData,
    QARFNode,
    WebhookNodeData,
    WebhookRFNode,
)
from api.services.workflow.qa import run_per_node_qa_analysis
from api.tasks.function_names import FunctionNames
from api.utils.recording_artifacts import get_recording_storage_key
from api.utils.template_renderer import render_template


def _should_skip_qa(
    qa_data: QANodeData,
    workflow_run: WorkflowRunModel,
) -> str | None:
    """Check whether QA analysis should be skipped for this call.

    Returns a reason string if the call should be skipped, or None if it should proceed.
    """
    usage_info = workflow_run.usage_info or {}
    call_duration = usage_info.get("call_duration_seconds")
    if call_duration is not None and call_duration < qa_data.qa_min_call_duration:
        return (
            f"call duration ({call_duration:.1f}s) below minimum "
            f"({qa_data.qa_min_call_duration}s)"
        )

    if not qa_data.qa_voicemail_calls:
        gathered_context = workflow_run.gathered_context or {}
        call_disposition = gathered_context.get("call_disposition", "")
        if call_disposition == EndTaskReason.VOICEMAIL_DETECTED.value:
            return "voicemail call and QA voicemail calls is disabled"

    if qa_data.qa_sample_rate < 100:
        roll = random.randint(1, 100)
        if roll > qa_data.qa_sample_rate:
            return (
                f"excluded by sampling ({qa_data.qa_sample_rate}% sample rate, "
                f"rolled {roll})"
            )

    return None


async def _run_qa_nodes(
    qa_nodes: list[dict],
    workflow_run: WorkflowRunModel,
    workflow_run_id: int,
    workflow_definition: dict,
    definition_id: int | None,
) -> Dict[str, Any]:
    """Run QA analysis for each enabled QA node and aggregate results.

    Returns:
        Dict keyed by node ID with QA analysis results.
    """
    results: Dict[str, Any] = {}

    for node in qa_nodes:
        node_id = node.get("id", "unknown")
        try:
            qa_node = QARFNode.model_validate(node)
        except ValidationError as e:
            logger.warning(f"QA node #{node_id} failed validation, skipping: {e}")
            results[f"qa_{node_id}"] = {"error": "validation_failed"}
            continue

        qa_data = qa_node.data
        node_name = qa_data.name

        if not qa_data.qa_enabled:
            logger.debug(f"QA node '{node_name}' is disabled, skipping")
            continue

        skip_reason = _should_skip_qa(qa_data, workflow_run)
        if skip_reason:
            logger.info(f"Skipping QA node '{node_name}' (#{node_id}): {skip_reason}")
            results[f"qa_{node_id}"] = {"skipped": True, "reason": skip_reason}
            continue

        try:
            logger.info(f"Running QA analysis for node '{node_name}' (#{node_id})")
            result = await run_per_node_qa_analysis(
                qa_data,
                workflow_run,
                workflow_run_id,
                workflow_definition,
                definition_id,
            )
            results[f"qa_{node_id}"] = result
            # Log summary from node_results
            node_results = result.get("node_results", {})
            logger.info(
                f"QA analysis complete for '{node_name}': "
                f"{len(node_results)} nodes analyzed"
            )
        except Exception as e:
            logger.error(f"QA analysis failed for node '{node_name}': {e}")
            results[f"qa_{node_id}"] = {"error": str(e)}

    return results


async def run_integrations_post_workflow_run(_ctx, workflow_run_id: int):
    """
    Run integrations after a workflow run completes.

    This function:
    1. Gets the workflow run and its contexts
    2. Runs QA analysis nodes (if any)
    3. Stores QA results in annotations
    4. Executes webhook nodes with QA results available in render context
    """
    set_current_run_id(workflow_run_id)
    logger.info("Running integrations for workflow run")

    try:
        # Step 1: Get workflow run with full context
        workflow_run, organization_id = await db_client.get_workflow_run_with_context(
            workflow_run_id
        )

        if not workflow_run or not workflow_run.workflow:
            logger.warning("Workflow run or workflow not found")
            return

        if not organization_id:
            logger.warning("No organization found, skipping integrations")
            return

        # Set org context for tracing and register org-specific Langfuse credentials
        # FIXME: If an org removes langfuse credentials during an exisitng deployment
        # we should unregister an existing langfuse credentials for that org.
        set_current_org_id(organization_id)
        langfuse_config = await db_client.get_configuration_value(
            organization_id,
            OrganizationConfigurationKey.LANGFUSE_CREDENTIALS.value,
        )
        if langfuse_config:
            register_org_langfuse_credentials(
                org_id=organization_id,
                host=langfuse_config.get("host"),
                public_key=langfuse_config.get("public_key"),
                secret_key=langfuse_config.get("secret_key"),
                project_id=langfuse_config.get("project_id"),
            )

        # Step 2: Get workflow definition from the run's pinned version
        workflow_definition = workflow_run.definition.workflow_json
        definition_id = workflow_run.definition.id

        if not workflow_definition:
            logger.debug("No workflow definition, skipping integrations")
            return

        # Step 3: Extract integration nodes
        nodes = workflow_definition.get("nodes", [])
        qa_nodes = [n for n in nodes if n.get("type") == "qa"]
        webhook_nodes = [n for n in nodes if n.get("type") == "webhook"]
        has_registered_integrations = has_completion_handlers(workflow_definition)

        # Step 4: Generate a public access token for any run that needs post-call work.
        has_campaign = workflow_run.campaign_id is not None
        if (
            not webhook_nodes
            and not qa_nodes
            and not has_registered_integrations
            and not has_campaign
        ):
            logger.debug("No integration nodes and no campaign, skipping")
            return

        public_token = await db_client.ensure_public_access_token(workflow_run_id)

        # Step 5: Run QA analysis before webhooks
        if qa_nodes:
            logger.info(f"Found {len(qa_nodes)} QA nodes to execute")
            qa_results = await _run_qa_nodes(
                qa_nodes,
                workflow_run,
                workflow_run_id,
                workflow_definition,
                definition_id,
            )

            if qa_results:
                # Collect unique tags across all QA node results, plus one per
                # failed check.
                #
                # These used to be written to annotations["tags"] under a
                # comment saying "for top-level filtering" -- but the callTags
                # filter reads gathered_context.call_tags (api/db/filters.py),
                # and so does the CSV "Call Tags" column, so nothing could ever
                # read them. Writing them where the filter looks is what makes
                # a QA tag actually filterable; no new filter attribute, no
                # allowlist entry and no index are needed.
                all_tags: set[str] = set()
                for qa_key, qa_result in qa_results.items():
                    for node_result in qa_result.get("node_results", {}).values():
                        for tag in node_result.get("tags", []):
                            if isinstance(tag, str):
                                all_tags.add(tag)
                            elif isinstance(tag, dict) and "tag" in tag:
                                all_tags.add(tag["tag"])
                    for check in qa_result.get("analysis", {}).get("checks", []):
                        # `is False` and not `not passed`: a check with no
                        # verdict is omitted upstream, and a missing verdict
                        # must not tag the call as having failed one.
                        if check.get("passed") is False:
                            all_tags.add(f"check_failed:{check['name']}")

                # Union the extracted values into the nested key the in-call
                # extractor already owns. update_workflow_run merges
                # gathered_context only one level deep, so writing
                # {"extracted_variables": {...}} without reading first would
                # REPLACE whatever the in-call extraction wrote. Nested only --
                # the flat mirror the in-call path also does would let a field
                # named e.g. call_disposition overwrite the run's disposition.
                existing_context = workflow_run.gathered_context or {}
                qa_extracted: Dict[str, Any] = {}
                for qa_result in qa_results.values():
                    qa_extracted.update(
                        qa_result.get("analysis", {}).get("extracted", {})
                    )

                context_update: Dict[str, Any] = {}
                # Only when QA actually extracted something. Writing back a copy
                # of what was already there is not harmless: it is a stale
                # read-modify-write that would clobber anything another writer
                # changed in between, to achieve nothing.
                if qa_extracted:
                    context_update["extracted_variables"] = {
                        **(existing_context.get("extracted_variables") or {}),
                        **qa_extracted,
                    }
                if all_tags:
                    context_update["call_tags"] = sorted(
                        set(existing_context.get("call_tags") or []) | all_tags
                    )

                await db_client.update_workflow_run(
                    workflow_run_id,
                    annotations=qa_results,
                    **({"gathered_context": context_update} if context_update else {}),
                )

                # Re-fetch workflow_run to get updated annotations. Everything
                # above must land BEFORE this: the webhook render context is
                # built once from the re-fetched row, so a later write would
                # never reach a webhook and a re-run would not resend it.
                workflow_run, _ = await db_client.get_workflow_run_with_context(
                    workflow_run_id
                )

        # Step 6: Run registered third-party integrations after uploads are complete
        integration_results = await run_completion_handlers(
            context=IntegrationCompletionContext(
                workflow_run_id=workflow_run_id,
                workflow_run=workflow_run,
                workflow_definition=workflow_definition,
                definition_id=definition_id,
                organization_id=organization_id,
                public_token=public_token,
            )
        )

        if integration_results:
            await db_client.update_workflow_run(
                workflow_run_id, annotations=integration_results
            )
            workflow_run, _ = await db_client.get_workflow_run_with_context(
                workflow_run_id
            )

        # Step 7: Execute webhooks
        if not webhook_nodes:
            logger.debug("No webhook nodes in workflow")
            return

        logger.info(f"Found {len(webhook_nodes)} webhook nodes to execute")

        # Step 8: Build render context (includes annotations from QA and integrations)
        render_context = _build_render_context(workflow_run, public_token)

        # Step 9: Execute each webhook node
        for node in webhook_nodes:
            node_id = node.get("id", "unknown")
            try:
                webhook_node = WebhookRFNode.model_validate(node)
            except ValidationError as e:
                log_failure(
                    RiltFailure(
                        source=ErrorSource.WEBHOOK,
                        type=ErrorType.CONFIG_ERROR,
                        code="webhook-invalid-config",
                        internal_message=f"Webhook node #{node_id} failed validation: {e}",
                        external_message="Check the webhook node configuration.",
                        provider="webhook",
                        error_owner="user",
                        retryable=False,
                    ),
                    organization_id=organization_id,
                    workflow_run_id=workflow_run_id,
                    node_id=str(node_id),
                )
                continue

            webhook_data = webhook_node.data
            try:
                await _enqueue_webhook_delivery(
                    webhook_data=webhook_data,
                    render_context=render_context,
                    organization_id=organization_id,
                    workflow_run_id=workflow_run_id,
                    webhook_node_id=str(node_id),
                )
            except Exception as e:
                log_failure(
                    classify_exception(
                        e,
                        source=ErrorSource.WEBHOOK,
                        provider="webhook",
                        error_owner="user",
                    ),
                    organization_id=organization_id,
                    workflow_run_id=workflow_run_id,
                    node_id=str(node_id),
                )

    except Exception as e:
        log_failure(
            classify_exception(e, source=ErrorSource.INTEGRATION),
            workflow_run_id=workflow_run_id,
        )
        raise


def _build_render_context(
    workflow_run: WorkflowRunModel, public_token: Optional[str] = None
) -> Dict[str, Any]:
    """Build the context dict for template rendering.

    Args:
        workflow_run: The workflow run model
        public_token: Optional public access token for download URLs

    Returns:
        Dict containing all fields available for template rendering
    """
    extra = workflow_run.extra or {}
    user_recording_key = get_recording_storage_key(extra, "user")
    bot_recording_key = get_recording_storage_key(extra, "bot")

    context = {
        # Top-level fields
        "workflow_run_id": workflow_run.id,
        "workflow_run_name": workflow_run.name,
        "workflow_id": workflow_run.workflow_id,
        "workflow_name": workflow_run.workflow.name if workflow_run.workflow else None,
        "campaign_id": workflow_run.campaign_id,
        "call_time": (workflow_run.created_at or datetime.now(UTC)).isoformat(),
        # Nested contexts
        "initial_context": workflow_run.initial_context or {},
        "gathered_context": workflow_run.gathered_context or {},
        "cost_info": workflow_run.usage_info or {},
        # Annotations (includes QA results)
        "annotations": workflow_run.annotations or {},
        "extra": extra,
    }

    # Add public download URLs if token is available
    if public_token:
        base_url = (
            f"{BACKEND_API_ENDPOINT}/api/v1/public/download/workflow/{public_token}"
        )
        context["recording_url"] = (
            f"{base_url}/recording" if workflow_run.recording_url else None
        )
        context["transcript_url"] = (
            f"{base_url}/transcript" if workflow_run.transcript_url else None
        )
        context["user_recording_url"] = (
            f"{base_url}/user_recording" if user_recording_key else None
        )
        context["bot_recording_url"] = (
            f"{base_url}/bot_recording" if bot_recording_key else None
        )
    else:
        context["recording_url"] = workflow_run.recording_url
        context["transcript_url"] = workflow_run.transcript_url
        context["user_recording_url"] = user_recording_key
        context["bot_recording_url"] = bot_recording_key

    return context


def _build_webhook_payload(
    webhook_data: WebhookNodeData, render_context: Dict[str, Any]
) -> Any:
    """Render the webhook payload once, so retries are deterministic.

    Always surfaces the call disposition on the outgoing payload, even when the
    template author didn't reference it. Fill only if absent so a template that
    sets it explicitly keeps its own value.
    """
    payload = render_template(webhook_data.payload_template or {}, render_context)

    if isinstance(payload, dict):
        gathered_context = render_context.get("gathered_context") or {}
        payload.setdefault(
            "call_disposition", gathered_context.get("call_disposition", "")
        )

    return payload


# Substrings that mark a header as likely carrying a secret. Matched against the
# normalized key so variants are caught too (e.g. ``X-Custom-Auth-Token``,
# ``My-Api-Key``), not just exact names. Their values are NOT persisted on the
# delivery row (which would store them in plaintext); secrets belong in the
# credential store, re-resolved at send time. Bare "key" is intentionally absent
# to avoid dropping benign headers like ``X-Idempotency-Key``.
_SECRET_HEADER_MARKERS = (
    "authorization",
    "auth",
    "token",
    "secret",
    "password",
    "passwd",
    "cookie",
    "credential",
    "api-key",
    "apikey",
    "api_key",
    "access-key",
)


def _looks_like_secret_header(key: str) -> bool:
    normalized = key.strip().lower()
    return any(marker in normalized for marker in _SECRET_HEADER_MARKERS)


def _safe_custom_headers(
    webhook_data: WebhookNodeData, webhook_name: str
) -> list[dict]:
    """Custom headers to persist, with secret-looking ones dropped.

    Persisting arbitrary header values would store credentials (Authorization,
    X-API-Key, ...) in plaintext on the delivery row. Drop those and tell the
    operator to use a credential instead.
    """
    safe = []
    for h in webhook_data.custom_headers or []:
        if not (h.key and h.value):
            continue
        if _looks_like_secret_header(h.key):
            logger.warning(
                f"Webhook '{webhook_name}' custom header '{h.key}' looks like a "
                f"secret; it will not be stored or sent. Use a credential instead."
            )
            continue
        safe.append({"key": h.key, "value": h.value})
    return safe


async def _enqueue_webhook_delivery(
    webhook_data: WebhookNodeData,
    render_context: Dict[str, Any],
    organization_id: int,
    workflow_run_id: int,
    webhook_node_id: str,
) -> None:
    """Persist a durable delivery record and enqueue its first send attempt.

    The actual HTTP request is performed by the ``deliver_webhook`` task, which
    retries transient failures with backoff and dead-letters exhausted/permanent
    ones. This replaces the previous one-shot, best-effort inline POST that lost
    the webhook entirely on a single network error.

    Idempotent on ``(workflow_run_id, webhook_node_id)``: a retried run reuses the
    existing delivery row and does not enqueue a second send.
    """
    webhook_name = webhook_data.name

    if not webhook_data.enabled:
        logger.debug(f"Webhook '{webhook_name}' is disabled, skipping")
        return

    url = webhook_data.endpoint_url
    if not url:
        logger.warning(f"Webhook '{webhook_name}' has no endpoint URL")
        return

    payload = _build_webhook_payload(webhook_data, render_context)

    # Persist non-secret request definition. The credential is stored by reference
    # (uuid) and re-resolved at send time so secrets never land in this row.
    custom_headers = _safe_custom_headers(webhook_data, webhook_name)
    method = (webhook_data.http_method or "POST").upper()

    delivery, created = await db_client.create_webhook_delivery(
        workflow_run_id=workflow_run_id,
        organization_id=organization_id,
        endpoint_url=url,
        payload=payload,
        max_attempts=DEFAULT_WEBHOOK_DELIVERY_CONFIG["max_attempts"],
        http_method=method,
        webhook_name=webhook_name,
        custom_headers=custom_headers or None,
        credential_uuid=webhook_data.credential_uuid,
        webhook_node_id=webhook_node_id,
    )

    if not created:
        logger.info(
            f"Webhook '{webhook_name}' delivery already exists for run "
            f"{workflow_run_id} node {webhook_node_id}; not re-enqueuing"
        )
        return

    # Lazy import avoids a circular import (arq imports this module at load time).
    from api.tasks.arq import enqueue_job

    await enqueue_job(
        FunctionNames.DELIVER_WEBHOOK,
        delivery.id,
        _job_id=f"webhook-delivery-{delivery.id}-0",
    )
    logger.info(
        f"Enqueued webhook '{webhook_name}' delivery {delivery.delivery_uuid} "
        f"for run {workflow_run_id}"
    )
