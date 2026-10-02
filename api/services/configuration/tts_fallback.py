"""The backup voice an agent switches to when its main voice provider fails.

Stored on the agent's own configuration as ``tts_fallback`` -- {provider, api_key, and
whatever else that provider's voice settings take} -- rather than inside the model
override. That override is rewritten into a different stored shape on every save, which
would drop a field it does not know; this one stays as written.

Three jobs, all pure so they are tested without a server:

* validate a fallback on save, against the same registry the main voice uses;
* keep its API key out of responses, and restore it when the page sends the mask back;
* turn what is stored into a typed voice config at call time, or nothing.

Anything wrong here means "no fallback", never a failed call.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from loguru import logger

from api.services.configuration.masking import _mask_secret_value, is_mask_of
from api.services.configuration.registry import REGISTRY, ServiceType

KEY = "tts_fallback"


def _tts_class(provider: Any):
    return REGISTRY.get(ServiceType.TTS, {}).get(provider)


def validate_for_save(
    fallback: Optional[dict], *, primary_provider: Optional[str], primary_api_key: Any
) -> Optional[dict]:
    """The fallback as it should be stored, or ``ValueError`` with a message for the user.

    ``None`` or an empty dict clears it. A blank key is filled from the main voice only
    when it is the same provider, because that is the one key the organization has
    already given us for that provider.
    """
    if not fallback:
        return None
    if not isinstance(fallback, dict):
        raise ValueError("The backup voice must be an object")

    out = {k: v for k, v in fallback.items() if v not in (None, "")}
    provider = out.get("provider")
    cls = _tts_class(provider)
    if cls is None:
        raise ValueError(f"'{provider}' is not a voice provider this platform supports")

    if not out.get("api_key") and primary_api_key and provider == primary_provider:
        out["api_key"] = primary_api_key

    if not out.get("api_key"):
        raise ValueError("The backup voice needs an API key")
    try:
        cls(**out)
    except Exception as e:
        raise ValueError(f"The backup voice settings are not valid: {_first_line(e)}") from e
    return out


def _first_line(e: Exception) -> str:
    return str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__


def mask_in_place(config: dict) -> None:
    """Mask the backup voice's key in a (copied) workflow configuration."""
    block = config.get(KEY)
    if isinstance(block, dict):
        raw = block.get("api_key")
        if raw:
            block["api_key"] = _mask_secret_value(raw)


def restore_secret(incoming: Optional[dict], existing: Optional[dict]) -> Optional[dict]:
    """Put the stored key back when the page sent the masked one."""
    if not incoming or not isinstance(incoming.get(KEY), dict):
        return incoming
    stored = (existing or {}).get(KEY)
    if not isinstance(stored, dict):
        return incoming
    key = incoming[KEY].get("api_key")
    real = stored.get("api_key")
    if key and real and is_mask_of(key, real):
        merged = copy.deepcopy(incoming)
        merged[KEY]["api_key"] = real
        return merged
    return incoming


def build_runtime_config(run_configs: Optional[dict]):
    """The typed voice config to fall back to, or None. Never raises."""
    block = (run_configs or {}).get(KEY)
    if not isinstance(block, dict) or not block:
        return None
    cls = _tts_class(block.get("provider"))
    if cls is None:
        logger.warning("Ignoring backup voice with unknown provider")
        return None
    try:
        return cls(**block)
    except Exception as e:
        logger.warning(f"Ignoring invalid backup voice: {_first_line(e)}")
        return None
