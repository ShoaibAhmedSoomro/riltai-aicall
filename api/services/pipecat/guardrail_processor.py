"""In-call guardrail: screens what the caller says before the agent sees it.

Sits right after speech-to-text. When a final transcription trips a jailbreak
rule (services/governance/screening.py) the configured action runs:

* ``log_only`` -- the words still reach the agent; the attempt is only recorded.
* ``deflect``  -- the words are withheld from the agent and a fixed line is
  spoken instead, so the model never sees the injected instruction.
* ``end_call`` -- as ``deflect``, then the call ends once the line has played.

SCOPE, stated plainly because it is narrower than "guardrails" suggests. This is
the CALLER side only, using fixed patterns, so it adds no model call and no
latency to a turn. It does not screen the agent's replies while the call is live:
doing that means buffering each reply until a classifier has judged it, which
puts a model call on the critical path of every turn. The agent's side is judged
after the call (services/governance/safety_scan.py) and recorded under
``annotations["safety"]``. It is also not wired for realtime (speech-to-speech)
models, which have no transcription stage to screen.

``on_violation`` is how the owner of the call (run_pipeline) records the event
and performs the action's effects; this class only decides and withholds.
"""

from typing import Awaitable, Callable

from loguru import logger

from api.services.governance.screening import looks_like_jailbreak
from pipecat.frames.frames import Frame, TranscriptionFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

DEFLECTION = "I'm sorry, I can't help with that."


class GuardrailProcessor(FrameProcessor):
    def __init__(
        self,
        *,
        action: str,
        on_violation: Callable[[str, str], Awaitable[None]],
        deflection: str = DEFLECTION,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._action = action
        self._on_violation = on_violation
        self._deflection = deflection

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            rule = looks_like_jailbreak(frame.text)
            if rule:
                # Reporting must never break the call: the screen is a safeguard,
                # not a dependency of the conversation.
                try:
                    await self._on_violation(rule, self._action)
                except Exception as exc:
                    logger.error(f"Guardrail violation handler failed: {exc}")

                if self._action != "log_only":
                    await self.push_frame(TTSSpeakFrame(self._deflection), direction)
                    return  # withheld: the agent never sees it

        await self.push_frame(frame, direction)
