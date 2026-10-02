"""A per-run fan-out for live call events, visible from every replica.

Replaces the old one-slot sender registry, which had two faults for monitoring:

* it held ONE websocket sender per run, so a supervisor could not watch a call the
  caller's own browser was already on, and telephony calls (which have no browser
  socket) published nothing at all;
* ``run_pipeline`` looked the sender up exactly once and closed over it, so anyone
  attaching mid-call was invisible to the running pipeline.

``get_or_create_bus`` hands out a STABLE object. Subscribing later is seen by a
pipeline that captured the bus earlier, because both hold the same bus.

Every event is also appended to a Redis stream, ``monitor:events:{run_id}``, which is
what lets a monitor connected to a different replica see the call. A stream rather
than pub/sub because a supervisor joining at minute four must see what was already
said: one XRANGE gives the backfill and one XREAD the tail, from one key.

Nothing here may break a call. Subscriber and Redis failures are swallowed.
"""

from __future__ import annotations

import json
import time
from typing import Awaitable, Callable, Optional

import redis.asyncio as aioredis
from loguru import logger

from api.constants import REDIS_URL

Sender = Callable[[dict], Awaitable[None]]

EVENTS_MAXLEN = 500
EVENTS_TTL_SECONDS = 7200
AUDIO_MAXLEN = 50
AUDIO_TTL_SECONDS = 60
# How long a cached "is anyone listening" answer is trusted. Short, so listening
# starts within a couple of seconds, long enough that a 50 fps audio stream does not
# ask Redis 50 times a second.
LISTEN_FLAG_REFRESH_SECONDS = 2.0


def events_key(run_id: int) -> str:
    return f"monitor:events:{run_id}"


def audio_key(run_id: int) -> str:
    return f"monitor:audio:{run_id}"


def listen_key(run_id: int) -> str:
    return f"monitor:listen:{run_id}"


def meta_key(run_id: int) -> str:
    return f"monitor:meta:{run_id}"


_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


class RunEventBus:
    def __init__(self, run_id: int, redis=None):
        self.run_id = run_id
        self._redis = redis
        self._subscribers: dict[int, Sender] = {}
        self._next_token = 0
        # Turns an event into what may leave the process, or None to keep it in.
        # Set by the pipeline from the run's data policy; the caller's own browser
        # still gets the raw event.
        self._monitor_filter: Optional[Callable[[dict], Optional[dict]]] = None
        self._listen_allowed = True
        self._listen_cached = False
        self._listen_checked_at = 0.0

    # -- subscribers (local: the caller's own browser) -------------------------

    def subscribe(self, sender: Sender) -> int:
        self._next_token += 1
        self._subscribers[self._next_token] = sender
        return self._next_token

    def unsubscribe(self, token: int) -> None:
        """Remove one subscriber. Never tears the run down: a participant leaving
        must not blind the monitors."""
        self._subscribers.pop(token, None)

    # -- publishing -------------------------------------------------------------

    def set_monitor_filter(self, fn: Optional[Callable[[dict], Optional[dict]]]) -> None:
        self._monitor_filter = fn

    async def publish(self, event: dict) -> None:
        for token, sender in list(self._subscribers.items()):
            try:
                await sender(event)
            except Exception as e:
                # One dead socket must not starve the others, or the pipeline.
                logger.debug(f"run {self.run_id}: subscriber {token} failed: {e}")
        await self._append_to_stream(event)

    async def _append_to_stream(self, event: dict) -> None:
        try:
            out = self._monitor_filter(event) if self._monitor_filter else event
            if out is None:
                return
            r = self._redis or get_redis()
            key = events_key(self.run_id)
            async with r.pipeline(transaction=False) as pipe:
                pipe.xadd(
                    key,
                    {"d": json.dumps(out, default=str)},
                    maxlen=EVENTS_MAXLEN,
                    approximate=True,
                )
                pipe.expire(key, EVENTS_TTL_SECONDS)
                await pipe.execute()
        except Exception as e:
            logger.debug(f"run {self.run_id}: could not append to monitor stream: {e}")

    async def publish_meta(self, meta: dict) -> None:
        """What a monitor should know before it connects, e.g. whether listen-in is
        allowed. A key rather than a stream entry so a long call cannot push it out
        of the backfill window."""
        try:
            r = self._redis or get_redis()
            await r.set(meta_key(self.run_id), json.dumps(meta), ex=EVENTS_TTL_SECONDS)
        except Exception as e:
            logger.debug(f"run {self.run_id}: could not publish monitor meta: {e}")

    # -- listen-in audio (demand-gated) ------------------------------------------

    def forbid_listening(self) -> None:
        """This run's data policy does not allow the audio to leave the call."""
        self._listen_allowed = False

    async def audio_wanted(self) -> bool:
        """True only while a supervisor has listen-in switched on for this run."""
        if not self._listen_allowed:
            return False
        now = time.monotonic()
        if now - self._listen_checked_at < LISTEN_FLAG_REFRESH_SECONDS:
            return self._listen_cached
        self._listen_checked_at = now
        try:
            r = self._redis or get_redis()
            self._listen_cached = bool(await r.exists(listen_key(self.run_id)))
        except Exception:
            self._listen_cached = False
        return self._listen_cached

    async def publish_audio(self, direction: str, sample_rate: int, pcm_b64: str) -> None:
        try:
            r = self._redis or get_redis()
            key = audio_key(self.run_id)
            async with r.pipeline(transaction=False) as pipe:
                pipe.xadd(
                    key,
                    {"dir": direction, "sr": str(sample_rate), "pcm": pcm_b64},
                    maxlen=AUDIO_MAXLEN,
                    approximate=True,
                )
                pipe.expire(key, AUDIO_TTL_SECONDS)
                await pipe.execute()
        except Exception as e:
            logger.debug(f"run {self.run_id}: could not tee audio: {e}")


_buses: dict[int, RunEventBus] = {}


def get_or_create_bus(workflow_run_id: int) -> RunEventBus:
    bus = _buses.get(workflow_run_id)
    if bus is None:
        bus = _buses[workflow_run_id] = RunEventBus(workflow_run_id)
    return bus


def unsubscribe(workflow_run_id: int, token: int) -> None:
    """Drop one subscriber if the run still has a bus; never creates one."""
    bus = _buses.get(workflow_run_id)
    if bus is not None:
        bus.unsubscribe(token)


def release_bus(workflow_run_id: int) -> None:
    """Forget the run's bus once its pipeline has ended. The Redis stream stays
    until it expires, so a late viewer still sees how the call ended."""
    _buses.pop(workflow_run_id, None)
