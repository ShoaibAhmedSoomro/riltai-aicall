#!/usr/bin/env python
"""Fail if the migration graph has more than one head.

Why this is a gate and not a lint: migrations run inside the api container's
own CMD (scripts/start_services_docker.sh) under `set -e`, and the service is
`restart: unless-stopped`. So a second head does not produce a failed deploy
with the old version still serving -- it produces a container that exits on
`alembic upgrade head` and is restarted into the same failure, forever. The
cheapest place to catch that is a red pull request.

Uses alembic's own ScriptDirectory rather than reading the revision files:
merge revisions carry a *tuple* down_revision, and a string-only parse reports
three heads on a graph that actually has one. No database is touched --
api/alembic.ini leaves sqlalchemy.url empty. It does, however, *import* every
revision module, so this needs the api requirements installed (notably
alembic_postgresql_enum), not just alembic.
"""

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

INI = Path(__file__).resolve().parent.parent / "api" / "alembic.ini"


def heads() -> list[str]:
    # script_location is %(here)s/alembic, so this resolves from the ini's own
    # directory and the caller's cwd does not matter.
    return ScriptDirectory.from_config(Config(str(INI))).get_heads()


def main() -> int:
    found = heads()
    if len(found) == 1:
        print(f"One alembic head: {found[0]}")
        return 0
    if not found:
        print(
            "::error::No alembic head found. The versions directory looks empty or unreadable."
        )
        return 1
    print(f"::error::{len(found)} alembic heads: {', '.join(found)}")
    print(
        "Two heads make `alembic upgrade head` fail inside the api container's "
        "entrypoint, which restart: unless-stopped turns into a crash loop in "
        "production. Merge them before this lands:"
    )
    print(f"  alembic -c api/alembic.ini merge -m 'merge heads' {' '.join(found)}")
    return 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        # The check that fails if the logic breaks: a synthetic two-head graph
        # must be rejected, and a merge revision's tuple down_revision must not
        # be miscounted as extra heads. Runs against temp files, never the repo.
        import tempfile
        import textwrap

        def rev(d, name, down, extra=""):
            (d / f"{name}.py").write_text(
                textwrap.dedent(f'''
                """{name}"""
                revision = "{name}"
                down_revision = {down}
                branch_labels = None
                depends_on = None
                {extra}
                def upgrade(): pass
                def downgrade(): pass
            ''')
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "versions").mkdir()
            (root / "env.py").write_text("")
            (root / "script.py.mako").write_text("")
            v = root / "versions"
            cfg = Config()
            cfg.set_main_option("script_location", str(root))

            rev(v, "base", "None")
            rev(v, "a", '"base"')
            got = ScriptDirectory.from_config(cfg).get_heads()
            assert got == ["a"], f"linear graph, got {got}"

            rev(v, "b", '"base"')  # branch: now two heads
            got = ScriptDirectory.from_config(cfg).get_heads()
            assert sorted(got) == ["a", "b"], f"two heads not detected, got {got}"

            rev(v, "m", '("a", "b")')  # merge revision, tuple down_revision
            got = ScriptDirectory.from_config(cfg).get_heads()
            assert got == ["m"], f"tuple down_revision miscounted, got {got}"

        print(
            "self-check passed: linear, branched and merged graphs all counted correctly"
        )
        raise SystemExit(0)
    raise SystemExit(main())
