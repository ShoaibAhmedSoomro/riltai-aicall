"""The host-side cache cleaner: what it must do, and what it must never do.

This script runs from cron as the server's own user and can delete things, so
the properties worth pinning are the ones about restraint:

  * It acts ONLY on a request file that exists, and removes that file first, so
    a crash cannot turn one click into a prune every minute forever.
  * The only thing it ever runs is `docker builder prune`. Never images,
    containers or volumes -- a volume is the database.
  * A failure is recorded where the person who asked can see it, and an unknown
    size stays unknown instead of becoming 0.

Docker is replaced by a recording fake, so nothing here touches a real daemon.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "maintenance.py"
pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not part of this image"
)


def _load():
    spec = importlib.util.spec_from_file_location("maintenance_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


maint = _load() if SCRIPT.exists() else None


class FakeDocker:
    """Records every command. `df` answers shrink after a prune."""

    def __init__(self, cache_before="109.2GB", cache_after="0B", prune_code=0):
        self.calls = []
        self.cache = cache_before
        self._after = cache_after
        self._prune_code = prune_code

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:3] == ["docker", "builder", "prune"]:
            if self._prune_code == 0:
                self.cache = self._after
            return (
                self._prune_code,
                "" if self._prune_code == 0 else "boom: daemon down",
            )
        if cmd[:3] == ["docker", "system", "df"]:
            return 0, f"Images|10.96GB\nBuild Cache|{self.cache}\n"
        raise AssertionError(f"unexpected command: {cmd}")

    def prunes(self):
        return [c for c in self.calls if c[:3] == ["docker", "builder", "prune"]]


def _m(tmp_path, docker=None, disk=20.0, now=1_000_000.0):
    (tmp_path / "requests").mkdir(parents=True, exist_ok=True)
    docker = docker or FakeDocker()
    clock = {"t": now}
    m = maint.Maintenance(
        tmp_path, run=docker, disk_percent=lambda: disk, now=lambda: clock["t"]
    )
    return m, docker, clock


def _status(tmp_path):
    return json.loads((tmp_path / "status.json").read_text())


# ── sizes ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("109.2GB", 109_200_000_000),
        ("4.183MB", 4_183_000),
        ("36.86kB", 36_860),  # Docker's kB is 1000, not 1024
        ("0B", 0),
        ("1.5TB", 1_500_000_000_000),
    ],
)
def test_docker_sizes_parse_as_decimal_units(text, expected):
    assert maint.parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "N/A", "lots", None, "12 parsecs"])
def test_an_unreadable_size_is_unknown_not_zero(text):
    """0 would claim the cache is empty -- or that a prune freed nothing."""
    assert maint.parse_size(text) is None


# ── the request file ────────────────────────────────────────────────────────


def test_nothing_is_pruned_without_a_request(tmp_path):
    m, docker, _ = _m(tmp_path)
    m.refresh_status()
    assert m.tick() == "idle"
    assert docker.prunes() == []


def test_a_request_triggers_exactly_one_prune_and_is_consumed(tmp_path):
    m, docker, _ = _m(tmp_path)
    (tmp_path / "requests" / "prune-build-cache").write_text("")

    assert m.tick() == "pruned"
    assert len(docker.prunes()) == 1
    assert not (tmp_path / "requests" / "prune-build-cache").exists()

    # The next minute must not do it again.
    assert m.tick() == "idle"
    assert len(docker.prunes()) == 1


def test_the_request_file_contents_are_never_used(tmp_path):
    """The portal creates an empty file. Whatever is inside must not influence
    what runs -- this is the whole reason the app needs no Docker access."""
    m, docker, _ = _m(tmp_path)
    (tmp_path / "requests" / "prune-build-cache").write_text(
        "; rm -rf / ; --filter until=0h\n"
    )
    m.tick()
    assert docker.prunes() == [["docker", "builder", "prune", "-af"]]


def test_a_failed_prune_still_consumes_the_request_and_is_recorded(tmp_path):
    """Leaving the file would retry every minute forever. The failure is shown
    to whoever clicked instead."""
    m, docker, _ = _m(tmp_path, docker=FakeDocker(prune_code=1))
    (tmp_path / "requests" / "prune-build-cache").write_text("")

    m.tick()

    assert not (tmp_path / "requests" / "prune-build-cache").exists()
    last = _status(tmp_path)["last_prune"]
    assert last["ok"] is False
    assert "daemon down" in last["error"]
    # A prune that failed freed nothing we can claim: the cache did not shrink.
    assert last["freed_bytes"] == 0


def test_a_prune_reports_how_much_it_freed(tmp_path):
    m, _, _ = _m(tmp_path)
    (tmp_path / "requests" / "prune-build-cache").write_text("")
    m.tick()
    last = _status(tmp_path)["last_prune"]
    assert last["ok"] is True
    assert last["source"] == "manual"
    assert last["freed_bytes"] == 109_200_000_000
    assert _status(tmp_path)["build_cache_bytes"] == 0


def test_freed_bytes_is_unknown_when_the_size_cannot_be_read(tmp_path):
    class Blind(FakeDocker):
        def __call__(self, cmd):
            if cmd[:3] == ["docker", "system", "df"]:
                return 1, "daemon unreachable"
            return super().__call__(cmd)

    m, _, _ = _m(tmp_path, docker=Blind())
    (tmp_path / "requests" / "prune-build-cache").write_text("")
    m.tick()
    assert _status(tmp_path)["last_prune"]["freed_bytes"] is None


# ── restraint ───────────────────────────────────────────────────────────────


def test_only_the_build_cache_is_ever_touched(tmp_path):
    """No image, container, volume or system prune, under any path."""
    m, docker, _ = _m(tmp_path, disk=95.0)
    (tmp_path / "requests" / "prune-build-cache").write_text("")
    m.tick()
    m.auto()
    for cmd in docker.calls:
        assert cmd[:3] in (
            ["docker", "builder", "prune"],
            ["docker", "system", "df"],
        ), cmd
    forbidden = {"volume", "image", "container", "system"}
    assert not any(c[1] in forbidden and c[2] != "df" for c in docker.calls), (
        docker.calls
    )


# ── the weekly job ──────────────────────────────────────────────────────────


def test_the_weekly_job_keeps_a_week_of_cache(tmp_path):
    m, docker, _ = _m(tmp_path, disk=40.0)
    assert m.auto() == "weekly"
    assert docker.prunes() == [
        ["docker", "builder", "prune", "-af", "--filter", "until=168h"]
    ]
    assert _status(tmp_path)["last_prune"]["source"] == "auto"


def test_a_nearly_full_disk_keeps_nothing(tmp_path):
    """At this point a retained week of cache is a failed deploy waiting."""
    m, docker, _ = _m(tmp_path, disk=90.0)
    assert m.auto() == "emergency"
    assert docker.prunes() == [["docker", "builder", "prune", "-af"]]
    assert _status(tmp_path)["last_prune"]["source"] == "auto-emergency"


# ── status refresh ──────────────────────────────────────────────────────────


def test_status_is_refreshed_only_when_stale(tmp_path):
    m, docker, clock = _m(tmp_path)
    assert m.tick() == "refreshed"  # nothing there yet
    assert m.tick() == "idle"  # fresh

    import os

    stale = clock["t"] - 700
    os.utime(tmp_path / "status.json", (stale, stale))
    assert m.tick() == "refreshed"


def test_the_status_carries_the_policy_so_the_portal_need_not_guess(tmp_path):
    m, _, _ = _m(tmp_path)
    m.refresh_status()
    assert _status(tmp_path)["policy"] == {
        "auto_keep_hours": 168,
        "emergency_disk_percent": 85,
    }


def test_a_corrupt_status_file_is_replaced_not_fatal(tmp_path):
    m, _, _ = _m(tmp_path)
    (tmp_path / "status.json").write_text("{half a fi")
    m.refresh_status()
    assert "build_cache_bytes" in _status(tmp_path)


# ── the environment it runs docker in ───────────────────────────────────────


def test_docker_runs_with_a_private_config_directory(tmp_path):
    """Found in production: deploys leave root-owned files in ~/.docker, and
    the cron job (a different user) then failed on buildx/.lock. A directory
    this script owns cannot be broken by whatever a deploy does."""
    env = maint.docker_env(tmp_path)
    assert env["DOCKER_CONFIG"] == str(tmp_path / ".docker-config")
    # Everything else is inherited: it still needs PATH to find docker at all.
    assert "PATH" in env


def test_a_missing_docker_binary_is_a_recorded_failure_not_a_crash(monkeypatch):
    """The request is consumed before the prune runs, so an exception here
    would lose the outcome and leave the person who clicked with silence."""

    def boom(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(maint.subprocess, "run", boom)
    code, out = maint._real_run(["docker", "builder", "prune"])
    assert code != 0
    assert "FileNotFoundError" in out


def test_a_hung_daemon_is_a_recorded_failure_not_a_crash(monkeypatch):
    import subprocess

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("docker", 900)

    monkeypatch.setattr(maint.subprocess, "run", hang)
    code, out = maint._real_run(["docker", "builder", "prune"])
    assert code != 0
    assert "TimeoutExpired" in out
