"""AICall subclass of pipecat's Gemini Live Vertex AI LLM service.

Diamond inheritance: combines the AICall engine-integration overrides from
:class:`RiltGeminiLiveLLMService` with the Vertex-specific tweaks from
upstream's :class:`GeminiLiveVertexLLMService` (no history config,
``NON_BLOCKING`` tools disabled, service-account credentials).

MRO::

    RiltGeminiLiveVertexLLMService
      -> RiltGeminiLiveLLMService
      -> GeminiLiveVertexLLMService
      -> GeminiLiveLLMService
      -> LLMService
      -> ...
"""

from api.services.pipecat.realtime.gemini_live import RiltGeminiLiveLLMService
from pipecat.services.google.gemini_live.vertex.llm import (
    GeminiLiveVertexLLMService,
)


class RiltGeminiLiveVertexLLMService(
    RiltGeminiLiveLLMService,
    GeminiLiveVertexLLMService,
):
    """Vertex AI variant of Gemini Live with AICall integration quirks."""

    pass


# Guard against MRO regressions: a future refactor that flips inheritance
# order or breaks the diamond would silently bypass the AICall overrides.
_mro = RiltGeminiLiveVertexLLMService.__mro__
assert _mro[1] is RiltGeminiLiveLLMService, (
    f"Expected RiltGeminiLiveLLMService at MRO[1], got {_mro[1]}"
)
assert _mro[2] is GeminiLiveVertexLLMService, (
    f"Expected GeminiLiveVertexLLMService at MRO[2], got {_mro[2]}"
)
del _mro
