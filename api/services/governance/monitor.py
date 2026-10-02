"""What a live supervisor may see and hear, under the run's data policy.

The caller's own browser still gets every event raw: it is the caller's conversation.
Only the copy that leaves the call for the monitor stream is governed, using the same
functions that decide what is stored after the call, so live and stored cannot disagree
about what a policy withholds.
"""

from typing import Callable, Optional

from api.services.governance.enforcement import govern_events
from api.services.governance.policy import GovernancePolicy

Event = dict


def monitor_view_for(policy: Optional[GovernancePolicy]) -> Callable[[Event], Optional[Event]]:
    def view(event: Event) -> Optional[Event]:
        # Interim transcripts are churn that no supervisor needs and that would
        # multiply the stream's write volume. Finals carry the content.
        if event.get("type") == "rtf-user-transcription" and not (
            event.get("payload") or {}
        ).get("final", True):
            return None
        kept, _ = govern_events([event], policy)
        return kept[0] if kept else None

    return view


def allows_listen_in(policy: Optional[GovernancePolicy]) -> bool:
    """Listen-in carries raw audio, which cannot be redacted. So it is off for a
    call whose policy withholds the audio or redacts what was said."""
    if policy is None:
        return True
    return policy.record_audio and not policy.redaction_categories
