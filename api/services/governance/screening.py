"""Zero-latency screening of what a caller says.

Used by the in-call guardrail, which sits on the critical path of every turn and
therefore cannot afford a model call. These are fixed patterns for well-known
instruction-override and prompt-extraction attempts. They catch the common,
low-effort attacks; a determined one phrased differently gets through, which is
what the post-call scan (safety_scan.py) is for.

Returns the NAME of the rule that matched, never the caller's words, so a log
line or event written from this cannot itself carry personal data.
"""

import re

_RULES: list[tuple[str, re.Pattern]] = [
    (
        "ignore_instructions",
        re.compile(
            r"(?i)\b(?:ignore|disregard|forget|override)\b[^.?!]{0,30}\b"
            r"(?:previous|prior|above|earlier|all|any|your|the)\b[^.?!]{0,20}\b"
            r"(?:instructions?|rules?|prompts?|guidelines?|directions?)\b"
        ),
    ),
    (
        "reveal_prompt",
        re.compile(
            r"(?i)\b(?:reveal|show|print|repeat|tell me|read out|what(?:'s| is))\b"
            r"[^.?!]{0,30}\b(?:system|hidden|initial|original|secret)\s+"
            r"(?:prompt|instructions?|message)\b"
        ),
    ),
    (
        "role_override",
        re.compile(
            r"(?i)\b(?:you are now|from now on you are|act as|pretend (?:to be|you are)|"
            r"roleplay as)\b[^.?!]{0,60}\b(?:dan|unrestricted|unfiltered|jailbroken|"
            r"without (?:any )?(?:rules|restrictions|filters|limits)|no (?:rules|restrictions|filters|limits))"
        ),
    ),
    (
        "developer_mode",
        re.compile(r"(?i)\b(?:developer|debug|god|sudo|admin) mode\b|\bjailbreak(?:ing|ed)?\b|\bdo anything now\b"),
    ),
    (
        "bypass_safety",
        re.compile(
            r"(?i)\b(?:bypass|disable|turn off|get around|circumvent)\b[^.?!]{0,25}\b"
            r"(?:safety|safeguards?|guardrails?|filters?|restrictions?|content polic(?:y|ies))\b"
        ),
    ),
]


def looks_like_jailbreak(text: str | None) -> str | None:
    """The name of the first rule the text trips, or None."""
    if not text:
        return None
    for name, pattern in _RULES:
        if pattern.search(text):
            return name
    return None
