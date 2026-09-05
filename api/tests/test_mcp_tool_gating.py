"""Every MCP tool is classified, and adding one forces a decision.

`/api/v1/mcp` is a mounted sub-application, not a set of FastAPI routes, so the
`require_admin` dependency that gates the REST surface does not reach it. A tool
added here therefore bypasses, by construction, any gate its REST twin enforces
— and it does so silently, because nothing fails.

That has not bitten yet: all sixteen tools today are member-level work
(authoring workflows and tools, listing the catalogue, reading docs), and none
maps to an admin-gated REST route. `list_credentials` in particular returns only
uuid, name, description and type — no secret values — matching the member-level
`GET /credentials/`.

So this file is a tripwire rather than a fix. The classification below is
exhaustive: a new tool fails these tests until someone decides which side it is
on, at which point `authenticate_mcp_request(require_admin_role=True)` is the
mechanism for the admin side.
"""

import pytest

from api.mcp_server.server import mcp

# Ordinary member work: authoring, reading your own org's catalogue, docs.
MEMBER_TOOLS = {
    "create_workflow",
    "create_tool",
    "get_node_type",
    "get_workflow",
    "get_workflow_code",
    "list_credentials",
    "list_documents",
    "list_node_types",
    "list_recordings",
    "list_tools",
    "list_workflows",
    "save_workflow",
    "get_voice_prompting_guide",
    "list_docs",
    "read_doc",
    "search_docs",
}

# Tools whose REST equivalent is admin-gated. Empty today; anything added here
# must pass require_admin_role=True.
ADMIN_TOOLS: set[str] = set()


async def _registered() -> set[str]:
    return {t.name for t in await mcp.list_tools()}


@pytest.mark.asyncio
async def test_every_registered_tool_is_classified():
    """The tripwire. A new tool lands here before it lands in production."""
    registered = await _registered()
    unclassified = registered - MEMBER_TOOLS - ADMIN_TOOLS
    assert not unclassified, (
        f"MCP tool(s) {sorted(unclassified)} are not classified. The MCP surface "
        f"is a mounted sub-app, so require_admin does NOT reach it — decide "
        f"whether each is member-level or needs "
        f"authenticate_mcp_request(require_admin_role=True), then list it in "
        f"this file."
    )


@pytest.mark.asyncio
async def test_the_classification_has_not_gone_stale():
    """Catches a tool being renamed or removed while the list still names it."""
    registered = await _registered()
    stale = (MEMBER_TOOLS | ADMIN_TOOLS) - registered
    assert not stale, f"classified but no longer registered: {sorted(stale)}"


@pytest.mark.asyncio
async def test_admin_tools_actually_ask_for_admin():
    """A tool on the admin list must really pass the flag.

    Listing it is not the gate — the call is. Without this, moving a name into
    ADMIN_TOOLS would look like gating while changing nothing at runtime.
    """
    import inspect

    from api.mcp_server import server as server_mod

    for name in ADMIN_TOOLS:
        fn = getattr(server_mod, name, None)
        assert fn is not None, f"{name} is on the admin list but not importable"
        src = inspect.getsource(inspect.unwrap(fn))
        assert "require_admin_role=True" in src, (
            f"{name} is classified admin but calls authenticate_mcp_request() "
            f"without require_admin_role=True, so it is not actually gated"
        )


def test_the_mechanism_exists_and_delegates_to_the_rest_rule():
    """The primitive the message above tells people to use.

    It must delegate to the same require_admin the REST routes use rather than
    re-deriving the rule, or the two surfaces drift: a superuser passing on one
    and not the other, or a missing membership row meaning admin here and denial
    there.
    """
    import inspect

    from api.mcp_server.auth import authenticate_mcp_request

    sig = inspect.signature(authenticate_mcp_request)
    assert "require_admin_role" in sig.parameters
    assert sig.parameters["require_admin_role"].default is False, (
        "the flag must default to off, or every existing tool silently becomes "
        "admin-only"
    )
    src = inspect.getsource(authenticate_mcp_request)
    assert "require_admin(user)" in src, (
        "the MCP gate must call the REST require_admin, not its own copy"
    )
