"""Which rules a run is under: the agent's block over the organization's default."""

from datetime import UTC, datetime

from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.workflow_configurations import (
    REDACTION_CATEGORIES,
    WorkflowConfigurationDefaults,
)
from api.services.governance.policy import resolve_governance_policy, retention_deadline


def _org(**kw):
    return OrganizationPreferences(**kw)


def test_nothing_configured_changes_nothing():
    """Every default equals today's behaviour: keep everything, forever."""
    p = resolve_governance_policy({}, _org())
    assert p.storage_mode == "everything"
    assert p.retention_days is None
    assert p.record_audio and p.store_transcript
    assert p.redaction_categories == ()
    assert not p.guardrails.enabled
    assert retention_deadline(datetime(2026, 1, 1, tzinfo=UTC), p) is None


def test_an_agent_with_no_opinion_inherits_the_organization_default():
    p = resolve_governance_policy({}, _org(data_retention_days=30))
    assert p.retention_days == 30


def test_an_agent_overrides_the_organization():
    cfg = {"governance_configuration": {"retention_days": 7}}
    assert resolve_governance_policy(cfg, _org(data_retention_days=30)).retention_days == 7


def test_zero_on_an_agent_means_keep_forever_not_inherit():
    """0 and None are different answers: 'forever on purpose' vs 'ask the org'."""
    cfg = {"governance_configuration": {"retention_days": 0}}
    p = resolve_governance_policy(cfg, _org(data_retention_days=30))
    assert p.retention_days is None


def test_the_deadline_is_creation_plus_the_window():
    p = resolve_governance_policy(
        {"governance_configuration": {"retention_days": 10}}, _org()
    )
    start = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    assert retention_deadline(start, p) == datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def test_basic_only_turns_off_audio_and_transcript_whatever_the_switches_say():
    cfg = {
        "governance_configuration": {
            "storage_mode": "basic_only",
            "record_audio": True,
            "store_transcript": True,
        }
    }
    p = resolve_governance_policy(cfg, _org())
    assert p.basic_only
    assert not p.record_audio and not p.store_transcript


def test_the_organization_default_storage_mode_applies_to_an_agent_that_has_none():
    p = resolve_governance_policy({}, _org(default_storage_mode="basic_only"))
    assert p.basic_only


def test_an_agent_storage_mode_beats_the_organization_default():
    cfg = {"governance_configuration": {"storage_mode": "everything"}}
    p = resolve_governance_policy(cfg, _org(default_storage_mode="basic_only"))
    assert not p.basic_only and p.record_audio


def test_except_pii_with_no_categories_redacts_all_of_them():
    """Keeping everything under a mode named 'except personal data' would be the
    opposite of what it says."""
    cfg = {"governance_configuration": {"storage_mode": "except_pii"}}
    assert resolve_governance_policy(cfg, _org()).redaction_categories == REDACTION_CATEGORIES


def test_chosen_categories_are_kept_as_chosen():
    cfg = {
        "governance_configuration": {
            "storage_mode": "except_pii",
            "redaction_categories": ["email"],
        }
    }
    assert resolve_governance_policy(cfg, _org()).redaction_categories == ("email",)


def test_a_malformed_block_falls_back_to_defaults_instead_of_raising():
    """It comes out of a JSON column; a bad dial must not stop a call starting."""
    cfg = {"governance_configuration": {"retention_days": "soon", "storage_mode": 5}}
    p = resolve_governance_policy(cfg, _org(data_retention_days=14))
    assert p.retention_days == 14 and p.storage_mode == "everything"


def test_the_block_is_part_of_the_workflow_configuration_defaults():
    d = WorkflowConfigurationDefaults()
    assert d.governance_configuration.record_audio is True
    assert d.governance_configuration.retention_days is None


def test_guardrails_report_whether_anything_is_on():
    cfg = {"governance_configuration": {"guardrails": {"input_jailbreak": True}}}
    assert resolve_governance_policy(cfg, _org()).guardrails.enabled
