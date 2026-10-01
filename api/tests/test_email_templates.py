"""The email layout: what could go wrong in a message that arrives from us.

An email is the one place where this product's own domain vouches for the
content. So the properties worth pinning are the ones that would turn that
trust against the reader: markup injected through a name, a link that is not a
web link, and a message whose plain-text half is missing the one thing the
reader needs.
"""

import pytest

from api.services.email_templates import render_email

URL = "https://aicall.rilt.ai/auth/reset-password?token=abc.def.ghi"


def _msg(**over):
    args = dict(
        preheader="pre",
        heading="Hello",
        paragraphs=["Body."],
        cta_label="Go",
        cta_url=URL,
    )
    args.update(over)
    return render_email(**args)


def test_user_controlled_text_cannot_inject_markup():
    """The inviter's display name goes straight into an HTML email."""
    evil = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    msg = _msg(paragraphs=[f"{evil} invited you."], heading=evil, preheader=evil)
    assert "<script>" not in msg.html
    assert "<img src=x" not in msg.html
    assert "&lt;script&gt;" in msg.html


def test_an_attribute_cannot_be_broken_out_of():
    """A quote in the URL must not close href and start a new attribute."""
    msg = _msg(cta_url='https://x.test/a?b="onmouseover="alert(1)')
    assert 'href="https://x.test/a?b="onmouseover' not in msg.html
    assert "&quot;" in msg.html


@pytest.mark.parametrize(
    "bad",
    [
        "javascript:alert(1)",
        "data:text/html,<b>x</b>",
        "file:///etc/passwd",
        "//evil.test",
    ],
)
def test_a_link_that_is_not_http_is_refused_outright(bad):
    """Failing is correct here: a quietly-dropped button would send a reset
    email with nothing to click, which looks like success."""
    with pytest.raises(ValueError):
        _msg(cta_url=bad)


def test_the_plain_text_part_carries_the_link():
    """Text-only clients and scanners that strip HTML still need the link."""
    msg = _msg()
    assert URL in msg.text
    assert "Hello" in msg.text and "Body." in msg.text
    assert "<" not in msg.text


def test_the_link_is_printed_in_full_under_the_button():
    """Mail scanners rewrite and disable buttons; a link you cannot copy is a
    locked-out user."""
    assert msg_count(_msg().html, URL) >= 2


def msg_count(haystack: str, needle: str) -> int:
    return haystack.count(needle.replace("&", "&amp;"))


def test_a_message_without_a_button_is_valid():
    msg = _msg(cta_label=None, cta_url=None)
    assert "btn-link" not in msg.html.split("</style>")[1]
    assert "Go" not in msg.text.split("\n")[-3:]


def test_a_label_without_a_url_is_a_programming_error():
    with pytest.raises(ValueError):
        _msg(cta_url=None)


def test_dark_mode_and_the_preheader_are_present():
    html = _msg().html
    assert "prefers-color-scheme: dark" in html
    assert 'name="color-scheme"' in html
    assert "pre" in html.split("<body")[1].split("<table")[0]


def test_nothing_is_fetched_from_the_network():
    """Remote images are blocked by default in many clients; the brand is text
    so the first open never shows a broken-image box."""
    assert "<img" not in _msg().html
    assert "url(" not in _msg().html
