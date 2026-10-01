"""The app's side of server maintenance: read a status file, file a request.

The API never touches Docker. The host runs scripts/maintenance.py from cron,
and the two sides talk through a shared folder (./maintenance, mounted at
/maintenance): the host writes status.json, and the API creates an EMPTY file
in requests/ to ask for a cache clear. See that script for why Docker access is
deliberately kept out of this process.

Everything here degrades to "unknown" rather than guessing. On a deployment
where the folder is not mounted (local development, a different host), the
portal says so instead of offering a button that cannot work.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Any

MAINTENANCE_DIR = Path(os.getenv("MAINTENANCE_DIR", "/maintenance"))
_REQUEST_NAME = "prune-build-cache"


def _requests_dir() -> Path:
    return MAINTENANCE_DIR / "requests"


def is_available() -> bool:
    """Whether a request could actually be picked up.

    Writable, not merely present: a read-only mount would accept the button
    press and then fail, which is worse than not offering it.
    """
    d = _requests_dir()
    return d.is_dir() and os.access(d, os.W_OK)


def read_status() -> dict[str, Any] | None:
    """The host script's last report, or None if there is none or it is unreadable."""
    try:
        data = json.loads((MAINTENANCE_DIR / "status.json").read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def prune_requested() -> bool:
    return (_requests_dir() / _REQUEST_NAME).exists()


def request_prune() -> bool:
    """Ask the host to clear the build cache. True if this call made the request.

    O_EXCL makes "already asked" atomic: two people clicking at once produce one
    request, not a race. The file is empty on purpose -- the host never reads
    it, so there is nothing in it to inject.
    """
    try:
        fd = os.open(
            _requests_dir() / _REQUEST_NAME,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o664,
        )
    except FileExistsError:
        return False
    os.close(fd)
    return True


def disk_usage() -> dict[str, float | int]:
    """The root filesystem. Inside the container this is the host's disk."""
    u = shutil.disk_usage("/")
    return {
        "total_bytes": u.total,
        "used_bytes": u.used,
        "free_bytes": u.free,
        "percent": round(u.used / u.total * 100, 1),
    }
