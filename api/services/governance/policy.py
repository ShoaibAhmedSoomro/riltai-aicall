"""Which data-handling rules a run is under.

One pure function. Everything that stamps, purges, redacts or screens a run asks
this rather than reading the two config surfaces itself, so they cannot disagree
about what "the policy" is.

Two surfaces feed it: the agent's versioned ``governance_configuration``
(snapshotted per version, already covered by the publish diff) and the
organization's defaults. Nothing here touches the database.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from loguru import logger

from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.workflow_configurations import (
    REDACTION_CATEGORIES,
    GovernanceConfigurationDefaults,
    GuardrailConfigurationDefaults,
)


@dataclass(frozen=True)
class GovernancePolicy:
    storage_mode: str
    # None means never purge. Never 0: "keep forever" is normalised away here so
    # no caller has to remember that 0 is special.
    retention_days: int | None
    record_audio: bool
    store_transcript: bool
    redaction_categories: tuple[str, ...]
    redact_gathered_context: bool
    guardrails: GuardrailConfigurationDefaults

    @property
    def basic_only(self) -> bool:
        return self.storage_mode == "basic_only"


def _agent_config(workflow_configurations: dict | None) -> GovernanceConfigurationDefaults:
    """The agent's block, or the defaults when it is absent or malformed.

    Falls back rather than raising: this comes out of a JSON column, and a bad
    dial must not stop a call from being created.
    """
    raw = (workflow_configurations or {}).get("governance_configuration")
    if not raw:
        return GovernanceConfigurationDefaults()
    try:
        return GovernanceConfigurationDefaults.model_validate(raw)
    except Exception as exc:
        logger.warning(f"Invalid governance_configuration, using defaults: {exc}")
        return GovernanceConfigurationDefaults()


def resolve_governance_policy(
    workflow_configurations: dict | None,
    organization: OrganizationPreferences | None = None,
) -> GovernancePolicy:
    org = organization or OrganizationPreferences()
    agent = _agent_config(workflow_configurations)

    storage_mode = agent.storage_mode or org.default_storage_mode

    if agent.retention_days is None:
        retention_days = org.data_retention_days
    elif agent.retention_days == 0:
        retention_days = None
    else:
        retention_days = agent.retention_days

    categories = tuple(agent.redaction_categories)
    if storage_mode == "except_pii" and not categories:
        # "Everything except personal data" with no categories chosen would keep
        # everything, which is the opposite of what the mode says.
        categories = REDACTION_CATEGORIES

    basic = storage_mode == "basic_only"
    return GovernancePolicy(
        storage_mode=storage_mode,
        retention_days=retention_days,
        record_audio=agent.record_audio and not basic,
        store_transcript=agent.store_transcript and not basic,
        redaction_categories=categories,
        redact_gathered_context=agent.redact_gathered_context,
        guardrails=agent.guardrails,
    )


def retention_deadline(created_at: datetime, policy: GovernancePolicy) -> datetime | None:
    if policy.retention_days is None:
        return None
    return created_at + timedelta(days=policy.retention_days)
