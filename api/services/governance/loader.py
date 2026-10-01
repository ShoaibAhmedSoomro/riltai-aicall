"""Resolve a run's policy from the stores that hold it.

Kept apart from policy.py because that module is imported by the database layer,
and this one imports the database layer.
"""

from loguru import logger

from api.schemas.organization_preferences import OrganizationPreferences
from api.services.governance.policy import GovernancePolicy, resolve_governance_policy
from api.services.organization_preferences import get_organization_preferences


async def load_governance_policy(
    workflow_configurations: dict | None, organization_id: int | None
) -> GovernancePolicy:
    """The agent's block over the organization's defaults.

    The agent's own settings always apply: they are passed in, not fetched. Only
    the organization default needs a lookup, and if that fails the agent's
    settings still hold and the default falls back to "keep everything" -- the
    same behaviour as before governance existed. Logged loudly, because a silent
    fallback here would mean an org-wide opt-out quietly not applying.
    """
    prefs = OrganizationPreferences()
    try:
        prefs = await get_organization_preferences(organization_id)
    except Exception as exc:
        logger.error(
            f"Could not read organization preferences for governance "
            f"(organization {organization_id}); using the agent's settings only: {exc}"
        )
    return resolve_governance_policy(workflow_configurations, prefs)
