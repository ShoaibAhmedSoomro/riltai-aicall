from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from api.constants import (
    MAX_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
    MIN_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
    TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
)

DEFAULT_MAX_CALL_DURATION_SECONDS = 300
# Hard ceiling on configurable call duration. Must stay <= the concurrency
# rate limiter's stale_call_timeout (20 min): a call running past that has
# its slot purged as stale and the org concurrency limit under-counts.
MAX_CALL_DURATION_SECONDS = 1200
DEFAULT_MAX_USER_IDLE_TIMEOUT_SECONDS = 10.0
DEFAULT_SMART_TURN_STOP_SECS = 2.0
DEFAULT_TURN_START_STRATEGY = "default"
DEFAULT_TURN_START_MIN_WORDS = 3
DEFAULT_PROVISIONAL_VAD_PAUSE_SECS = 1.5
DEFAULT_TURN_STOP_STRATEGY = "transcription"
DEFAULT_CONTEXT_COMPACTION_ENABLED = False

# Every constant below equals a literal that is live in the pipeline today, so
# adding these dials changes nothing until somebody moves one. Sources:
#   VAD_*  -> pipecat VADParams defaults (audio/vad/vad_analyzer.py)
#   STT_*  -> the Deepgram Flux and RiltAI Flux branches of service_factory
#   KB_*   -> PipecatEngine's knowledge-base lookup
DEFAULT_VAD_STOP_SECS = 0.2
DEFAULT_VAD_CONFIDENCE = 0.7
DEFAULT_VAD_START_SECS = 0.2
DEFAULT_STT_ENDPOINTING_MS = 100
DEFAULT_STT_EOT_THRESHOLD = 0.7
DEFAULT_STT_EAGER_EOT_THRESHOLD = 0.5
DEFAULT_STT_EOT_TIMEOUT_MS = 3000
DEFAULT_KB_CHUNKS_TO_RETRIEVE = 3
# 0.0 keeps every result, which is what no filter at all did.
DEFAULT_KB_MIN_SIMILARITY = 0.0


class ExternalPBXFieldMapping(BaseModel):
    """Map one gathered-context value to a provider-native field."""

    context_path: str = Field(min_length=1, max_length=255)
    destination_field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

    @field_validator("context_path", mode="before")
    @classmethod
    def strip_context_path(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("destination_field", mode="before")
    @classmethod
    def strip_destination_field(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


# Extra lead fields to capture from the inbound INVITE, named without the
# provider's header prefix (``first_name`` -> ``X-VICIDIAL-first_name``). Each
# entry costs one ARI round trip during call setup, so the set is configured
# explicitly per workflow rather than enumerated off the INVITE.
MAX_EXTERNAL_PBX_LEAD_HEADERS = 50

ExternalPBXLeadHeader = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
]


class AmbientNoiseConfigurationDefaults(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    volume: float = 0.3


class VADConfigurationDefaults(BaseModel):
    """When the agent decides the caller has stopped talking.

    Mirrors pipecat's VADParams. min_volume is deliberately not exposed: it is
    the one parameter where a wrong value makes the agent deaf rather than
    merely eager or slow.
    """

    model_config = ConfigDict(extra="allow")

    stop_secs: float = Field(default=DEFAULT_VAD_STOP_SECS, ge=0.05, le=2.0)
    confidence: float = Field(default=DEFAULT_VAD_CONFIDENCE, ge=0.1, le=1.0)
    start_secs: float = Field(default=DEFAULT_VAD_START_SECS, ge=0.0, le=1.0)


class STTTurnConfigurationDefaults(BaseModel):
    """End-of-turn detection inside the transcriber.

    Provider-specific by nature: the three eot_* dials reach Deepgram Flux and
    the AICall managed transcriber, endpointing_ms reaches Deepgram Nova, and
    on any other provider they are accepted and ignored -- the same tolerance
    the Dictionary feature already has.
    """

    model_config = ConfigDict(extra="allow")

    endpointing_ms: int = Field(default=DEFAULT_STT_ENDPOINTING_MS, ge=10, le=2000)
    eot_threshold: float = Field(default=DEFAULT_STT_EOT_THRESHOLD, ge=0.1, le=1.0)
    eager_eot_threshold: float = Field(
        default=DEFAULT_STT_EAGER_EOT_THRESHOLD, ge=0.1, le=1.0
    )
    eot_timeout_ms: int = Field(default=DEFAULT_STT_EOT_TIMEOUT_MS, ge=500, le=15000)


class KnowledgeBaseConfigurationDefaults(BaseModel):
    """How much the agent pulls back from its documents, and how strictly."""

    model_config = ConfigDict(extra="allow")

    chunks_to_retrieve: int = Field(default=DEFAULT_KB_CHUNKS_TO_RETRIEVE, ge=1, le=10)
    min_similarity: float = Field(default=DEFAULT_KB_MIN_SIMILARITY, ge=0.0, le=1.0)


class WorkflowConfigurationDefaults(BaseModel):
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _treat_null_as_unset(cls, data):
        # Stored configs (and older clients) carry explicit JSON nulls for
        # keys the user never configured; dropping them lets the field
        # defaults apply instead of failing validation.
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data

    ambient_noise_configuration: AmbientNoiseConfigurationDefaults = Field(
        default_factory=AmbientNoiseConfigurationDefaults
    )
    vad_configuration: VADConfigurationDefaults = Field(
        default_factory=VADConfigurationDefaults
    )
    stt_turn_configuration: STTTurnConfigurationDefaults = Field(
        default_factory=STTTurnConfigurationDefaults
    )
    knowledge_base_configuration: KnowledgeBaseConfigurationDefaults = Field(
        default_factory=KnowledgeBaseConfigurationDefaults
    )
    max_call_duration: int = Field(
        default=DEFAULT_MAX_CALL_DURATION_SECONDS,
        gt=0,
        le=MAX_CALL_DURATION_SECONDS,
    )
    max_user_idle_timeout: float = DEFAULT_MAX_USER_IDLE_TIMEOUT_SECONDS
    smart_turn_stop_secs: float = DEFAULT_SMART_TURN_STOP_SECS
    turn_start_strategy: Literal["default", "min_words", "provisional_vad"] = (
        DEFAULT_TURN_START_STRATEGY
    )
    turn_start_min_words: int = DEFAULT_TURN_START_MIN_WORDS
    provisional_vad_pause_secs: float = DEFAULT_PROVISIONAL_VAD_PAUSE_SECS
    turn_stop_strategy: Literal["transcription", "turn_analyzer"] = (
        DEFAULT_TURN_STOP_STRATEGY
    )
    dictionary: str = ""
    context_compaction_enabled: bool = DEFAULT_CONTEXT_COMPACTION_ENABLED
    text_chat_inactivity_timeout_seconds: int = Field(
        default=TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
        ge=MIN_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
        le=MAX_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
    )
    external_pbx_field_mappings: list[ExternalPBXFieldMapping] = Field(
        default_factory=list,
        max_length=100,
    )
    external_pbx_lead_headers: list[ExternalPBXLeadHeader] = Field(
        default_factory=list,
        max_length=MAX_EXTERNAL_PBX_LEAD_HEADERS,
    )

    @field_validator("external_pbx_lead_headers", mode="before")
    @classmethod
    def strip_lead_headers(cls, value: object) -> object:
        """Trim and de-duplicate while preserving the configured order."""
        if not isinstance(value, list):
            return value
        cleaned: list[str] = []
        for item in value:
            name = item.strip() if isinstance(item, str) else item
            if name and name not in cleaned:
                cleaned.append(name)
        return cleaned


class TextChatInactivityTimeoutConstraints(BaseModel):
    """Backend-owned timeout metadata consumed by generated API clients."""

    default_seconds: int = TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS
    minimum_seconds: int = MIN_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS
    maximum_seconds: int = MAX_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS


def resolve_knowledge_base_configuration(
    configs: dict | None,
) -> KnowledgeBaseConfigurationDefaults:
    """Validated KB dials from a stored config blob, or the defaults.

    Shared by the voice and text-chat runners so the two cannot drift. Invalid
    values fall back rather than raise: these come out of a JSON column, and a
    bad dial must degrade retrieval quality, not stop the call connecting.
    """
    try:
        return KnowledgeBaseConfigurationDefaults(
            **((configs or {}).get("knowledge_base_configuration") or {})
        )
    except Exception:
        return KnowledgeBaseConfigurationDefaults()


def get_default_workflow_configurations() -> WorkflowConfigurationDefaults:
    return WorkflowConfigurationDefaults()
