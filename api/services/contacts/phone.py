"""One definition of "the phone number a contact is known by".

Every contact, suppression and dial check matches on the canonical E.164 string
this returns, so "+14155551234", "+1 (415) 555-1234" and "14155551234" are one
person. It reuses the platform's telephony normaliser rather than adding a second
opinion on what a number is.
"""

from api.utils.telephony_address import normalize_telephony_address


def to_e164(raw: str | None, country_hint: str | None = None) -> tuple[str, str | None] | None:
    """``(e164, country_code)`` for a dialable phone number, or None.

    None means "not a phone number we can match on": empty, a SIP address or
    extension, or digits that cannot be an international number. Never raises --
    a bad cell in a spreadsheet is a rejected row, not a crashed import.
    """
    if not raw or not str(raw).strip():
        return None
    try:
        normalized = normalize_telephony_address(str(raw), country_hint)
    except ValueError:
        return None
    if normalized.address_type != "pstn":
        return None
    e164 = normalized.canonical
    # No country calling code begins with 0, so "+0501234567" is a local number
    # that was never given a country, not an international one. Accepting it would
    # file the same person under two keys the moment a country hint is supplied.
    if len(e164) < 2 or e164[1] == "0":
        return None
    return e164, normalized.country_code
