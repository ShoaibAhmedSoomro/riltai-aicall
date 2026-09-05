from fastapi import HTTPException
from fastmcp.server.dependencies import get_http_headers
from opentelemetry import trace

from api.db.models import UserModel
from api.services.auth.depends import _handle_api_key_auth, require_admin


async def authenticate_mcp_request(*, require_admin_role: bool = False) -> UserModel:
    """Resolve the authenticated AICall user for an MCP tool invocation.

    Accepts either `X-API-Key: <key>` or `Authorization: Bearer <key>`,
    reusing the API-key flow from `api.services.auth.depends`.

    Pass ``require_admin_role=True`` for any tool whose REST equivalent is
    gated on ``require_admin``. This surface is a mounted sub-application, not
    a set of FastAPI routes, so a route dependency does not reach it — without
    this a tool added here would bypass a gate its REST twin enforces. No tool
    needs it today; every one of them maps to member-level work.

    It delegates to the same ``require_admin`` used by the REST routes rather
    than re-deriving the rule, so the two cannot drift: superusers pass, and a
    missing membership row resolves to admin (API-key auth sets the org in
    memory without requiring a row to exist).

    Tags the currently-active OTel span with the resolved organization
    and user identifiers. `_OrgRoutingExporter` reads `rilt.org_id`
    at export time to dispatch the span to the right Langfuse project;
    the `langfuse.user.id` / `langfuse.session.id` attributes make the
    span filterable in the Langfuse UI.
    """
    # FastMCP strips Authorization by default unless explicitly included.
    # Preserve it here so Bearer API keys work for MCP tool invocations.
    headers = get_http_headers(include={"authorization"})
    api_key = headers.get("x-api-key")
    if not api_key:
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            api_key = auth.split(" ", 1)[1].strip()
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key — send X-API-Key or Authorization: Bearer <key>",
        )
    user = await _handle_api_key_auth(api_key)

    if require_admin_role:
        # Raises 403 when the caller is not an org admin. Checked after the key
        # resolves a user, because the role is a property of that user in the
        # key's organization -- and re-resolved on every call, so demoting
        # someone takes effect without having to hunt down their API keys.
        await require_admin(user)

    span = trace.get_current_span()
    if span.is_recording():
        org_id = user.selected_organization_id
        # Intentionally NOT `rilt.org_id` — that attribute triggers the
        # per-org Langfuse routing for pipeline spans, and MCP traffic
        # should land in the default (developer-facing) project only.
        # Exposed under `mcp.org_id` for Langfuse UI filtering without
        # affecting the router.
        span.set_attribute("mcp.org_id", str(org_id))
        span.set_attribute("mcp.user_id", str(user.id))
        span.set_attribute("langfuse.user.id", str(user.id))

    return user
