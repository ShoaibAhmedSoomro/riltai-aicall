"""PII redaction: what it catches, and just as important what it must leave alone."""

import pytest

from api.services.governance.redaction import redact_events, redact_text, redact_value

ALL = ("phone", "email", "card", "national_id", "address", "dob")


def red(text, cats=ALL):
    return redact_text(text, cats)


@pytest.mark.parametrize(
    "text",
    [
        "call me on +971 50 123 4567 please",
        "my number is 050-123-4567",
        "it's 0501234567",
        "reach me at (415) 555-0132",
        "0 5 0 1 2 3 4 5 6 7",  # speech-to-text often spaces the digits out
    ],
)
def test_phone_numbers_are_redacted(text):
    out, counts = red(text)
    assert "[REDACTED:phone]" in out
    assert counts == {"phone": 1}
    assert "123" not in out and "555" not in out


@pytest.mark.parametrize(
    "text",
    [
        "the date is 2026-10-02",
        "on 02/10/2026 we met",
        "pi is 3.14159",
        "that costs 1,000,000 dirhams",
        "order 12345",  # too short to be a phone
        "see section 4.2.1 of the policy",
    ],
)
def test_things_that_look_numeric_but_are_not_phones_are_left_alone(text):
    out, counts = red(text)
    assert out == text and counts == {}


def test_a_valid_card_is_redacted():
    out, counts = red("my card is 4111 1111 1111 1111 expiring soon")
    assert "4111" not in out
    assert counts == {"card": 1}


def test_a_long_number_that_fails_luhn_is_not_a_card():
    """An order or reference number that happens to be 16 digits is not a card,
    and eating it would damage the transcript for no privacy gain."""
    text = "reference 1234 5678 9012 3456 please"
    out, counts = red(text)
    assert out == text and "card" not in counts


def test_emails_are_redacted_and_their_digits_are_not_read_as_a_phone():
    out, counts = red("write to sam.lee1234567@example.com")
    assert out == "write to [REDACTED:email]"
    assert counts == {"email": 1}


@pytest.mark.parametrize(
    "text,gone",
    [
        ("emirates id 784-1990-1234567-1", "1234567"),
        ("ssn 123-45-6789", "6789"),
        ("cnic 35202-1234567-1", "1234567"),
        ("my passport number is X1234567", "X1234567"),
    ],
)
def test_national_ids_are_redacted(text, gone):
    out, counts = red(text)
    assert gone not in out
    assert counts.get("national_id") == 1


def test_a_date_is_a_date_of_birth_only_with_a_birth_cue():
    out, counts = red("I was born on 14/03/1990 in Dubai")
    assert "1990" not in out and counts == {"dob": 1}
    # The same date with no cue is an ordinary date and must survive: redacting
    # every date would wreck appointment and delivery transcripts.
    plain, plain_counts = red("the delivery is on 14/03/1990")
    assert plain == "the delivery is on 14/03/1990" and plain_counts == {}


def test_written_out_birth_dates_are_caught():
    out, _ = red("date of birth: 3rd March 1985")
    assert "1985" not in out


def test_street_and_unit_addresses_are_redacted():
    out, counts = red("I live at 221 Baker Street and also villa 12")
    assert "Baker" not in out and "villa 12" not in out.lower()
    assert counts.get("address") == 2


def test_only_the_requested_categories_are_applied():
    text = "mail a@b.co or call 050 123 4567"
    out, counts = redact_text(text, ("email",))
    assert out == "mail [REDACTED:email] or call 050 123 4567"
    assert counts == {"email": 1}


def test_no_categories_changes_nothing():
    assert redact_text("a@b.co", ()) == ("a@b.co", {})
    assert redact_text("", ALL) == ("", {})


def test_counts_add_up_across_several_hits():
    out, counts = red("a@b.co, c@d.co and 050 123 4567")
    assert counts == {"email": 2, "phone": 1}


def test_events_are_redacted_in_the_payload_but_never_in_the_envelope():
    events = [
        {
            "type": "rtf-user-transcription",
            "timestamp": "2026-10-02T12:34:56.789+00:00",
            "turn": 3,
            "payload": {"text": "my email is a@b.co", "final": True},
        }
    ]
    out, counts = redact_events(events, ALL)
    assert out[0]["payload"]["text"] == "my email is [REDACTED:email]"
    assert out[0]["payload"]["final"] is True
    assert out[0]["timestamp"] == events[0]["timestamp"]
    assert counts == {"email": 1}
    # the input is not mutated: the caller still holds the raw events
    assert events[0]["payload"]["text"] == "my email is a@b.co"


def test_nested_tool_call_arguments_are_redacted_too():
    out = redact_value({"args": {"to": ["a@b.co"], "n": 5}}, ALL)
    assert out == {"args": {"to": ["[REDACTED:email]"], "n": 5}}


def test_timestamps_inside_a_payload_are_not_mistaken_for_phone_numbers():
    out = redact_value({"timestamp": "2026-10-02 12:34", "text": "hello"}, ALL)
    assert out["timestamp"] == "2026-10-02 12:34"
