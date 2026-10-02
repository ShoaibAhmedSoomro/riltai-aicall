"""Text rewrites applied to what the agent says, just before it is spoken.

Two things, in this order:

1. The agent's own pronunciation overrides ("AED" -> "dirhams", "Acme" -> "Ack-me").
2. Pipecat's standard speech formatting (numbers, dates, currency, phone numbers...).

The order is the reason overrides are a separate transform and not VoiceFormatter's own
``custom_replacements``: that option runs LAST, and by then acronym spacing has already
turned "AED" into "A E D", so an override for "AED" could never match.

Overrides are literal text, never a pattern the user wrote. Pipecat compiles what it is
given as a regular expression, so a user-supplied pattern would be a way to stall the
call with catastrophic backtracking. Everything is escaped here.

Nothing is returned for an agent with neither feature on, so existing agents' speech is
unchanged. Bad stored values are ignored, never raised: this runs while a call connects.
"""

from __future__ import annotations

import re
from typing import Callable

from loguru import logger

from api.schemas.workflow_configurations import (
    PronunciationOverride,
    SpeechNormalizationDefaults,
)


def override_pattern(override: PronunciationOverride) -> str:
    """A regex that matches exactly the override's text.

    Whole-word uses look-arounds rather than ``\\b`` so text that starts or ends with a
    symbol ("C++", "R&D") still matches at its edges.
    """
    body = re.escape(override.from_text)
    if override.whole_word:
        body = rf"(?<!\w){body}(?!\w)"
    return body if override.match_case else f"(?i){body}"


def _escape_replacement(text: str) -> str:
    # A replacement string is a template: "\1" or "\g<0>" would mean something. The
    # text the user typed means only itself.
    return text.replace("\\", "\\\\")


def _overrides(configs: dict) -> list[PronunciationOverride]:
    out = []
    for raw in configs.get("pronunciation_overrides") or []:
        try:
            out.append(PronunciationOverride.model_validate(raw))
        except Exception:
            logger.warning("Ignoring an invalid pronunciation override")
    return out


def _normalization(configs: dict) -> SpeechNormalizationDefaults | None:
    try:
        opts = SpeechNormalizationDefaults.model_validate(configs.get("speech_normalization") or {})
    except Exception:
        logger.warning("Ignoring invalid speech_normalization")
        return None
    return opts if opts.enabled else None


def build_tts_text_transforms(workflow_configurations: dict | None) -> list[Callable]:
    """The transforms to register on the voice, in order; empty when nothing is set."""
    configs = workflow_configurations or {}
    transforms: list[Callable] = []

    overrides = _overrides(configs)
    if overrides:
        from pipecat.utils.text.transforms.replacements import replace_text

        transforms.append(
            replace_text(
                [(override_pattern(o), _escape_replacement(o.to_text)) for o in overrides]
            )
        )

    normalization = _normalization(configs)
    if normalization is not None:
        from pipecat.utils.text.transforms.voice_formatter import VoiceFormatter

        try:
            transforms.append(VoiceFormatter(**normalization.model_dump(exclude={"enabled"})))
        except Exception as e:
            # e.g. a formatter option whose optional dependency is missing
            logger.error(f"Speech formatting unavailable, continuing without it: {e}")

    return transforms
