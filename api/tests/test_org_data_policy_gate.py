"""Anyone in the org can save preferences; only an admin can change the data policy."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes import organization as routes
from api.schemas.organization_preferences import OrganizationPreferences


def _user(*, superuser=False):
    return SimpleNamespace(selected_organization_id=1, is_superuser=superuser)


@pytest.fixture
def store(monkeypatch):
    state = {"current": OrganizationPreferences(timezone="UTC", data_retention_days=30)}
    saved = AsyncMock(side_effect=lambda org, prefs: prefs)

    async def current(_org):
        return state["current"]

    monkeypatch.setattr(routes, "get_organization_preferences", current)
    monkeypatch.setattr(routes, "upsert_organization_preferences", saved)
    return SimpleNamespace(state=state, saved=saved)


def _role(monkeypatch, role):
    monkeypatch.setattr(routes, "get_org_role", AsyncMock(return_value=role))


@pytest.mark.asyncio
async def test_a_member_can_still_save_the_ordinary_preferences(monkeypatch, store):
    _role(monkeypatch, "member")
    out = await routes.save_preferences(OrganizationPreferences(timezone="Asia/Dubai"), _user())
    assert out.timezone == "Asia/Dubai" and out.data_retention_days == 30  # untouched


@pytest.mark.asyncio
async def test_a_member_cannot_change_the_retention_window(monkeypatch, store):
    _role(monkeypatch, "member")
    with pytest.raises(HTTPException) as exc:
        await routes.save_preferences(OrganizationPreferences(data_retention_days=1), _user())
    assert exc.value.status_code == 403
    store.saved.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_member_echoing_the_policy_back_unchanged_is_not_refused(monkeypatch, store):
    """The existing form sends the whole object; refusing that would break it."""
    _role(monkeypatch, "member")
    echoed = OrganizationPreferences(timezone="Asia/Dubai", data_retention_days=30)
    out = await routes.save_preferences(echoed, _user())
    assert out.timezone == "Asia/Dubai"


@pytest.mark.asyncio
async def test_an_admin_can_change_it_and_can_clear_it(monkeypatch, store):
    _role(monkeypatch, "admin")
    out = await routes.save_preferences(OrganizationPreferences(data_retention_days=90), _user())
    assert out.data_retention_days == 90
    store.state["current"] = out
    cleared = await routes.save_preferences(OrganizationPreferences(data_retention_days=None), _user())
    assert cleared.data_retention_days is None  # None is a legal "keep forever"


@pytest.mark.asyncio
async def test_a_superuser_passes_without_a_membership_row(monkeypatch, store):
    _role(monkeypatch, "member")
    out = await routes.save_preferences(
        OrganizationPreferences(default_storage_mode="basic_only"), _user(superuser=True)
    )
    assert out.default_storage_mode == "basic_only"
