"""Cloudonix keypresses already decode, by inheriting Twilio's serializer.

A parity audit listed Cloudonix as a provider whose serializer ignores DTMF, because
cloudonix.py itself never mentions it. It inherits the Twilio serializer, which does.
This pins that, so a future change to either class cannot silently drop keypresses.
"""

import json

import pytest
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.frames.frames import InputDTMFFrame

from api.services.telephony.providers.cloudonix.serializers import CloudonixFrameSerializer


def _serializer():
    return CloudonixFrameSerializer(
        call_id="c1", stream_sid="s1", domain_id="d1", bearer_token="t"
    )


@pytest.mark.asyncio
async def test_a_keypress_event_becomes_a_keypad_frame():
    frame = await _serializer().deserialize(json.dumps({"event": "dtmf", "dtmf": {"digit": "5"}}))
    assert isinstance(frame, InputDTMFFrame) and frame.button == KeypadEntry.FIVE


@pytest.mark.asyncio
async def test_star_and_pound_decode_and_a_junk_digit_is_dropped():
    s = _serializer()
    star = await s.deserialize(json.dumps({"event": "dtmf", "dtmf": {"digit": "*"}}))
    pound = await s.deserialize(json.dumps({"event": "dtmf", "dtmf": {"digit": "#"}}))
    junk = await s.deserialize(json.dumps({"event": "dtmf", "dtmf": {"digit": "x"}}))
    assert star.button == KeypadEntry.STAR and pound.button == KeypadEntry.POUND and junk is None
