"""The metrics an alert rule may name.

A rule can only name something in this registry, so an alert can never be configured
on a figure the evaluator does not compute. The list is also what the UI offers, so
the two cannot drift.

What is deliberately NOT here, and why: money (a run's cost is null until priced, and
"empty is not zero"), transfer counts, and token counts. The dashboard already learned
these the hard way; see ui/src/app/overview/useDashboardData.ts.
"""

from dataclasses import dataclass
from typing import Optional

from api.enums import AlertComparator, AlertTrigger, TelephonyCallStatus

# A rate over a handful of calls is noise: 1 failed of 2 is "50% failing". Below this
# many finished calls in the window, a rate metric reports nothing rather than guess.
MIN_WINDOW_RUNS_FOR_RATE = 5


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    description: str
    trigger: str
    # "number": compared with a comparator and threshold.
    # "text": matched against rule.match_value.
    # "flag": fires when true; comparator and threshold are not used.
    value_type: str
    unit: Optional[str] = None


_RUN = AlertTrigger.RUN_COMPLETED.value
_WIN = AlertTrigger.WINDOW.value

METRICS: dict[str, Metric] = {
    m.key: m
    for m in (
        Metric("call_failed", "A call failed", "A call ended with an error instead of completing.", _RUN, "flag"),
        Metric("call_duration_seconds", "Call duration", "How long a finished call lasted.", _RUN, "number", "seconds"),
        Metric("call_disposition_is", "Call outcome is", "A call ended with this outcome (for example: busy, no-answer).", _RUN, "text"),
        Metric("call_tag_present", "Call has tag", "A call was tagged with this by quality analysis.", _RUN, "text"),
        Metric("safety_violation", "Safety violation", "The post-call safety scan flagged a violation or a jailbreak attempt.", _RUN, "flag"),
        Metric("window_run_count", "Calls in the window", "How many calls finished in the last N minutes. Use 'below' to catch silence.", _WIN, "number", "calls"),
        Metric("window_failed_rate_percent", "Failure rate in the window", f"Share of calls that failed in the last N minutes. Needs at least {MIN_WINDOW_RUNS_FOR_RATE} calls to judge.", _WIN, "number", "%"),
        Metric("window_mean_duration_seconds", "Average duration in the window", "Mean length of calls that finished in the last N minutes.", _WIN, "number", "seconds"),
    )
}


def get_metric(key: str) -> Optional[Metric]:
    return METRICS.get(key)


def compare(comparator: str, observed: float, threshold: float) -> bool:
    return {
        AlertComparator.GT.value: observed > threshold,
        AlertComparator.GTE.value: observed >= threshold,
        AlertComparator.LT.value: observed < threshold,
        AlertComparator.LTE.value: observed <= threshold,
        AlertComparator.EQ.value: observed == threshold,
    }.get(comparator, False)


def _disposition(run) -> Optional[str]:
    value = (getattr(run, "gathered_context", None) or {}).get("mapped_call_disposition")
    return str(value) if value is not None else None


def run_observation(metric_key: str, run, match_value: Optional[str]) -> tuple[Optional[float], bool]:
    """(observed number or None, whether the condition itself already holds).

    The second element is how flag and text metrics answer; number metrics leave it
    False and are decided by the comparator.
    """
    if metric_key == "call_failed":
        failed = _disposition(run) == TelephonyCallStatus.ERROR.value
        return (1.0 if failed else 0.0), failed
    if metric_key == "call_duration_seconds":
        raw = (getattr(run, "usage_info", None) or {}).get("call_duration_seconds")
        try:
            return float(raw), False
        except (TypeError, ValueError):
            return None, False
    if metric_key == "call_disposition_is":
        hit = bool(match_value) and (_disposition(run) or "").lower() == match_value.strip().lower()
        return (1.0 if hit else 0.0), hit
    if metric_key == "call_tag_present":
        tags = (getattr(run, "gathered_context", None) or {}).get("call_tags") or []
        wanted = (match_value or "").strip().lower()
        hit = bool(wanted) and any(isinstance(t, str) and t.lower() == wanted for t in tags)
        return (1.0 if hit else 0.0), hit
    if metric_key == "safety_violation":
        safety = (getattr(run, "annotations", None) or {}).get("safety") or {}
        hit = bool(safety.get("violations")) or safety.get("jailbreak_attempt") is True
        return (1.0 if hit else 0.0), hit
    return None, False


def window_observation(metric_key: str, stats: dict) -> Optional[float]:
    if metric_key == "window_run_count":
        return float(stats["run_count"])
    if metric_key == "window_failed_rate_percent":
        if stats["run_count"] < MIN_WINDOW_RUNS_FOR_RATE:
            return None
        return 100.0 * stats["failed_count"] / stats["run_count"]
    if metric_key == "window_mean_duration_seconds":
        return stats["mean_duration_seconds"]
    return None
