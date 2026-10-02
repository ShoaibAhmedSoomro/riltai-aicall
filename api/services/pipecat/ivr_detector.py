"""Hang up when an outbound call is answered by a phone menu instead of a person.

A call that reaches "Press 1 for billing" is not a conversation, and an agent talking
to it wastes the call and the minutes. This watches the first things heard on the call,
asks a small classifier whether it is an automated menu, and fires ``on_ivr_detected``
once if it is.

It does NOT sit in the LLM's way. Transcripts pass straight through to the agent while
the classification runs on the side, so a person is never delayed by a slow classifier;
the cost is that the agent may begin its greeting to a menu before the hang-up lands.

Why not pipecat's IVRNavigator: it occupies the LLM slot of the pipeline and replaces
the whole message list that the node engine owns. This only classifies.

Bounds, so a wrong guess has a ceiling: only the first ``window_secs`` of the call, and
at most ``max_checks`` transcripts. A person who speaks after that is never classified.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

from loguru import logger

from pipecat.extensions.ivr.ivr_navigator import IVRNavigator
from pipecat.frames.frames import Frame, StartFrame, TranscriptionFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

IVR_MARKER = "<mode>ivr</mode>"
CLASSIFY_TIMEOUT_SECONDS = 10.0
DEFAULT_WINDOW_SECONDS = 30.0
DEFAULT_MAX_CHECKS = 4

# The classifier prompt the pipecat fork already ships; reused verbatim so there is one
# definition of what an IVR sounds like.
IVR_CLASSIFIER_PROMPT = IVRNavigator.CLASSIFIER_PROMPT


async def classify_is_ivr(llm, text: str) -> bool:
    """True if the classifier says this transcript is an automated menu."""
    context = LLMContext(messages=[{"role": "user", "content": text}])
    answer = await asyncio.wait_for(
        llm.run_inference(context, max_tokens=20, system_instruction=IVR_CLASSIFIER_PROMPT),
        CLASSIFY_TIMEOUT_SECONDS,
    )
    return IVR_MARKER in (answer or "").lower().replace(" ", "")


class IVRDetectionProcessor(FrameProcessor):
    def __init__(
        self,
        llm,
        *,
        window_secs: float = DEFAULT_WINDOW_SECONDS,
        max_checks: int = DEFAULT_MAX_CHECKS,
        classify: Optional[Callable[[object, str], Awaitable[bool]]] = None,
        clock: Callable[[], float] = time.monotonic,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._llm = llm
        self._window_secs = window_secs
        self._max_checks = max_checks
        self._classify = classify or classify_is_ivr
        self._clock = clock
        self._started_at: Optional[float] = None
        self._checks = 0
        self._detected = False
        self._tasks: set[asyncio.Task] = set()
        self._register_event_handler("on_ivr_detected")

    def _watching(self) -> bool:
        if self._detected or self._checks >= self._max_checks:
            return False
        started = self._started_at
        return started is None or self._clock() - started <= self._window_secs

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._started_at = self._clock()
        elif (
            isinstance(frame, TranscriptionFrame)
            and direction == FrameDirection.DOWNSTREAM
            and frame.text
            and self._watching()
        ):
            self._checks += 1
            task = asyncio.create_task(self._check(frame.text))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        # Never held back: the agent hears everything exactly as before.
        await self.push_frame(frame, direction)

    async def _check(self, text: str) -> None:
        try:
            is_ivr = await self._classify(self._llm, text)
        except Exception as e:
            # A classifier that fails or times out must never end a call.
            logger.warning(f"IVR check failed, ignoring: {e}")
            return
        if is_ivr and not self._detected:
            self._detected = True
            logger.info("IVR menu detected")
            await self._call_event_handler("on_ivr_detected")

    async def cleanup(self):
        await super().cleanup()
        for task in list(self._tasks):
            task.cancel()
