"""Apply a run's governance policy to what is about to be stored.

Called in the pipeline process BEFORE the write, so the raw text never lands. The
voice call-end handler and the text-chat completion both go through here, so the
two cannot drift in what they keep or how they redact.
"""

from datetime import UTC, datetime

from api.services.governance.policy import GovernancePolicy
from api.services.governance.redaction import redact_events, redact_text, redact_value

# The events that carry what was said. Everything else in the log (latency,
# node transitions, tool calls) is operational and stays.
TRANSCRIPT_EVENT_TYPES = frozenset({"rtf-user-transcription", "rtf-bot-text"})


def govern_events(
    events: list[dict], policy: GovernancePolicy | None
) -> tuple[list[dict], dict[str, int]]:
    """Events as they should be stored, and what redaction removed."""
    if policy is None:
        return events, {}
    if not policy.store_transcript:
        events = [e for e in events if e.get("type") not in TRANSCRIPT_EVENT_TYPES]
    return redact_events(events, policy.redaction_categories)


def govern_transcript(
    text: str | None, policy: GovernancePolicy | None
) -> tuple[str | None, dict[str, int]]:
    """The transcript file's text, or None when none should be stored."""
    if not text:
        return text, {}
    if policy is None:
        return text, {}
    if not policy.store_transcript:
        return None, {}
    return redact_text(text, policy.redaction_categories)


def govern_context(context: dict, policy: GovernancePolicy | None) -> tuple[dict, dict[str, int]]:
    """Gathered context, redacted only when the policy explicitly asks.

    Off by default: it feeds webhook payloads and post-call extraction, so
    redacting it silently would break integrations.
    """
    if policy is None or not policy.redact_gathered_context or not policy.redaction_categories:
        return context, {}
    counts: dict[str, int] = {}
    return redact_value(context, policy.redaction_categories, counts), counts


def redaction_record(policy: GovernancePolicy | None, *parts: dict[str, int]) -> dict | None:
    """What goes in ``extra["redaction"]``: proof the pass ran, and what it caught.

    None when the policy redacts nothing, so an ordinary run's ``extra`` is
    untouched. Present with zero counts when the pass ran and found nothing,
    which is a result worth being able to show.
    """
    if policy is None or not policy.redaction_categories:
        return None
    totals: dict[str, int] = {}
    for part in parts:
        for k, v in part.items():
            totals[k] = totals.get(k, 0) + v
    return {
        "categories": list(policy.redaction_categories),
        "counts": totals,
        "applied_at": datetime.now(UTC).isoformat(),
    }
