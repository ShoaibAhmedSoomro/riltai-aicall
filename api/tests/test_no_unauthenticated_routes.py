"""Every route is either authenticated or on this list. Adding one forces a choice.

Auth here is opt-in with no default: not one of the route modules passes
`dependencies=` on its APIRouter, so each protected route repeats the dependency
by hand and **nothing fails when a new one forgets**. That is the gap this
closes.

Why a test rather than a router-level default-deny: 39 routes are legitimately
unauthenticated, including 19 telephony provider webhooks (the carrier has no
session to present), every embed widget session, the public download links, and
the health probes. A blanket default would 401 all of them — breaking live
customer embeds and silently dropping carrier callbacks, which fail in ways
nobody sees until calls stop working. The gap being closed is "someone forgot",
and a test catches that at review time without putting a working product at risk.

Each entry below is a deliberate decision. If you are adding to this list, the
question to answer is: who calls this, and why can they not hold a session?
"""

import pytest
from fastapi.routing import APIRoute

from api.app import app

# Any of these in a route's dependency tree means it is authenticated.
# require_local_auth is deliberately NOT here: it gates on deployment mode, not
# on identity, so counting it would let the login routes masquerade as protected.
AUTH_DEPENDENCIES = {
    "get_user",
    "get_user_with_selected_organization",
    "require_admin",
    "get_superuser",
    "get_user_ws",
}

PUBLIC_BY_DESIGN: dict[str, str] = {
    # Unauthenticated on purpose: the caller has no session to present.
    "/api/v1/auth/login": "issues the session; cannot require one",
    "/api/v1/auth/signup": "creates the account; cannot require one",
    # Note: /auth/session and /auth/logout are Next.js routes under
    # ui/src/app/api/auth/, not FastAPI ones. Listing them here made this
    # list look more complete than it was, which the staleness check caught.
    # Probes. active-calls and autoscale-metric carry their own shared-secret
    # header check (X-Rilt-Devops-Secret) instead of a user session.
    "/api/v1/health": "liveness probe used by compose and the load balancer",
    "/api/v1/health/active-calls": "devops-secret header, not a user session",
    "/api/v1/health/autoscale-metric": "devops-secret header, not a user session",
    # Public artifact links. The token IS the credential, and it now expires.
    "/api/v1/public/download/workflow/{token}/{artifact_type}": "bearer token in the path",
    # Embed widget: anonymous end users on a customer's website.
    "/api/v1/public/embed/init": "anonymous widget bootstrap",
    "/api/v1/public/embed/config/{token}": "embed token is the credential",
    "/api/v1/public/embed/chat/{session_token}": "session token is the credential",
    "/api/v1/public/embed/chat/{session_token}/messages": "session token is the credential",
    "/api/v1/public/embed/chat/{session_token}/end": "session token is the credential",
    "/api/v1/public/embed/turn-credentials/{session_token}": "session token is the credential",
    # Public agent test surfaces, reached by uuid.
    "/api/v1/public/agent/{uuid}": "public agent uuid is the credential",
    "/api/v1/public/agent/test/{uuid}": "public agent uuid is the credential",
    "/api/v1/public/agent/workflow/{workflow_uuid}": "public workflow uuid is the credential",
    "/api/v1/public/agent/test/workflow/{workflow_uuid}": "public workflow uuid is the credential",
    # Static provider registry: JSON schemas only, no organization data.
    "/api/v1/user/configurations/defaults": "static provider schemas, no org data",
}

# Telephony provider webhooks. Carriers post to these with no session; each one
# should verify the provider's own signature instead, which is tracked
# separately -- being on this list means "no user session", not "unverified".
TELEPHONY_WEBHOOK_PREFIXES = (
    "/api/v1/telephony/inbound",
    "/api/v1/telephony/twiml",
    "/api/v1/telephony/twilio/",
    "/api/v1/telephony/plivo-xml",
    "/api/v1/telephony/plivo/",
    "/api/v1/telephony/telnyx/",
    "/api/v1/telephony/vobiz-xml",
    "/api/v1/telephony/vobiz/",
    "/api/v1/telephony/vonage/",
    "/api/v1/telephony/ncco",
    "/api/v1/telephony/cloudonix/",
    "/api/v1/telephony/transfer-result/",
)


def _dependency_names(route: APIRoute) -> set[str]:
    seen, stack = set(), [route.dependant]
    while stack:
        d = stack.pop()
        if getattr(d, "call", None) is not None:
            seen.add(getattr(d.call, "__name__", ""))
        stack.extend(d.dependencies)
    return seen


def _unauthenticated() -> list[APIRoute]:
    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and not (_dependency_names(r) & AUTH_DEPENDENCIES)
    ]


def _is_allowed(path: str) -> bool:
    return path in PUBLIC_BY_DESIGN or path.startswith(TELEPHONY_WEBHOOK_PREFIXES)


def test_no_route_is_unauthenticated_by_accident():
    """The tripwire.

    A new route with no auth dependency fails here rather than shipping open.
    """
    stray = sorted({r.path for r in _unauthenticated() if not _is_allowed(r.path)})
    assert not stray, (
        f"{len(stray)} route(s) have no authentication dependency and are not "
        f"listed as public: {stray}. Auth is opt-in in this codebase, so this is "
        f"most likely an omission. If the route really is public, add it to "
        f"PUBLIC_BY_DESIGN with the reason."
    )


def test_the_public_list_has_not_gone_stale():
    """A path renamed or deleted while still listed hides a real gap later."""
    live = {r.path for r in app.routes if isinstance(r, APIRoute)}
    stale = sorted(p for p in PUBLIC_BY_DESIGN if p not in live)
    assert not stale, f"listed as public but no longer registered: {stale}"


def test_every_public_entry_states_a_reason():
    blank = sorted(p for p, why in PUBLIC_BY_DESIGN.items() if not why.strip())
    assert not blank, f"public without a stated reason: {blank}"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/workflow/templates",
        "/api/v1/organizations/members",
        "/api/v1/user/api-keys",
    ],
)
def test_known_protected_routes_stay_protected(path):
    """A handful pinned directly, so the allow-list cannot be widened to hide them.

    /workflow/templates is here because it read the templates table with no auth
    and no org scoping until this change.
    """
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path == path]
    assert routes, f"{path} is not registered"
    for r in routes:
        assert _dependency_names(r) & AUTH_DEPENDENCIES, f"{path} lost its auth"
