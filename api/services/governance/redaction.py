"""Deterministic PII redaction for transcripts and logs.

``redact_text(text, categories) -> (text, counts)`` replaces matches with
``[REDACTED:<category>]`` and reports how many it replaced per category, so a
compliance reviewer can see that the pass ran and what it caught.

WHAT THIS IS, AND IS NOT. It is a pattern pass over text that has already been
transcribed. It catches numbers and identifiers written as digits and fixed
formats (phone, email, card, national IDs, street addresses, dates of birth
given with a cue like "born" or "DOB"). It does NOT catch:

* numbers spoken out as words ("five oh five ...") -- speech-to-text usually
  writes digits, but not always;
* names and free-text details ("I live next to the blue mosque");
* anything in a language or format the patterns do not know.

A model pass could catch more and was deliberately not built: it would send the
very text being protected to a second provider. This module is the floor, not the
ceiling. Of the sixteen speech providers wired in service_factory.py, only
Deepgram can also redact inside the provider, so this post-processing pass is the
primary mechanism for the rest.

Where a digit run is ambiguous the pass over-redacts (a 7-digit order number may
be taken for a phone number). That is the safe direction for a privacy control.
The one place it works to be exact is payment cards: a Luhn check means an
order or reference number that merely looks long is left alone.
"""

import re
from typing import Any, Callable

from api.schemas.workflow_configurations import REDACTION_CATEGORIES

__all__ = ["redact_text", "redact_value", "redact_events", "REDACTION_CATEGORIES"]


def _placeholder(category: str) -> str:
    return f"[REDACTED:{category}]"


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DATE = (
    r"(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"
    r"|\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTHS}\.?,?\s+\d{{2,4}}"
    rf"|{_MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{2,4}})"
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")
_PHONE = re.compile(r"(?<![\w@./\-])\+?\(?\d[\d ().\-]{5,18}\d(?![\w@])")
_DOB = re.compile(
    r"(?i)((?:born|dob|d\.o\.b\.?|date of birth|birth ?date|birthday)\W{0,25}"
    r"(?:on|is|was)?\W{0,10})(" + _DATE + ")"
)
_NATIONAL_ID = [
    # UAE Emirates ID, US SSN, Pakistani CNIC.
    re.compile(r"(?<!\d)784[\- ]?\d{4}[\- ]?\d{7}[\- ]?\d(?!\d)"),
    re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    re.compile(r"(?<!\d)\d{5}-\d{7}-\d(?!\d)"),
]
# "my passport number is X1234567": redact the value after the cue, keep the cue.
_ID_CUE = re.compile(
    r"(?i)(\b(?:passport|national id|id number|id no\.?|nic|cnic|emirates id|ssn|"
    r"social security)\b(?:\s+(?:number|no\.?))?\W{0,8}(?:is\s+)?)"
    # Not a value an earlier pass already replaced.
    r"(?!REDACTED)([A-Z0-9][A-Z0-9 \-]{4,18}[A-Z0-9])"
)
_STREET = re.compile(
    r"(?i)\b\d{1,5}[A-Za-z]?\s+(?:[A-Za-z0-9.'\-]+\s+){0,4}?"
    r"(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way|court|ct|"
    r"place|pl)\b\.?"
)
_UNIT = re.compile(
    r"(?i)\b(?:villa|flat|apartment|apt|unit|building|bldg|tower|po\s?box|"
    r"p\.o\.\s?box)\s*(?:no\.?\s*)?#?\s*[A-Za-z0-9\-]{1,8}\b"
)
_LOOKS_LIKE_DATE = re.compile(
    r"^(?:\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})$"
)
_PLAIN_DECIMAL = re.compile(r"^\d+\.\d+$")


def _sub(pattern: re.Pattern, text: str, category: str, counts: dict, *, accept=None):
    def repl(m: re.Match) -> str:
        if accept is not None and not accept(m.group(0)):
            return m.group(0)
        counts[category] = counts.get(category, 0) + 1
        return _placeholder(category)

    return pattern.sub(repl, text)


def _sub_group2(pattern: re.Pattern, text: str, category: str, counts: dict) -> str:
    def repl(m: re.Match) -> str:
        counts[category] = counts.get(category, 0) + 1
        return m.group(1) + _placeholder(category)

    return pattern.sub(repl, text)


def _accept_card(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


def _accept_phone(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        return False
    stripped = raw.strip()
    return not (_LOOKS_LIKE_DATE.match(stripped) or _PLAIN_DECIMAL.match(stripped))


def _national_id(text: str, counts: dict) -> str:
    for pattern in _NATIONAL_ID:
        text = _sub(pattern, text, "national_id", counts)
    return _sub_group2(_ID_CUE, text, "national_id", counts)


def _address(text: str, counts: dict) -> str:
    text = _sub(_STREET, text, "address", counts)
    return _sub(_UNIT, text, "address", counts)


# Order matters: the most specific patterns first, so a national ID is not
# half-eaten by the phone pattern and an email's digits are not read as a number.
_PASSES: list[tuple[str, Callable[[str, dict], str]]] = [
    ("national_id", _national_id),
    ("card", lambda t, c: _sub(_CARD, t, "card", c, accept=_accept_card)),
    ("email", lambda t, c: _sub(_EMAIL, t, "email", c)),
    ("dob", lambda t, c: _sub_group2(_DOB, t, "dob", c)),
    ("phone", lambda t, c: _sub(_PHONE, t, "phone", c, accept=_accept_phone)),
    ("address", _address),
]


def redact_text(text: str, categories) -> tuple[str, dict[str, int]]:
    """Return the redacted text and a per-category count of replacements."""
    counts: dict[str, int] = {}
    if not text or not categories:
        return text, counts
    wanted = set(categories)
    for name, apply in _PASSES:
        if name in wanted:
            text = apply(text, counts)
    return text, counts


# Keys whose values are identifiers or timestamps, never speech. A timestamp is
# digits with separators and must not be mistaken for a phone number.
_SKIP_KEYS = frozenset({"timestamp", "created_at", "id", "type", "node_id", "turn"})


def _merge(into: dict[str, int], more: dict[str, int]) -> None:
    for k, v in more.items():
        into[k] = into.get(k, 0) + v


def redact_value(value: Any, categories, counts: dict[str, int] | None = None) -> Any:
    """Redact every string inside a JSON-like structure; other types pass through."""
    counts = counts if counts is not None else {}
    if isinstance(value, str):
        out, c = redact_text(value, categories)
        _merge(counts, c)
        return out
    if isinstance(value, dict):
        return {
            k: (v if k in _SKIP_KEYS else redact_value(v, categories, counts))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(v, categories, counts) for v in value]
    return value


def redact_events(events: list[dict], categories) -> tuple[list[dict], dict[str, int]]:
    """Redact the payload of each realtime feedback event.

    Only ``payload`` is touched: the envelope (type, timestamp, turn, node) is
    metadata the run detail view and reports depend on.
    """
    counts: dict[str, int] = {}
    if not categories:
        return events, counts
    out = []
    for event in events:
        if isinstance(event, dict) and "payload" in event:
            event = {**event, "payload": redact_value(event["payload"], categories, counts)}
        out.append(event)
    return out, counts
