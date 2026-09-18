"""Structured extraction and pass/fail checks over a finished call.

The QA review pass already reads the transcript and asks an LLM to write prose.
This asks the same transcript a set of NAMED questions instead, so the answers
can be filtered, exported and totalled rather than only read.

Two rules govern everything here:

  Absent is absent. A configured field the model did not return, or returned in
  a shape that will not coerce to its declared type, is OMITTED. It is never
  "", never 0, never null-as-a-value. A check with no verdict is omitted rather
  than recorded as failing. Downstream renders "not analysed" for the
  difference, which is why the configured names are returned alongside the
  results -- the reader needs to know what was asked, not just what came back.

  One inference per QA node per run. Extraction is a whole-call question, so
  splitting it per graph node would produce N conflicting answers per field and
  force merge rules nobody asked for.
"""

from typing import Any

from loguru import logger

from api.services.gen_ai.json_parser import parse_llm_json
from api.services.workflow.dto import QANodeData, VariableType
from api.services.workflow.qa.llm_config import run_llm_inference

_SYSTEM_PROMPT = (
    "You review completed phone conversations and answer specific questions "
    "about them. Return ONLY a valid JSON object. Do not wrap it in markdown.\n"
    "\n"
    'Shape: {"extracted": {<field name>: <value>}, '
    '"checks": {<check name>: {"passed": true|false, "reason": "<one sentence>"'
    ', "score": <0-100 or omitted>}}}\n'
    "\n"
    "If the conversation does not establish a field, OMIT that key entirely. "
    "Do not guess, and do not substitute an empty string, a zero or null -- a "
    "missing key is a meaningful answer and a wrong value is not."
)


def _coerce(value: Any, declared: VariableType) -> Any | None:
    """Value as its declared type, or None if it will not convert.

    The declared type has never been enforced anywhere in this codebase: the
    in-call extractor interpolates it into the prompt text
    (pipecat_engine_variable_extractor.py) and stores whatever JSON comes back.
    So a field declared `number` could arrive as "42", as "forty-two", or as a
    dict. Coercing here is what makes the declared type mean something; None
    means "drop it" rather than "store a default".
    """
    if value is None:
        return None

    if declared == VariableType.string:
        # A dict or list stringifies to something unreadable rather than
        # failing, so those are dropped instead.
        if isinstance(value, (dict, list)):
            return None
        return str(value).strip() or None

    if declared == VariableType.number:
        if isinstance(value, bool):
            # bool is an int subclass in Python; True as 1 is not a number the
            # operator asked for.
            return None
        if isinstance(value, (int, float)):
            return value
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    if declared == VariableType.boolean:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
        return None

    return None


def _score(raw: Any) -> float | None:
    """A 0-100 score, or None. Out-of-range is dropped, not clamped."""
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 100 else None


def _build_user_prompt(fields: list, checks: list, transcript: str) -> str:
    parts = []
    if fields:
        parts.append(
            "Fields to extract:\n"
            + "\n".join(
                f"- {f.name} ({f.type.value}): {f.prompt or 'no further hint'}"
                for f in fields
            )
        )
    if checks:
        parts.append(
            "Checks to evaluate:\n"
            + "\n".join(
                f"- {c.name}: {c.criterion}"
                + (" (also return a 0-100 score)" if c.scored else "")
                for c in checks
            )
        )
    parts.append(f"Conversation:\n{transcript}")
    return "\n\n".join(parts)


async def run_field_analysis(
    qa_data: QANodeData,
    workflow_run_id: int,
    llm,
    transcript: str,
) -> dict[str, Any]:
    """Extract configured fields and evaluate configured checks.

    Returns {} when nothing is configured, so the caller can attach the result
    unconditionally without every run carrying an empty analysis object.
    """
    fields = list(qa_data.qa_extraction_fields or [])
    checks = list(qa_data.qa_checks or [])
    if not fields and not checks:
        return {}
    if not transcript:
        return {"error": "empty_transcript"}

    # The configured names travel with the result. Draft definition rows mutate
    # in place and definition_id is nullable, so a reader cannot reliably go
    # back to the graph to find out what was asked of this run.
    configured = {
        "fields": [{"name": f.name, "type": f.type.value} for f in fields],
        "checks_configured": [c.name for c in checks],
    }

    try:
        raw = await run_llm_inference(
            llm,
            [
                {
                    "role": "user",
                    "content": _build_user_prompt(fields, checks, transcript),
                }
            ],
            _SYSTEM_PROMPT,
            workflow_run_id=workflow_run_id,
        )
    except Exception as e:
        logger.warning(f"Field analysis degraded for run {workflow_run_id}: {e}")
        return {**configured, "error": str(e)}

    if raw is None:
        return {**configured, "error": "no_response"}

    parsed = parse_llm_json(raw)
    # parse_llm_json is annotated -> dict but returns a list for a top-level
    # JSON array and {"raw": ...} when every parse attempt fails.
    if not isinstance(parsed, dict) or set(parsed) == {"raw"}:
        logger.warning(
            f"Field analysis got unusable JSON for run {workflow_run_id}: "
            f"{type(parsed).__name__}"
        )
        return {**configured, "error": "unparseable_response"}

    raw_extracted = parsed.get("extracted")
    if not isinstance(raw_extracted, dict):
        raw_extracted = {}
    extracted: dict[str, Any] = {}
    for field in fields:
        coerced = _coerce(raw_extracted.get(field.name), field.type)
        if coerced is not None:
            extracted[field.name] = coerced

    raw_checks = parsed.get("checks")
    if not isinstance(raw_checks, dict):
        raw_checks = {}
    results = []
    for check in checks:
        verdict = raw_checks.get(check.name)
        if not isinstance(verdict, dict):
            continue
        passed = verdict.get("passed")
        if not isinstance(passed, bool):
            # An unparseable verdict is no verdict. Recording it as a failure
            # would invent a problem and tag the call for it.
            continue
        reason = verdict.get("reason")
        results.append(
            {
                "name": check.name,
                "passed": passed,
                "reason": str(reason).strip() if reason else None,
                "score": _score(verdict.get("score")) if check.scored else None,
            }
        )

    return {**configured, "extracted": extracted, "checks": results}
