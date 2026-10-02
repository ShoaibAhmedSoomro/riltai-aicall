"""A keypress opens a user turn.

On some speech-to-text setups (Deepgram Flux, the managed transcriber) the aggregator
only starts a turn when the transcriber says the caller started speaking. A caller who
presses "1" says nothing, so the DTMFAggregator's "DTMF: 1" transcript would arrive
with no turn open and the agent would never answer it. This strategy opens the turn on
the keypress itself.

Lives in api/ rather than in the pipecat fork: it needs only the public strategy base
class, and the fork is a pinned submodule.
"""

from pipecat.frames.frames import Frame, InputDTMFFrame
from pipecat.turns.types import ProcessFrameResult
from pipecat.turns.user_start.base_user_turn_start_strategy import (
    BaseUserTurnStartStrategy,
)


class DTMFUserTurnStartStrategy(BaseUserTurnStartStrategy):
    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        if isinstance(frame, InputDTMFFrame):
            await self.trigger_user_turn_started()
            return ProcessFrameResult.STOP
        return ProcessFrameResult.CONTINUE
