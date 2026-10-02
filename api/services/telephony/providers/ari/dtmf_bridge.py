"""Caller keypresses on an Asterisk (ARI) call.

Other providers carry a keypress inside the audio stream, where the serializer turns it
into a frame. Asterisk does not: digits arrive on the ARI *event* socket, which belongs
to ari_manager, a different process from the one running the call's pipeline. Until
this bridge, ari_manager logged the digit and dropped it.

ari_manager already keeps a channel -> run map in Redis, so it publishes the digit on a
per-run channel, and the pipeline process listens on that channel for the life of the
call and queues each digit into the pipeline as a keypress frame.

Best-effort throughout. A lost digit costs the caller one keypress; it must never cost
the call.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from loguru import logger

from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.frames.frames import InputDTMFFrame


def dtmf_channel(workflow_run_id: int | str) -> str:
    return f"ari:dtmf:{workflow_run_id}"


async def publish_digit(redis, workflow_run_id: int | str, digit: str) -> None:
    """Called by ari_manager when the caller presses a key."""
    try:
        await redis.publish(dtmf_channel(workflow_run_id), digit)
    except Exception as e:
        logger.warning(f"Could not forward DTMF digit for run {workflow_run_id}: {e}")


def digit_to_frame(digit) -> InputDTMFFrame | None:
    """A keypress frame for a digit, or None for anything that is not a key."""
    if isinstance(digit, bytes):
        digit = digit.decode("utf-8", "ignore")
    try:
        return InputDTMFFrame(KeypadEntry(str(digit).strip()))
    except ValueError:
        return None


async def run_dtmf_bridge(
    redis,
    workflow_run_id: int,
    queue_frame: Callable[[InputDTMFFrame], Awaitable[None]],
) -> None:
    """Forward this run's digits into the pipeline until cancelled."""
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(dtmf_channel(workflow_run_id))
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            frame = digit_to_frame(message.get("data"))
            if frame is None:
                continue
            try:
                await queue_frame(frame)
            except Exception as e:
                logger.warning(f"Could not queue DTMF for run {workflow_run_id}: {e}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"DTMF bridge for run {workflow_run_id} stopped: {e}")
    finally:
        try:
            await pubsub.unsubscribe(dtmf_channel(workflow_run_id))
            await pubsub.aclose()
        except Exception:
            pass
