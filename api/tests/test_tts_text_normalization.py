"""Pronunciation overrides and speech formatting: what the voice is actually given."""

import pytest
from pydantic import ValidationError

from api.schemas.workflow_configurations import (
    PronunciationOverride,
    WorkflowConfigurationDefaults,
)
from api.services.pipecat.text_normalization import (
    build_tts_text_transforms,
    override_pattern,
)


async def speak(configs: dict, text: str) -> str:
    for transform in build_tts_text_transforms(configs):
        text = await transform(text, "sentence")
    return text


def ovr(from_text, to_text, **kw):
    return {"from_text": from_text, "to_text": to_text, **kw}


# -- nothing set means nothing changes ------------------------------------------------------


@pytest.mark.parametrize("configs", [None, {}, {"pronunciation_overrides": []}, {"speech_normalization": {"enabled": False}}])
def test_an_agent_with_neither_feature_gets_no_transforms(configs):
    assert build_tts_text_transforms(configs) == []


@pytest.mark.asyncio
async def test_a_default_agent_hears_its_text_exactly_as_written():
    assert await speak({}, "Your balance is AED 500, call 0501234567.") == "Your balance is AED 500, call 0501234567."


# -- overrides ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_word_is_replaced_by_its_pronunciation():
    out = await speak({"pronunciation_overrides": [ovr("AED", "Dhirhams")]}, "Your balance is AED 500.")
    assert out == "Your balance is Dhirhams 500."


@pytest.mark.asyncio
async def test_whole_word_does_not_touch_the_inside_of_other_words():
    configs = {"pronunciation_overrides": [ovr("cat", "kat")]}
    assert await speak(configs, "A cat, a category, a Cat.") == "A kat, a category, a kat."


@pytest.mark.asyncio
async def test_whole_word_off_replaces_inside_words_too():
    configs = {"pronunciation_overrides": [ovr("cat", "kat", whole_word=False)]}
    assert await speak(configs, "category") == "kategory"


@pytest.mark.asyncio
async def test_match_case_is_respected_when_asked_for():
    configs = {"pronunciation_overrides": [ovr("Rilt", "Rilt-ai", match_case=True)]}
    assert await speak(configs, "Rilt and rilt") == "Rilt-ai and rilt"


@pytest.mark.asyncio
async def test_text_with_symbols_at_its_edges_still_matches_as_a_whole_word():
    configs = {"pronunciation_overrides": [ovr("C++", "see plus plus"), ovr("R&D", "research and development")]}
    assert await speak(configs, "We use C++ in R&D.") == "We use see plus plus in research and development."


@pytest.mark.asyncio
async def test_the_text_is_literal_so_regex_characters_mean_themselves():
    configs = {"pronunciation_overrides": [ovr("a.b", "dot"), ovr("(x+)+y", "boom")]}
    # "axb" must NOT match "a.b"; and the classic catastrophic pattern is just text.
    assert await speak(configs, "axb a.b (x+)+y") == "axb dot boom"
    # ...and a long run that would stall a real pattern engine is instantaneous.
    assert await speak(configs, "x" * 5000) == "x" * 5000


@pytest.mark.asyncio
async def test_the_replacement_is_literal_too():
    configs = {"pronunciation_overrides": [ovr("one", r"\g<0>\1\n")]}
    assert await speak(configs, "one") == r"\g<0>\1\n"


@pytest.mark.asyncio
async def test_overrides_apply_in_the_order_given():
    configs = {"pronunciation_overrides": [ovr("a", "b"), ovr("b", "c")]}
    assert await speak(configs, "a") == "c"


@pytest.mark.asyncio
async def test_an_invalid_stored_override_is_skipped_not_fatal():
    configs = {"pronunciation_overrides": [{"from_text": ""}, ovr("ok", "fine")]}
    assert await speak(configs, "ok") == "fine"


def test_the_pattern_is_built_from_the_flags():
    assert override_pattern(PronunciationOverride(from_text="a.b", to_text="x", whole_word=False, match_case=True)) == r"a\.b"
    assert override_pattern(PronunciationOverride(from_text="ab", to_text="x")).startswith("(?i)")


# -- ordering with acronym spacing ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_override_still_fires_when_acronym_spacing_is_on():
    """The reason overrides are their own transform: formatter-last would see "A E D"."""
    configs = {
        "pronunciation_overrides": [ovr("AED", "dirhams")],
        "speech_normalization": {"enabled": True, "normalize_acronyms": True},
    }
    out = await speak(configs, "Pay in AED.")
    assert "dirhams" in out and "A E D" not in out


def test_overrides_come_before_the_formatter():
    configs = {
        "pronunciation_overrides": [ovr("AED", "dirhams")],
        "speech_normalization": {"enabled": True},
    }
    transforms = build_tts_text_transforms(configs)
    assert len(transforms) == 2 and type(transforms[1]).__name__ == "VoiceFormatter"


@pytest.mark.asyncio
async def test_formatting_alone_expands_what_it_is_asked_to():
    configs = {"speech_normalization": {"enabled": True, "normalize_acronyms": True}}
    assert await speak(configs, "Use the API.") == "Use the A P I."
    off = {"speech_normalization": {"enabled": True, "normalize_acronyms": False}}
    assert await speak(off, "Use the API.") == "Use the API."


# -- the schema ----------------------------------------------------------------------------------------


def test_defaults_change_nothing_and_stored_rows_without_the_keys_still_load():
    cfg = WorkflowConfigurationDefaults()
    assert cfg.pronunciation_overrides == [] and cfg.speech_normalization.enabled is False
    assert WorkflowConfigurationDefaults(**{"max_call_duration": 100}).speech_normalization.enabled is False


def test_overrides_are_bounded():
    for bad in ({"from_text": "", "to_text": "x"}, {"from_text": "x" * 101, "to_text": "y"}, {"from_text": "a", "to_text": "y" * 201}):
        with pytest.raises(ValidationError):
            PronunciationOverride(**bad)
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults(pronunciation_overrides=[ovr("a", "b")] * 201)


def test_text_is_trimmed_and_unknown_keys_are_refused():
    assert PronunciationOverride(from_text="  AED ", to_text=" dirhams ").from_text == "AED"
    with pytest.raises(ValidationError):
        PronunciationOverride(from_text="a", to_text="b", pattern=".*")
