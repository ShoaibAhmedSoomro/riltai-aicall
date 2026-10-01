#!/usr/bin/env python3
"""Host-side maintenance: clear the Docker build cache, on request and on a timer.

Why this runs on the HOST and not inside the API container: pruning needs the
Docker daemon, and handing the API container the Docker socket is root on the
whole machine. The API is the network-facing process; if it were ever
compromised, that would be the entire server. So the app never touches Docker.
Instead:

    the portal button  -->  creates an empty file in ./maintenance/requests/
    this script (cron) -->  sees the file, deletes it, runs ONE fixed command

The file's contents are never read, let alone executed, so there is nothing to
inject through it. The worst anyone with portal access can do is ask for the
same cache clear this script would run anyway.

    maintenance.py tick     every minute from cron: honour a pending request, and
                            refresh the numbers the portal shows if they are stale
    maintenance.py auto     weekly from cron: clear cache older than a week, or
                            everything if the disk is nearly full
    maintenance.py status   refresh the numbers now and print them

Only the BUILD CACHE is ever touched. Never images, containers or volumes: a
build cache is rebuilt on demand (the cost is a slower next build), whereas a
volume holds the database.

Why this exists at all: on 2026-10-01 the build cache had grown to 109 GB and
taken the disk to 81%, from builds that nobody ever cleaned up.
"""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Weekly job keeps a week of cache so routine rebuilds stay fast.
AUTO_KEEP_HOURS = int(os.getenv("MAINT_AUTO_KEEP_HOURS", "168"))
# Above this the disk is a deploy away from failing, so keep nothing.
EMERGENCY_DISK_PERCENT = int(os.getenv("MAINT_EMERGENCY_DISK_PERCENT", "85"))
# `docker system df` walks every cache record, so it is not run every minute.
STATUS_MAX_AGE_SECONDS = 600

_UNITS = {"B": 1, "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12}


def parse_size(text: str) -> int | None:
    """Docker's human sizes ("109.2GB", "36.86kB", "0B") as bytes.

    Docker prints decimal units, so kB is 1000 and not 1024. None for anything
    unrecognisable: a parse failure must read as "unknown", never as 0 bytes.
    """
    m = re.fullmatch(r"\s*([\d.]+)\s*([kKMGT]?B)\s*", text or "")
    if not m:
        return None
    try:
        return int(float(m.group(1)) * _UNITS[m.group(2).upper()])
    except ValueError:
        return None


def docker_env(maint_dir: Path) -> dict[str, str]:
    """The environment to run Docker with: a PRIVATE config directory.

    Found in production on the first real run: `docker builder prune` failed
    with "open /home/ubuntu/.docker/buildx/.lock: permission denied". Deploys
    run `sudo docker compose build`, which leaves root-owned files in the
    deploying user's ~/.docker, and a cron job running as that user then cannot
    open them. The daemon (and so the build cache) is the same whichever config
    directory the client uses, so pointing this script at one it owns removes
    the whole class of problem instead of fixing the current ownership and
    waiting for the next deploy to break it again.
    """
    return {**os.environ, "DOCKER_CONFIG": str(Path(maint_dir) / ".docker-config")}


def _real_run(cmd: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    # A missing binary or a hung daemon raises rather than returning a code.
    # Either must come back as a failed result: the caller has already consumed
    # the request, and an exception here would lose the outcome entirely.
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


class Maintenance:
    def __init__(
        self,
        maint_dir: Path,
        run: Callable[[list[str]], tuple[int, str]] = _real_run,
        disk_percent: Callable[[], float] | None = None,
        now: Callable[[], float] = time.time,
    ):
        self.dir = Path(maint_dir)
        self.requests = self.dir / "requests"
        self.status_path = self.dir / "status.json"
        self.request_path = self.requests / "prune-build-cache"
        self._run = run
        self._now = now
        self._disk_percent = disk_percent or self._host_disk_percent

    @staticmethod
    def _host_disk_percent() -> float:
        u = shutil.disk_usage("/")
        return u.used / u.total * 100

    # -- reading the world -------------------------------------------------

    def build_cache_bytes(self) -> int | None:
        code, out = self._run(
            ["docker", "system", "df", "--format", "{{.Type}}|{{.Size}}"]
        )
        if code != 0:
            return None
        for line in out.splitlines():
            kind, _, size = line.partition("|")
            if kind.strip() == "Build Cache":
                return parse_size(size)
        return None

    # -- status file -------------------------------------------------------

    def _read_status(self) -> dict:
        try:
            data = json.loads(self.status_path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_status(self, patch: dict) -> None:
        data = {**self._read_status(), **patch}
        data["updated_at"] = datetime.fromtimestamp(
            self._now(), timezone.utc
        ).isoformat()
        data["policy"] = {
            "auto_keep_hours": AUTO_KEEP_HOURS,
            "emergency_disk_percent": EMERGENCY_DISK_PERCENT,
        }
        # Temp file then rename: the portal reads this at any moment, and a
        # half-written file would parse as corrupt or, worse, as empty.
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.chmod(0o644)
        os.replace(tmp, self.status_path)

    def refresh_status(self) -> None:
        self._write_status({"build_cache_bytes": self.build_cache_bytes()})

    def _status_is_stale(self) -> bool:
        try:
            age = self._now() - self.status_path.stat().st_mtime
        except OSError:
            return True
        return age > STATUS_MAX_AGE_SECONDS

    # -- the one destructive action ----------------------------------------

    def prune(self, *, source: str, older_than_hours: int | None) -> dict:
        before = self.build_cache_bytes()
        cmd = ["docker", "builder", "prune", "-af"]
        if older_than_hours is not None:
            cmd += ["--filter", f"until={older_than_hours}h"]
        code, out = self._run(cmd)
        after = self.build_cache_bytes()

        # Freed = cache before minus cache after. Disk usage would be simpler
        # but moves for unrelated reasons (logs, other containers) and would
        # report a number that this action did not cause. Unknown stays None.
        freed = before - after if before is not None and after is not None else None
        record = {
            "at": datetime.fromtimestamp(self._now(), timezone.utc).isoformat(),
            "source": source,
            "ok": code == 0,
            "freed_bytes": freed,
            "error": None if code == 0 else out.strip()[-300:] or f"exit {code}",
            "older_than_hours": older_than_hours,
        }
        self._write_status({"build_cache_bytes": after, "last_prune": record})
        return record

    # -- entry points ------------------------------------------------------

    def tick(self) -> str:
        if self.request_path.exists():
            # Removed BEFORE acting, not after. If the prune crashed this
            # process, leaving the file would re-run it every minute forever.
            # A failed attempt is recorded in last_prune instead, where the
            # person who asked can see it.
            self.request_path.unlink(missing_ok=True)
            self.prune(source="manual", older_than_hours=None)
            return "pruned"
        if self._status_is_stale():
            self.refresh_status()
            return "refreshed"
        return "idle"

    def auto(self) -> str:
        if self._disk_percent() >= EMERGENCY_DISK_PERCENT:
            self.prune(source="auto-emergency", older_than_hours=None)
            return "emergency"
        self.prune(source="auto", older_than_hours=AUTO_KEEP_HOURS)
        return "weekly"


def _locked(maint_dir: Path):
    """One run at a time: a slow prune must not overlap the next minute's tick."""
    maint_dir.mkdir(parents=True, exist_ok=True)
    handle = open(maint_dir / ".lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return None
    return handle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["tick", "auto", "status"])
    args = parser.parse_args(argv)

    maint_dir = Path(
        os.getenv("MAINTENANCE_DIR")
        or Path(__file__).resolve().parent.parent / "maintenance"
    )
    lock = _locked(maint_dir)
    if lock is None:
        print("another maintenance run is in progress", file=sys.stderr)
        return 0

    env = docker_env(maint_dir)
    Path(env["DOCKER_CONFIG"]).mkdir(parents=True, exist_ok=True)
    m = Maintenance(maint_dir, run=lambda cmd: _real_run(cmd, env=env))
    if args.command == "status":
        m.refresh_status()
        print(json.dumps(m._read_status(), indent=2))
    else:
        print(getattr(m, args.command)())
    return 0


if __name__ == "__main__":
    sys.exit(main())
