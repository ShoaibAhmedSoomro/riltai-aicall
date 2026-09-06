"""Per-agent tuning: every default this workstream promised not to move.

Nine numbers that were hardcoded in the pipeline became configurable. The
feature is the easy half. The risk is the other half: each of those literals is
live on every existing agent right now, so a default that resolves to anything
else silently re-tunes every call in production, and nothing would fail.

So these tests are almost all negative. They assert what happens when nothing is
configured, because that is the case nobody will test by hand and the case every
existing agent is in.

The exceptions worth naming:
  - gpt-5 must keep receiving NO temperature however hard you configure one; the
    reasoning models reject the parameter outright.
  - MiniMax rejects 0 and Sarvam wants 0.5, so both keep their own defaults
    rather than inheriting the base field's.
  - RILT, Bedrock and Speaches sent no temperature at all before this, and must
    keep sending none until somebody asks for one.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pipecat.services.settings import NOT_GIVEN

from api.schemas.workflow_configurations import (
    KnowledgeBaseConfigurationDefaults,
    STTTurnConfigurationDefaults,
    VADConfigurationDefaults,
    resolve_knowledge_base_configuration,
)
from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.run_pipeline import (
    _resolve_stt_turn_config,
    _resolve_vad_params,
)
from api.services.pipecat.service_factory import (
    create_llm_service_from_provider,
    create_stt_service,
    create_tts_service,
)


def _audio_config():
    return AudioConfig(transport_in_sample_rate=16000, transport_out_sample_rate=16000)


def _settings(mock):
    return mock.call_args.kwargs["settings"]


# ── the seven providers that shipped on 0.1 ─────────────────────────────────

# (provider, model, patched class, settings attribute holder)
TEMPERATURE_0_1_PROVIDERS = [
    (ServiceProviders.OPENAI.value, "gpt-4.1", "OpenAILLMService"),
    (ServiceProviders.GROQ.value, "llama-3.3-70b-versatile", "GroqLLMService"),
    (ServiceProviders.OPENROUTER.value, "openai/gpt-4.1", "OpenRouterLLMService"),
    (ServiceProviders.GOOGLE.value, "gemini-3.5-flash", "RiltGoogleLLMService"),
    (ServiceProviders.AZURE.value, "gpt-4.1", "AzureLLMService"),
    (
        ServiceProviders.HUGGINGFACE.value,
        "meta-llama/Llama-3.3-70B",
        "HuggingFaceLLMService",
    ),
]


@pytest.mark.parametrize("provider,model,cls", TEMPERATURE_0_1_PROVIDERS)
def test_unconfigured_temperature_stays_at_the_shipped_0_1(provider, model, cls):
    """THE guard for this workstream.

    Every existing agent has no temperature set. If this returns anything but
    0.1, this change quietly re-tuned every conversation in production.
    """
    with patch(f"api.services.pipecat.service_factory.{cls}") as mock:
        create_llm_service_from_provider(provider, model, "k")
    assert _settings(mock).temperature == 0.1


@pytest.mark.parametrize("provider,model,cls", TEMPERATURE_0_1_PROVIDERS)
def test_a_configured_temperature_is_actually_used(provider, model, cls):
    with patch(f"api.services.pipecat.service_factory.{cls}") as mock:
        create_llm_service_from_provider(provider, model, "k", temperature=0.7)
    assert _settings(mock).temperature == 0.7


def test_zero_is_honoured_rather_than_treated_as_unset():
    # 0.0 is falsy and is also the most useful value for deterministic tool
    # calling. An `if temperature:` check anywhere in the chain sends 0.1.
    with patch("api.services.pipecat.service_factory.OpenAILLMService") as mock:
        create_llm_service_from_provider(
            ServiceProviders.OPENAI.value, "gpt-4.1", "k", temperature=0.0
        )
    assert _settings(mock).temperature == 0.0


# ── the models and providers that must NOT receive one ──────────────────────


def test_gpt5_never_receives_a_temperature_however_it_is_configured():
    """Reasoning models reject the parameter, so the dial must not reach them."""
    with patch("api.services.pipecat.service_factory.OpenAILLMService") as mock:
        create_llm_service_from_provider(
            ServiceProviders.OPENAI.value, "gpt-5-mini", "k", temperature=0.7
        )
    settings = _settings(mock)
    assert settings.temperature is NOT_GIVEN
    # and the reasoning knobs it does take are untouched
    assert settings.extra == {"reasoning_effort": "minimal", "verbosity": "low"}


@pytest.mark.parametrize(
    "provider,model,cls",
    [
        (ServiceProviders.RILT.value, "gpt-4.1", "RiltLLMService"),
        (
            ServiceProviders.AWS_BEDROCK.value,
            "anthropic.claude-v2",
            "AWSBedrockLLMService",
        ),
        (ServiceProviders.SPEACHES.value, "llama3", "SpeachesLLMService"),
    ],
)
def test_providers_that_sent_no_temperature_still_send_none(provider, model, cls):
    with patch(f"api.services.pipecat.service_factory.{cls}") as mock:
        create_llm_service_from_provider(provider, model, "k")
    settings = _settings(mock)
    # NOT_GIVEN specifically, not just "not a number": these settings objects
    # serialise an explicit None as a JSON null, which is what the provider
    # rejects. A test that accepts None here cannot tell the omission that is
    # correct from the null that breaks the call.
    assert settings.temperature is NOT_GIVEN


@pytest.mark.parametrize(
    "provider,model,cls",
    [
        (
            ServiceProviders.AWS_BEDROCK.value,
            "anthropic.claude-v2",
            "AWSBedrockLLMService",
        ),
        (ServiceProviders.SPEACHES.value, "llama3", "SpeachesLLMService"),
    ],
)
def test_those_providers_do_send_one_when_asked(provider, model, cls):
    with patch(f"api.services.pipecat.service_factory.{cls}") as mock:
        create_llm_service_from_provider(provider, model, "k", temperature=0.3)
    assert _settings(mock).temperature == 0.3


# ── the two providers with their own defaults ───────────────────────────────


def test_minimax_keeps_its_own_default_of_1_0():
    # MiniMax rejects 0, so it must not inherit the base field's ge=0.0.
    with patch("api.services.pipecat.service_factory.MiniMaxLLMService") as mock:
        create_llm_service_from_provider(
            ServiceProviders.MINIMAX.value, "MiniMax-M2.7", "k"
        )
    # MiniMax builds settings off the class under patch, so the settings object
    # is itself a mock -- assert on what it was constructed with.
    assert mock.Settings.call_args.kwargs["temperature"] == 1.0


def test_sarvam_keeps_its_own_default_of_0_5():
    with patch("api.services.pipecat.service_factory.SarvamLLMService") as mock:
        create_llm_service_from_provider(
            ServiceProviders.SARVAM.value, "sarvam-105b", "k"
        )
    assert _settings(mock).temperature == 0.5


# ── ElevenLabs voice settings ───────────────────────────────────────────────


def _elevenlabs_config(**overrides):
    tts = {
        "provider": ServiceProviders.ELEVENLABS.value,
        "api_key": "k",
        "voice": "21m00Tcm4TlvDq8ikWAM",
        "model": "eleven_flash_v2_5",
        "speed": 1.0,
        "base_url": "https://api.elevenlabs.io",
        "stability": 0.8,
        "similarity_boost": 0.75,
        "style": None,
        "use_speaker_boost": None,
    }
    tts.update(overrides)
    return SimpleNamespace(tts=SimpleNamespace(**tts))


def test_elevenlabs_defaults_match_the_literals_they_replaced():
    with patch("api.services.pipecat.service_factory.ElevenLabsTTSService") as mock:
        create_tts_service(_elevenlabs_config(), _audio_config())
    settings = _settings(mock)
    assert settings.stability == 0.8
    assert settings.similarity_boost == 0.75


def test_elevenlabs_omits_style_and_speaker_boost_when_unset():
    # The settings object distinguishes "not given" from an explicit None, and
    # sending None is not the same as leaving them out.
    with patch("api.services.pipecat.service_factory.ElevenLabsTTSService") as mock:
        create_tts_service(_elevenlabs_config(), _audio_config())
    settings = _settings(mock)
    assert settings.style is NOT_GIVEN
    assert settings.use_speaker_boost is NOT_GIVEN


def test_elevenlabs_sends_the_optional_pair_when_configured():
    with patch("api.services.pipecat.service_factory.ElevenLabsTTSService") as mock:
        create_tts_service(
            _elevenlabs_config(style=0.4, use_speaker_boost=True, stability=0.3),
            _audio_config(),
        )
    settings = _settings(mock)
    assert settings.style == 0.4
    assert settings.use_speaker_boost is True
    assert settings.stability == 0.3


# ── STT end-of-turn dials, on both Flux paths and on nova ───────────────────


def _stt_config(provider, model, **extra):
    stt = {"provider": provider, "api_key": "k", "model": model}
    stt.update(extra)
    return SimpleNamespace(stt=SimpleNamespace(**stt))


TURN = {
    "eot_timeout_ms": 4500,
    "eot_threshold": 0.9,
    "eager_eot_threshold": 0.6,
    "endpointing_ms": 250,
}


def test_deepgram_flux_honours_the_turn_dials():
    cfg = _stt_config("deepgram", "flux-general-multi", language="multi")
    with patch("api.services.pipecat.service_factory.DeepgramFluxSTTService") as mock:
        create_stt_service(cfg, _audio_config(), turn_config=TURN)
    settings = _settings(mock)
    assert settings.eot_threshold == 0.9
    assert settings.eager_eot_threshold == 0.6
    assert settings.eot_timeout_ms == 4500


def test_the_rilt_managed_flux_path_honours_them_too():
    """The same three literals were written out twice; both had to change.

    Missing this branch would mean the dials work on Deepgram and silently do
    nothing for every customer on the managed transcriber.
    """
    # NOT the literal "rilt": ServiceProviders.RILT.value is the frozen wire
    # value "dograh", and a literal falls through to the invalid-provider branch.
    cfg = _stt_config(
        ServiceProviders.RILT.value, "flux-general-multi", language="multi"
    )
    with patch("api.services.pipecat.service_factory.RiltFluxSTTService") as mock:
        create_stt_service(cfg, _audio_config(), turn_config=TURN)
    settings = _settings(mock)
    assert settings.eot_threshold == 0.9
    assert settings.eager_eot_threshold == 0.6
    assert settings.eot_timeout_ms == 4500


def test_deepgram_nova_honours_endpointing():
    cfg = _stt_config("deepgram", "nova-3", language="multi")
    with patch("api.services.pipecat.service_factory.DeepgramSTTService") as mock:
        create_stt_service(cfg, _audio_config(), turn_config=TURN)
    assert _settings(mock).endpointing == 250


def test_stt_without_a_turn_config_keeps_the_shipped_literals():
    cfg = _stt_config("deepgram", "flux-general-multi", language="multi")
    with patch("api.services.pipecat.service_factory.DeepgramFluxSTTService") as mock:
        create_stt_service(cfg, _audio_config())
    settings = _settings(mock)
    assert settings.eot_timeout_ms == 3000
    assert settings.eot_threshold == 0.7
    assert settings.eager_eot_threshold == 0.5

    cfg = _stt_config("deepgram", "nova-3", language="multi")
    with patch("api.services.pipecat.service_factory.DeepgramSTTService") as mock:
        create_stt_service(cfg, _audio_config())
    assert _settings(mock).endpointing == 100


# ── the resolvers ───────────────────────────────────────────────────────────


def test_vad_defaults_match_pipecat():
    params = _resolve_vad_params({})
    assert params.stop_secs == 0.2
    assert params.confidence == 0.7
    assert params.start_secs == 0.2


def test_vad_dials_are_read_when_present():
    params = _resolve_vad_params({"vad_configuration": {"stop_secs": 0.8}})
    assert params.stop_secs == 0.8
    assert params.confidence == 0.7


def test_an_out_of_range_dial_falls_back_instead_of_failing_the_call():
    """These come from a JSON column anything could have written.

    A bad value must degrade to the default, not raise -- otherwise one bad
    edit stops the agent answering the phone at all.
    """
    params = _resolve_vad_params({"vad_configuration": {"stop_secs": 99.0}})
    assert params.stop_secs == 0.2

    turn = _resolve_stt_turn_config({"stt_turn_configuration": {"eot_threshold": 5.0}})
    assert turn["eot_threshold"] == 0.7


def test_a_null_configuration_blob_resolves_to_defaults():
    # Stored configs carry explicit JSON nulls for keys nobody set.
    assert _resolve_vad_params({"vad_configuration": None}).stop_secs == 0.2
    assert (
        _resolve_stt_turn_config({"stt_turn_configuration": None})["endpointing_ms"]
        == 100
    )
    assert (
        resolve_knowledge_base_configuration(
            {"knowledge_base_configuration": None}
        ).chunks_to_retrieve
        == 3
    )


def test_knowledge_base_defaults_preserve_todays_behaviour():
    kb = resolve_knowledge_base_configuration({})
    assert kb.chunks_to_retrieve == 3
    # 0.0 keeps every result, which is what having no filter at all did.
    assert kb.min_similarity == 0.0


def test_the_schema_bounds_are_enforced():
    for model, field, bad in [
        (VADConfigurationDefaults, "stop_secs", 0.01),
        (VADConfigurationDefaults, "confidence", 0.0),
        (STTTurnConfigurationDefaults, "eot_timeout_ms", 100),
        (STTTurnConfigurationDefaults, "endpointing_ms", 5),
        (KnowledgeBaseConfigurationDefaults, "chunks_to_retrieve", 0),
        (KnowledgeBaseConfigurationDefaults, "min_similarity", 1.5),
    ]:
        with pytest.raises(Exception):
            model(**{field: bad})


# ── the similarity floor ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_floor_drops_weak_chunks_but_never_a_full_document():
    """Full-document chunks are chosen by the author, not by a score.

    Their exemption is structural rather than numeric: they are appended before
    the scored loop and the filter lives inside it, so no threshold reaches
    them. The pinned 1.0 is belt-and-braces. This test therefore documents that
    arrangement -- breaking it takes moving the filter to the whole list AND
    dropping the pin, and either alone leaves it passing.

    Worth keeping anyway: a knowledge base whose documents are attached whole
    rather than chunked would silently return nothing, and the agent would
    simply answer as if it had no documents at all.
    """
    from api.services.workflow.tools import knowledge_base as kb

    class _Embedder:
        async def search_similar_chunks(self, **_):
            return [
                {
                    "chunk_text": "weak",
                    "filename": "a.pdf",
                    "similarity": 0.4,
                    "chunk_index": 0,
                },
                {
                    "chunk_text": "strong",
                    "filename": "b.pdf",
                    "similarity": 0.9,
                    "chunk_index": 1,
                },
            ]

    class _Doc:
        document_uuid = "whole"
        filename = "whole.pdf"
        full_text = "the entire document"

    async def _fake_full_text(**_):
        return [_Doc()]

    async def _fake_builder(**_):
        return _Embedder()

    with (
        patch.object(kb, "build_embedding_service", _fake_builder),
        patch.object(kb.db_client, "get_full_text_documents", _fake_full_text),
    ):
        result = await kb._perform_retrieval(
            "q",
            1,
            ["whole", "chunked"],
            3,
            "key",
            min_similarity=0.6,
        )

    texts = [c["text"] for c in result["chunks"]]
    assert "the entire document" in texts, "a pinned full_document chunk was dropped"
    assert "strong" in texts
    assert "weak" not in texts


# ── the chat / realtime split ───────────────────────────────────────────────


def test_every_conversational_llm_config_exposes_temperature():
    """The dial has to exist on the classes the settings UI actually renders.

    Everything else here calls the factory with an explicit temperature, so the
    field could vanish from the schema entirely and only this would notice.
    """
    from api.services.configuration import registry as reg

    chat = [
        reg.OpenAILLMService,
        reg.AtlasCloudLLMService,
        reg.GoogleLLMService,
        reg.GoogleVertexLLMConfiguration,
        reg.GroqLLMService,
        reg.OpenRouterLLMConfiguration,
        reg.AzureLLMService,
        reg.RiltLLMService,
        reg.AWSBedrockLLMConfiguration,
        reg.SpeachesLLMConfiguration,
        reg.HuggingFaceLLMConfiguration,
        reg.MiniMaxLLMConfiguration,
        reg.SarvamLLMConfiguration,
    ]
    for cls in chat:
        assert "temperature" in cls.model_fields, f"{cls.__name__} lost temperature"


def test_realtime_providers_that_reject_temperature_do_not_advertise_one():
    """These four APIs do not accept the parameter.

    They inherit from BaseLLMConfiguration, so putting temperature on that
    shared base -- the obvious place -- shows a dial in the UI for providers
    that cannot use it. That is why BaseChatLLMConfiguration exists.
    """
    from api.services.configuration import registry as reg

    for cls in (
        reg.OpenAIRealtimeLLMConfiguration,
        reg.GrokRealtimeLLMConfiguration,
        reg.UltravoxRealtimeLLMConfiguration,
        reg.AzureRealtimeLLMConfiguration,
    ):
        assert "temperature" not in cls.model_fields, (
            f"{cls.__name__} now advertises a temperature its API rejects"
        )

    # The two that DO support it declare their own field with their own bounds.
    for cls in (
        reg.GoogleRealtimeLLMConfiguration,
        reg.GoogleVertexRealtimeLLMConfiguration,
    ):
        assert "temperature" in cls.model_fields
