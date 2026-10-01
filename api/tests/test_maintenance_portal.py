"""The maintenance portal's API: who may use it, and what it can and cannot do.

The portal can ask the host to delete a cache. The properties worth pinning:

  * SUPERUSER ONLY. Every route carries get_superuser. A regular org admin must
    not be able to trigger host actions -- the tier spans every tenant, and the
    host is shared by all of them.
  * "Already asked" is atomic. Two people clicking at once make one request.
  * The app never reads the request back or runs anything: the request file is
    empty and the host ignores its contents.
  * A broken or half-written status file from the host degrades to "unknown";
    it must not turn the whole page into a 500.
"""

import json
import os

import pytest
from fastapi import HTTPException

from api.routes import superuser
from api.services import maintenance
from api.services.auth.depends import get_superuser


@pytest.fixture
def folder(tmp_path, monkeypatch):
    (tmp_path / "requests").mkdir()
    monkeypatch.setattr(maintenance, "MAINTENANCE_DIR", tmp_path)
    return tmp_path


# ── who may call it ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path, method",
    [
        ("/superuser/maintenance", "GET"),
        ("/superuser/maintenance/prune-build-cache", "POST"),
    ],
)
def test_the_routes_require_a_superuser(path, method):
    route = next(
        r
        for r in superuser.router.routes
        if getattr(r, "path", None) == path and method in r.methods
    )
    deps = [d.call for d in route.dependant.dependencies]
    assert get_superuser in deps


# ── the shared folder ───────────────────────────────────────────────────────


def test_a_request_is_an_empty_file(folder):
    assert maintenance.request_prune() is True
    f = folder / "requests" / "prune-build-cache"
    assert f.exists()
    # Empty on purpose: the host never reads it, so nothing can be injected.
    assert f.read_bytes() == b""


def test_asking_twice_makes_one_request(folder):
    assert maintenance.request_prune() is True
    assert maintenance.request_prune() is False
    assert maintenance.prune_requested() is True
    assert len(list((folder / "requests").iterdir())) == 1


def test_unavailable_when_the_folder_is_not_mounted(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, "MAINTENANCE_DIR", tmp_path / "missing")
    assert maintenance.is_available() is False


@pytest.mark.skipif(
    os.name == "nt" or os.geteuid() == 0, reason="needs a non-root POSIX user"
)
def test_a_read_only_folder_is_not_offered(folder):
    """A mount that accepts the button press and then cannot write is worse
    than no button."""
    (folder / "requests").chmod(0o555)
    try:
        assert maintenance.is_available() is False
    finally:
        (folder / "requests").chmod(0o755)


def test_a_missing_status_is_none_not_an_empty_report(folder):
    assert maintenance.read_status() is None


@pytest.mark.parametrize("text", ["{half a fi", "[]", '"a string"', ""])
def test_a_broken_status_file_reads_as_none(folder, text):
    (folder / "status.json").write_text(text)
    assert maintenance.read_status() is None


# ── the endpoints ───────────────────────────────────────────────────────────

USER = type("U", (), {"id": 9})()


@pytest.mark.asyncio
async def test_status_reports_unknown_before_the_host_has_reported(folder):
    res = await superuser.get_maintenance_status(USER)
    assert res.available is True
    assert res.build_cache_bytes is None
    assert res.last_prune is None
    assert res.policy is None
    assert res.prune_requested is False
    assert res.disk.total_bytes > 0


@pytest.mark.asyncio
async def test_status_passes_through_what_the_host_reported(folder):
    (folder / "status.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-10-01T10:00:00+00:00",
                "build_cache_bytes": 5_000,
                "last_prune": {
                    "at": "2026-10-01T09:00:00+00:00",
                    "source": "manual",
                    "ok": True,
                    "freed_bytes": 109_200_000_000,
                    "error": None,
                },
                "policy": {"auto_keep_hours": 168, "emergency_disk_percent": 85},
            }
        )
    )
    res = await superuser.get_maintenance_status(USER)
    assert res.build_cache_bytes == 5_000
    assert res.last_prune.freed_bytes == 109_200_000_000
    assert res.policy.auto_keep_hours == 168


@pytest.mark.asyncio
async def test_a_malformed_section_is_unknown_not_a_500(folder):
    (folder / "status.json").write_text(
        json.dumps({"last_prune": {"at": 5}, "policy": "nope", "build_cache_bytes": 1})
    )
    res = await superuser.get_maintenance_status(USER)
    assert res.last_prune is None
    assert res.policy is None
    assert res.build_cache_bytes == 1


@pytest.mark.asyncio
async def test_requesting_creates_the_file_and_reports_it(folder):
    first = await superuser.request_build_cache_prune(USER)
    second = await superuser.request_build_cache_prune(USER)
    assert first.status == "requested"
    assert second.status == "already_requested"
    assert (await superuser.get_maintenance_status(USER)).prune_requested is True


@pytest.mark.asyncio
async def test_requesting_says_so_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, "MAINTENANCE_DIR", tmp_path / "missing")
    with pytest.raises(HTTPException) as raised:
        await superuser.request_build_cache_prune(USER)
    assert raised.value.status_code == 503
