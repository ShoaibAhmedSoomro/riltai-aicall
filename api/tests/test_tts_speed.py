"""Speed for the voices whose provider accepts it, and only those."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from api.services.configuration.registry import (
    CambTTSConfiguration,
    DeepgramTTSConfiguration,
    LmntTTSConfiguration,
    OpenAITTSService,
    ServiceProviders,
    XAITTSConfiguration,
)
from api.services.pipecat.service_factory import create_tts_service

AUDIO = SimpleNamespace(transport_out_sample_rate=16000, transport_in_sample_rate=16000)


def _openai(**over):
    return SimpleNamespace(
        tts=SimpleNamespace(
            provider=ServiceProviders.OPENAI.value, api_key="k", model="gpt-4o-mini-tts",
            voice="alloy", base_url=None, **over,
        )
    )


def _xai(**over):
    return SimpleNamespace(
        tts=SimpleNamespace(
            provider=ServiceProviders.XAI.value, api_key="k", model="xai-tts",
            voice="eve", language="en", **over,
        )
    )


def _settings(patch_target, config):
    with patch(f"api.services.pipecat.service_factory.{patch_target}") as svc:
        create_tts_service(config, AUDIO)
    return svc.call_args.kwargs["settings"]


def test_defaults_are_normal_speed_and_bounded_by_what_the_provider_accepts():
    assert OpenAITTSService(api_key="k").speed == 1.0
    assert XAITTSConfiguration(api_key="k").speed == 1.0
    for cls, bad in ((OpenAITTSService, (0.1, 4.5)), (XAITTSConfiguration, (0.6, 1.6))):
        for value in bad:
            with pytest.raises(ValidationError):
                cls(api_key="k", speed=value)


def test_providers_that_cannot_change_speed_do_not_offer_it():
    for cls in (DeepgramTTSConfiguration, CambTTSConfiguration, LmntTTSConfiguration):
        assert "speed" not in cls.model_fields, cls.__name__


def test_an_unchanged_speed_sends_nothing_so_existing_agents_sound_the_same():
    from pipecat.services.settings import NOT_GIVEN

    # NOT_GIVEN is pipecat's "unset" marker; a number would mean we sent one.
    assert _settings("OpenAITTSService", _openai()).speed is NOT_GIVEN  # field absent entirely
    assert _settings("OpenAITTSService", _openai(speed=1.0)).speed is NOT_GIVEN
    assert _settings("XAITTSService", _xai(speed=1.0)).speed is NOT_GIVEN


def test_a_changed_speed_reaches_the_service():
    assert _settings("OpenAITTSService", _openai(speed=1.3)).speed == 1.3
    assert _settings("XAITTSService", _xai(speed=0.8)).speed == 0.8
