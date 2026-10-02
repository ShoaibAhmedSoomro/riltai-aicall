"""Mid-call language switching: which language a code means, and whether to switch.

A node may carry a language (the same codes the agent-level language picker offers).
Entering the node changes what the transcriber listens for and what the voice speaks,
and entering a node with no language returns to the agent's own. Pure so the decisions
are tested without an engine.
"""

from __future__ import annotations

from typing import Optional

from pipecat.transcriptions.language import Language


def to_pipecat_language(code: Optional[str]) -> Optional[Language]:
    """The pipecat language for a picker code, or None if there is no such language.

    "ar-AE" falls back to "ar" when the regional form is not one pipecat knows. "multi"
    (auto-detect) is not a language a voice can speak, so it maps to None.
    """
    if not code or code == "multi":
        return None
    for candidate in (code, code.split("-")[0]):
        try:
            return Language(candidate)
        except ValueError:
            continue
    return None


def language_to_apply(
    node_language: Optional[str],
    base_language: Optional[str],
    active_language: Optional[str],
) -> Optional[str]:
    """The code to switch to, or None when nothing should change.

    A node without a language means the agent's own. If that is unknown, the call
    simply stays in whatever it is speaking rather than guess.
    """
    target = node_language or base_language
    if not target or target == active_language:
        return None
    return target
