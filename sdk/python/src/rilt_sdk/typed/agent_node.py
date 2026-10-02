"""GENERATED — do not edit by hand.

Regenerate with `python -m rilt_sdk.codegen` against the target
AICall backend. Source of truth: the backend's model-backed node-spec
catalog served from `/api/v1/node-types`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Optional

from rilt_sdk.typed._base import TypedNode


@dataclass(kw_only=True)
class AgentNode_Extraction_variablesRow:
    """
    Each entry declares one variable to capture, with its name, data type,
    and extraction hint.
    """

    name: str
    """
    snake_case identifier used downstream.
    """
    type: Literal['string', 'number', 'boolean'] = 'string'
    """
    Data type of the extracted value.
    """
    prompt: Optional[str] = None
    """
    Per-variable hint describing what to look for.
    """

@dataclass(kw_only=True)
class AgentNode(TypedNode):
    """
    Conversational step — the LLM runs one focused exchange.  LLM hint: Mid-
    call step executed by the LLM. Most workflows are a chain of agent nodes
    connected by edges that describe transition conditions. Each agent node
    can invoke tools and reference documents.
    """

    type: ClassVar[str] = 'agentNode'

    prompt: str
    """
    Agent system prompt for this step. Supports {{template_variables}} from
    extraction or pre-call fetch.
    """

    name: str = 'Agent'
    """
    Short identifier for this step (e.g., 'Qualify Budget'). Appears in call
    logs and edge transition tools.
    """

    allow_interrupt: bool = True
    """
    When true, the user can interrupt the agent mid-utterance. Set false for
    non-interruptible disclosures.
    """

    language: Optional[Literal['multi', 'ar', 'ar-AE', 'ar-SA', 'ar-QA', 'ar-KW', 'ar-SY', 'ar-LB', 'ar-PS', 'ar-JO', 'ar-EG', 'ar-SD', 'ar-TD', 'ar-MA', 'ar-DZ', 'ar-TN', 'ar-IQ', 'ar-IR', 'be', 'bn', 'bs', 'bg', 'ca', 'cs', 'da', 'da-DK', 'de', 'de-CH', 'el', 'en', 'en-US', 'en-AU', 'en-GB', 'en-IN', 'en-NZ', 'es', 'es-419', 'et', 'fa', 'fi', 'fr', 'fr-CA', 'he', 'hi', 'hr', 'hu', 'id', 'it', 'ja', 'kn', 'ko', 'ko-KR', 'lt', 'lv', 'mk', 'mr', 'ms', 'nl', 'nl-BE', 'no', 'pl', 'pt', 'pt-BR', 'pt-PT', 'ro', 'ru', 'sk', 'sl', 'sr', 'sv', 'sv-SE', 'ta', 'te', 'th', 'tl', 'tr', 'uk', 'ur', 'vi', 'zh-CN', 'zh-TW']] = None
    """
    Switch the call to this language while in this step, for both what the
    agent listens for and how it speaks. Leave empty to use the agent's own
    language. Not available with the managed voice.
    """

    add_global_prompt: bool = True
    """
    When true and a Global node exists, prepends the global prompt to this
    node's prompt at runtime.
    """

    extraction_enabled: bool = False
    """
    When true, runs an LLM extraction pass for this node.
    """

    extraction_prompt: Optional[str] = None
    """
    Overall instructions guiding variable extraction.
    """

    extraction_variables: list[AgentNode_Extraction_variablesRow] = field(default_factory=list)
    """
    Each entry declares one variable to capture, with its name, data type,
    and extraction hint.
    """

    tool_uuids: list[str] = field(default_factory=list)
    """
    Tools the agent can invoke during this step.
    """

    document_uuids: list[str] = field(default_factory=list)
    """
    Documents the agent can reference during this step.
    """

