"""A partial PUT to /organizations/preferences must not wipe what it omits.

Every field on OrganizationPreferences has a default, so replacing the blob
wholesale meant a client that sent a subset silently rewrote the rest. The
sharp edge is `external_pbx_integrations_enabled: bool = False` -- it is not
None, so the `exclude_none` applied when writing did not protect it, and a PUT
of just {"timezone": ...} turned external PBX off for the entire organization.

This cannot be fixed client-side: the generated SDK marks every field optional
and the endpoint is public API, so the server can never assume a complete blob.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import organization as org_routes
from api.schemas.organization_preferences import OrganizationPreferences


def _user(org_id=10):
    return SimpleNamespace(id=1, selected_organization_id=org_id, is_superuser=False)


@pytest.fixture
def stored(monkeypatch):
    """An org whose settings are all set to non-default values."""
    current = OrganizationPreferences(
        test_phone_number="+15550100",
        timezone="Asia/Dubai",
        external_pbx_integrations_enabled=True,
    )
    monkeypatch.setattr(
        org_routes, "get_organization_preferences", AsyncMock(return_value=current)
    )
    saved = AsyncMock(side_effect=lambda _org, prefs: prefs)
    monkeypatch.setattr(org_routes, "upsert_organization_preferences", saved)
    return saved


@pytest.mark.asyncio
async def test_setting_only_timezone_keeps_the_other_settings(stored):
    # The exact regression: this used to write external_pbx_integrations_enabled
    # false, because a bool default is not None and so survived exclude_none.
    req = OrganizationPreferences.model_validate({"timezone": "Europe/London"})
    result = await org_routes.save_preferences(req, _user())

    assert result.timezone == "Europe/London"
    assert result.external_pbx_integrations_enabled is True, (
        "external PBX was turned off"
    )
    assert result.test_phone_number == "+15550100", "the test number was wiped"


@pytest.mark.asyncio
async def test_an_explicit_null_still_clears_a_field(stored):
    # The other half, and why this merges on exclude_unset rather than
    # exclude_none: None has to stay a storable "clear this" value. Merging on
    # exclude_none would make test_phone_number permanently unclearable, which
    # would regress behaviour that works today.
    req = OrganizationPreferences.model_validate({"test_phone_number": None})
    result = await org_routes.save_preferences(req, _user())

    assert result.test_phone_number is None, "an explicit null failed to clear"
    assert result.timezone == "Asia/Dubai", "clearing one field disturbed another"
    assert result.external_pbx_integrations_enabled is True


@pytest.mark.asyncio
async def test_turning_the_pbx_flag_off_still_works(stored):
    # Guard against over-correcting: an explicitly sent false must still win.
    req = OrganizationPreferences.model_validate(
        {"external_pbx_integrations_enabled": False}
    )
    result = await org_routes.save_preferences(req, _user())

    assert result.external_pbx_integrations_enabled is False
    assert result.timezone == "Asia/Dubai"


@pytest.mark.asyncio
async def test_a_full_blob_still_replaces_every_field(stored):
    req = OrganizationPreferences.model_validate(
        {
            "test_phone_number": "+15550199",
            "timezone": "UTC",
            "external_pbx_integrations_enabled": False,
        }
    )
    result = await org_routes.save_preferences(req, _user())

    assert result.test_phone_number == "+15550199"
    assert result.timezone == "UTC"
    assert result.external_pbx_integrations_enabled is False
