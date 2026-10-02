"""A tiny in-memory stand-in for the slice of Redis the live monitor uses.

Streams (XADD/XRANGE/XREAD), EXPIRE/EXISTS/SET and pipelines. Enough to exercise the
monitor without a server, and small enough to read. Not a general fake.
"""

import asyncio
import itertools


class FakeRedis:
    def __init__(self):
        self.streams: dict[str, list[tuple[str, dict]]] = {}
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.xadd_calls: list[tuple[str, dict, dict]] = []
        self._ids = itertools.count(1)

    # -- commands -----------------------------------------------------------------
    async def xadd(self, key, fields, maxlen=None, approximate=True):
        self.xadd_calls.append((key, dict(fields), {"maxlen": maxlen}))
        entry_id = f"{next(self._ids)}-0"
        stream = self.streams.setdefault(key, [])
        stream.append((entry_id, dict(fields)))
        if maxlen is not None and len(stream) > maxlen:
            del stream[: len(stream) - maxlen]
        return entry_id

    async def expire(self, key, seconds):
        self.ttls[key] = seconds
        return 1

    async def get(self, key):
        return self.values.get(key)

    async def exists(self, key):
        return 1 if key in self.values or key in self.streams else 0

    async def set(self, key, value, ex=None):
        self.values[key] = value
        if ex:
            self.ttls[key] = ex
        return True

    async def delete(self, key):
        self.values.pop(key, None)
        self.streams.pop(key, None)
        return 1

    async def xrevrange(self, key, count=None):
        return list(reversed(self.streams.get(key, [])))[:count]

    async def xrange(self, key, min="-", max="+", count=None):
        entries = [e for e in self.streams.get(key, []) if min == "-" or _after(e[0], min, inclusive=True)]
        return entries[:count] if count else entries

    async def xread(self, streams, block=None, count=None):
        out = []
        for key, last in streams.items():
            if last == "$":
                last = self.streams.get(key, [("0-0", {})])[-1][0] if self.streams.get(key) else "0-0"
            new = [e for e in self.streams.get(key, []) if _after(e[0], last)]
            if new:
                out.append((key, new[:count] if count else new))
        if not out and block:
            await asyncio.sleep(0.005)  # a real XREAD would wait; don't spin
        return out

    # -- pipelines ----------------------------------------------------------------
    def pipeline(self, transaction=False):
        return _Pipeline(self)


def _n(entry_id: str) -> int:
    return int(entry_id.split("-")[0])


def _after(entry_id: str, other: str, inclusive: bool = False) -> bool:
    return _n(entry_id) >= _n(other) if inclusive else _n(entry_id) > _n(other)


class _Pipeline:
    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._queued = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def xadd(self, *a, **k):
        self._queued.append(self._redis.xadd(*a, **k))

    def expire(self, *a, **k):
        self._queued.append(self._redis.expire(*a, **k))

    async def execute(self):
        return [await q for q in self._queued]
