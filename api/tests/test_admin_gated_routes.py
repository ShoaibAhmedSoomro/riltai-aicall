"""The routes that must require an org admin, pinned.

Gating is a per-route decision applied by hand: FastAPI has no default, every
router declares its own dependencies, and nothing fails when a new route forgets
one. So the set is asserted here rather than trusted to review.

Two directions matter and they are not symmetric.

Under-gating is a security bug: these routes change org-wide credentials,
telephony configuration, API keys and embed tokens, so a plain member reaching
them can spend the org's money, redirect its calls, or mint a token that
outlives their access.

Over-gating is an outage: every one of these was usable by every authenticated
user before roles existed, and "admin" is defined as exactly today's access. A
route gated by mistake takes a working feature away from real users. Three
routes were caught in review for precisely this and are pinned NOT-admin below,
so nobody re-gates them from the original list without reading why.
"""

import pytest
from fastapi.routing import APIRoute

from api.app import app

# Org-wide or destructive. One user reaching these can harm another.
MUST_BE_ADMIN = [
    ("PUT", "/api/v1/credentials/{credential_uuid}"),
    ("DELETE", "/api/v1/credentials/{credential_uuid}"),
    ("PUT", "/api/v1/organizations/model-configurations/v2"),
    ("POST", "/api/v1/organizations/telephony-configs"),
    ("PUT", "/api/v1/organizations/telephony-configs/{config_id}"),
    ("DELETE", "/api/v1/organizations/telephony-configs/{config_id}"),
    ("POST", "/api/v1/organizations/telephony-configs/{config_id}/phone-numbers"),
    ("POST", "/api/v1/organizations/langfuse-credentials"),
    ("DELETE", "/api/v1/organizations/langfuse-credentials"),
    ("POST", "/api/v1/user/api-keys"),
    ("DELETE", "/api/v1/user/api-keys/{api_key_id}"),
    ("PUT", "/api/v1/user/configurations/user"),
    ("POST", "/api/v1/workflow/{workflow_id}/embed-token"),
    ("DELETE", "/api/v1/workflow/{workflow_id}/embed-token"),
    ("PATCH", "/api/v1/organizations/members/{user_id}"),
]

# Ordinary work. Gating any of these locks real users out of a working product.
MUST_NOT_BE_ADMIN = [
    # Written before every test call by PhoneCallDialog, and by the usage page's
    # timezone picker. Admin-gating it stops a member placing a call at all.
    ("PUT", "/api/v1/organizations/preferences"),
    # Reachable inline from the workflow node editor and the HTTP-tool config,
    # behind an "Add new credential" button. Gating it dead-ends tool building
    # with no admin-free path to finish.
    ("POST", "/api/v1/credentials/"),
    # In OSS these mint and archive the caller's OWN per-user keys -- the handler
    # branches on DEPLOYMENT_MODE and passes no organization_id. Gating them
    # stops a member managing keys nobody else can even see.
    ("POST", "/api/v1/user/service-keys"),
    # Knowing who your teammates are is not privileged, and hiding it leaves a
    # member unable to work out who to ask for an admin action.
    ("GET", "/api/v1/organizations/members"),
]


def _dependency_names(route: APIRoute) -> set[str]:
    """Every callable in the route's resolved dependency tree.

    Walked recursively rather than checked one level deep, because require_admin
    itself depends on get_user_with_selected_organization -- a shallow check
    would miss gating applied through any future wrapper.
    """
    seen, stack = set(), [route.dependant]
    while stack:
        d = stack.pop()
        if getattr(d, "call", None) is not None:
            seen.add(getattr(d.call, "__name__", ""))
        stack.extend(d.dependencies)
    return seen


def _route(method: str, path: str) -> APIRoute:
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == path and method in r.methods:
            return r
    raise AssertionError(
        f"{method} {path} is not registered. Every router is hand-included in "
        f"api/routes/main.py -- a missed line there is a silent 404."
    )


@pytest.mark.parametrize("method,path", MUST_BE_ADMIN)
def test_route_requires_an_org_admin(method, path):
    assert "require_admin" in _dependency_names(_route(method, path)), (
        f"{method} {path} is org-wide or destructive but any member can call it"
    )


@pytest.mark.parametrize("method,path", MUST_NOT_BE_ADMIN)
def test_route_stays_open_to_members(method, path):
    names = _dependency_names(_route(method, path))
    assert "require_admin" not in names, (
        f"{method} {path} is ordinary member work; gating it locks real users "
        f"out of a feature that works today. See this file's docstring."
    )
    # Still authenticated, just not admin-only -- "not admin" must never have
    # been achieved by dropping auth altogether.
    assert names & {"get_user", "get_user_with_selected_organization"}, (
        f"{method} {path} has no authentication dependency at all"
    )


def test_the_superuser_routes_are_not_downgraded_to_admin():
    """The one that would have been a cross-tenant breach.

    These were proposed as "admin" during review. Applied literally that is a
    DOWNGRADE: they are superuser-only today, and org admin is every backfilled
    member -- so it would have handed impersonation of any user in any
    organization, and a cross-tenant run listing, to the entire user base.
    """
    for method, path in [
        ("POST", "/api/v1/superuser/impersonate"),
        ("GET", "/api/v1/superuser/workflow-runs"),
    ]:
        names = _dependency_names(_route(method, path))
        assert "get_superuser" in names, f"{method} {path} lost its superuser gate"
        assert "require_admin" not in names, (
            f"{method} {path} was downgraded from superuser to org admin"
        )
