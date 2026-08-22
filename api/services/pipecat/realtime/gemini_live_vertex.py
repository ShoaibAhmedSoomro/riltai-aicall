"""Social Cangaroo subclass of pipecat's Gemini Live Vertex AI LLM service.

Diamond inheritance: combines the Social Cangaroo engine-integration overrides from
:class:`SocialCangarooGeminiLiveLLMService` with the Vertex-specific tweaks from
upstream's :class:`GeminiLiveVertexLLMService` (no history config,
``NON_BLOCKING`` tools disabled, service-account credentials).

MRO::

    SocialCangarooGeminiLiveVertexLLMService
      -> SocialCangarooGeminiLiveLLMService
      -> GeminiLiveVertexLLMService
      -> GeminiLiveLLMService
      -> LLMService
      -> ...
"""

from api.services.pipecat.realtime.gemini_live import SocialCangarooGeminiLiveLLMService
from pipecat.services.google.gemini_live.vertex.llm import (
    GeminiLiveVertexLLMService,
)


class SocialCangarooGeminiLiveVertexLLMService(
    SocialCangarooGeminiLiveLLMService,
    GeminiLiveVertexLLMService,
):
    """Vertex AI variant of Gemini Live with Social Cangaroo integration quirks."""

    pass


# Guard against MRO regressions: a future refactor that flips inheritance
# order or breaks the diamond would silently bypass the Social Cangaroo overrides.
_mro = SocialCangarooGeminiLiveVertexLLMService.__mro__
assert _mro[1] is SocialCangarooGeminiLiveLLMService, (
    f"Expected SocialCangarooGeminiLiveLLMService at MRO[1], got {_mro[1]}"
)
assert _mro[2] is GeminiLiveVertexLLMService, (
    f"Expected GeminiLiveVertexLLMService at MRO[2], got {_mro[2]}"
)
del _mro
