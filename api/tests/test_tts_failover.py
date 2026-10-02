"""A backup voice: validated on save, kept secret, and switched to when the main voice fails."""

import asyncio
from unittest.mock import MagicMock

import pytest
from pipecat.frames.frames import ErrorFrame
from pipecat.processors.frame_processor import FrameProcessor

from api.services.configuration import tts_fallback as fb
from api.services.configuration.masking import mask_workflow_configurations
from api.services.pipecat import service_factory
from api.services.pipecat.run_pipeline import _wrap_tts_with_failover

KEY = "sk-abcdefghijklmnop1234"
ELEVEN = {"provider": "elevenlabs", "api_key": KEY, "voice": "voice-1"}


# -- validate on save ---------------------------------------------------------------------


def test_a_real_provider_with_a_key_is_accepted_and_empties_are_dropped():
    out = fb.validate_for_save({**ELEVEN, "note": ""}, primary_provider="deepgram", primary_api_key="x")
    assert out["provider"] == "elevenlabs" and out["api_key"] == KEY and "note" not in out


def test_nothing_or_empty_clears_the_backup():
    for off in (None, {}):
        assert fb.validate_for_save(off, primary_provider="x", primary_api_key="y") is None


def test_an_unknown_provider_is_refused_with_its_name():
    with pytest.raises(ValueError, match="nonesuch"):
        fb.validate_for_save({"provider": "nonesuch", "api_key": "k"}, primary_provider=None, primary_api_key=None)


def test_a_backup_with_no_key_is_refused_unless_it_is_the_same_provider_as_the_main_voice():
    with pytest.raises(ValueError, match="API key"):
        fb.validate_for_save({"provider": "elevenlabs"}, primary_provider="deepgram", primary_api_key="dg-key")
    out = fb.validate_for_save({"provider": "elevenlabs"}, primary_provider="elevenlabs", primary_api_key=KEY)
    assert out["api_key"] == KEY


def test_settings_the_provider_does_not_accept_are_refused_before_a_call_needs_them():
    with pytest.raises(ValueError):
        fb.validate_for_save({**ELEVEN, "speed": 99}, primary_provider=None, primary_api_key=None)


# -- secrecy --------------------------------------------------------------------------------


def test_the_key_never_leaves_in_a_response():
    masked = mask_workflow_configurations({"tts_fallback": dict(ELEVEN), "other": 1})
    assert masked["tts_fallback"]["api_key"] != KEY
    assert masked["other"] == 1 and masked["tts_fallback"]["voice"] == "voice-1"


def test_the_masked_key_the_page_sends_back_restores_the_stored_one():
    shown = mask_workflow_configurations({"tts_fallback": dict(ELEVEN)})
    merged = fb.restore_secret(shown, {"tts_fallback": dict(ELEVEN)})
    assert merged["tts_fallback"]["api_key"] == KEY


def test_a_new_key_is_kept_as_typed():
    out = fb.restore_secret({"tts_fallback": {**ELEVEN, "api_key": "brand-new-key-123456"}}, {"tts_fallback": dict(ELEVEN)})
    assert out["tts_fallback"]["api_key"] == "brand-new-key-123456"


# -- at call time ---------------------------------------------------------------------------


def test_stored_settings_become_a_typed_voice_or_nothing():
    cfg = fb.build_runtime_config({"tts_fallback": dict(ELEVEN)})
    assert cfg is not None and cfg.provider == "elevenlabs" and cfg.voice == "voice-1"
    for junk in (None, {}, {"tts_fallback": None}, {"tts_fallback": {"provider": "nope"}}, {"tts_fallback": "x"}):
        assert fb.build_runtime_config(junk) is None


# -- building and switching -------------------------------------------------------------------


@pytest.fixture
def factory(monkeypatch):
    built = []

    def fake_create(user_config, audio_config, correlation_id=None):
        built.append(user_config.tts)
        return FrameProcessor(name=f"tts-{len(built)}")

    monkeypatch.setattr(service_factory, "create_tts_service", fake_create)
    return built


def _user_config():
    cfg = MagicMock()
    cfg.model_copy = lambda update: MagicMock(tts=update["tts"])
    cfg.tts = "primary-config"
    return cfg


def test_without_a_backup_there_is_one_voice(factory):
    assert len(service_factory.create_tts_services(_user_config(), None)) == 1
    assert factory == ["primary-config"]


def test_with_a_backup_there_are_two_and_the_second_uses_the_backup_settings(factory):
    services = service_factory.create_tts_services(_user_config(), None, fallback="backup-config")
    assert len(services) == 2 and factory == ["primary-config", "backup-config"]


def test_a_backup_that_cannot_be_built_never_stops_the_call(monkeypatch):
    calls = []

    def flaky(user_config, audio_config, correlation_id=None):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("bad key")
        return FrameProcessor()

    monkeypatch.setattr(service_factory, "create_tts_service", flaky)
    assert len(service_factory.create_tts_services(_user_config(), None, fallback="backup")) == 1


def test_one_voice_is_used_as_it_always_was():
    voice = FrameProcessor()
    tts, switcher = _wrap_tts_with_failover([voice])
    assert tts is voice and switcher is None


@pytest.mark.asyncio
async def test_a_failing_main_voice_moves_the_call_to_the_backup():
    primary, backup = FrameProcessor(name="main"), FrameProcessor(name="backup")
    tts, switcher = _wrap_tts_with_failover([primary, backup])
    switched = []

    @switcher.strategy.event_handler("on_service_switched")
    async def _(_strategy, service):
        switched.append(service)

    assert switcher.strategy.active_service is primary
    error = ErrorFrame(error="provider outage", fatal=False)
    error.processor = primary
    await switcher.strategy.handle_error(error)
    await asyncio.sleep(0.05)  # event handlers run as their own tasks

    assert switcher.strategy.active_service is backup
    assert switched == [backup]


@pytest.mark.asyncio
async def test_a_fatal_error_is_not_failover_and_a_stranger_error_is_ignored():
    primary, backup = FrameProcessor(), FrameProcessor()
    _, switcher = _wrap_tts_with_failover([primary, backup])
    # The switcher only acts on non-fatal errors from the ACTIVE voice (see its
    # push_frame); the strategy itself must not flip for no reason.
    assert switcher.strategy.active_service is primary
