"""Canonical catalog of call disposition codes.

``gathered_context.mapped_call_disposition`` is what the Disposition column
and the ``dispositionCode`` filter both read, so this module enumerates every
value the platform can write there. Keeping the list here — rather than
duplicated in the frontend — is what stops the filter dropdown from drifting
behind the code that produces the dispositions.

Two writers feed that field:

* the pipeline, via ``PipecatEngine.end_call_with_reason`` /
  ``record_call_disposition`` — an ``EndTaskReason`` value;
* the telephony status callback, via ``status_processor`` and
  ``mark_workflow_run_failed`` — a ``TelephonyCallStatus`` value, for calls
  that never connected.

Organizations that map dispositions to their own codes (``XFER``, ``DNC``, …)
produce values outside this catalog. Those are learned per workflow by
``add_call_disposition_code`` and merged in by
``get_organization_disposition_codes``.
"""

from pipecat.utils.enums import EndTaskReason

from api.enums import TelephonyCallStatus

# Keep this derived directly from the enum so every pipeline disposition is
# available to clients without maintaining a second list.
END_TASK_REASON_DISPOSITION_CODES: tuple[str, ...] = tuple(
    reason.value for reason in EndTaskReason
)

# Statuses written when the call never reached the pipeline.
_TELEPHONY_DISPOSITIONS: tuple[str, ...] = (
    TelephonyCallStatus.NO_ANSWER.value,
    TelephonyCallStatus.BUSY.value,
    TelephonyCallStatus.FAILED.value,
    TelephonyCallStatus.CANCELED.value,
    TelephonyCallStatus.ERROR.value,
)

SYSTEM_DISPOSITION_CODES: tuple[str, ...] = (
    END_TASK_REASON_DISPOSITION_CODES + _TELEPHONY_DISPOSITIONS
)

# The codes a transfer actually writes into
# gathered_context.mapped_call_disposition. Two of them, because the pipeline
# distinguishes asking for a transfer from completing one
# (api/services/pipecat/event_handlers.py explains why it does not collapse
# them), and a report that counts transfers has to count both.
#
# NOT "XFER". Nothing in the platform writes that string -- the daily report
# compared against it, so its transfer count was structurally zero and the
# dashboard never surfaced the number. An organization may still define XFER as
# a custom code of its own, and it is deliberately not counted here: a custom
# code means whatever that organization decided, which is not necessarily a
# transfer.
TRANSFER_DISPOSITION_CODES: tuple[str, ...] = (
    EndTaskReason.CALL_TRANSFERRED.value,
    EndTaskReason.TRANSFER_CALL.value,
)
