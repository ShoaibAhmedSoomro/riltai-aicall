"""Literal paths must be declared before parameterised siblings.

FastAPI matches routes in declaration order. A literal segment registered
AFTER a parameterised one on the same prefix is unreachable: the parameter
captures it, coercion to int fails, and the caller gets 422. The endpoint
looks broken rather than mis-ordered, which is exactly how
GET /campaign/queue-summary shipped and stayed broken -- every unit test
passed, because the handler itself was fine and simply never ran.

This walks the real app's route table, so it covers routers nobody thought
to check here.
"""

import re

import pytest

from api.app import app

_PARAM = re.compile(r"\{[^}]+\}")


def _segments(path: str) -> list[str]:
    return [p for p in path.split("/") if p]


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_no_literal_route_is_shadowed_by_an_earlier_parameter(method):
    seen: list[list[str]] = []
    shadowed: list[str] = []

    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        if method not in methods:
            continue
        path = getattr(route, "path", "")
        segs = _segments(path)

        for earlier in seen:
            if len(earlier) != len(segs):
                continue
            # An earlier route shadows this one when, segment by segment, it
            # either matches literally or captures with a parameter -- and at
            # least one of those captures a literal this route spells out.
            captures_a_literal = False
            for a, b in zip(earlier, segs):
                if a == b:
                    continue
                if _PARAM.fullmatch(a) and not _PARAM.fullmatch(b):
                    captures_a_literal = True
                    continue
                break
            else:
                if captures_a_literal:
                    shadowed.append(
                        f"{method} {path} is shadowed by /{'/'.join(earlier)}"
                    )
        seen.append(segs)

    assert not shadowed, "Unreachable routes:\n" + "\n".join(shadowed)
