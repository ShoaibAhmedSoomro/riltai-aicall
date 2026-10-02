"""Denoising: off unless an agent asks, and a bad setting never stops a call."""

import inspect
from unittest.mock import MagicMock

import pytest
from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.audio_config import create_audio_config
from api.services.pipecat.audio_mixer import build_audio_in_filter
from api.services.pipecat.run_pipeline import _resolve_denoising_mode
from api.services.pipecat.transport_setup import create_webrtc_transport

PROVIDERS = ["ari", "cloudonix", "plivo", "telnyx", "twilio", "vobiz", "vonage"]


@pytest.mark.asyncio
async def test_only_rnnoise_builds_a_filter():
    assert isinstance(await build_audio_in_filter("rnnoise"), RNNoiseFilter)
    for off in ("none", None, "", "krisp", "RNNOISE "):
        assert await build_audio_in_filter(off) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected", [("rnnoise", RNNoiseFilter), ("none", type(None)), (None, type(None))])
async def test_the_webrtc_transport_gets_the_filter_it_was_asked_for(mode, expected):
    transport = await create_webrtc_transport(
        MagicMock(), 1, create_audio_config("smallwebrtc"), denoising_mode=mode
    )
    assert isinstance(transport._params.audio_in_filter, expected)


@pytest.mark.parametrize("name", PROVIDERS)
def test_every_telephony_transport_accepts_the_setting(name):
    """The mistake this guards: wiring seven factories and missing the eighth, which
    then silently never denoises."""
    import importlib

    module = importlib.import_module(f"api.services.telephony.providers.{name}.transport")
    assert "denoising_mode" in inspect.signature(module.create_transport).parameters
    assert "audio_in_filter=audio_in_filter" in inspect.getsource(module)


def test_the_setting_is_validated_and_defaults_to_off():
    assert WorkflowConfigurationDefaults().denoising_mode == "none"
    assert WorkflowConfigurationDefaults(denoising_mode="rnnoise").denoising_mode == "rnnoise"
    with pytest.raises(Exception):
        WorkflowConfigurationDefaults(denoising_mode="loud")


def test_a_bad_stored_value_means_off_not_a_failed_call():
    assert _resolve_denoising_mode({"denoising_mode": "rnnoise"}) == "rnnoise"
    assert _resolve_denoising_mode({"denoising_mode": "bogus"}) == "none"
    assert _resolve_denoising_mode({}) == "none"
    assert _resolve_denoising_mode(None) == "none"
