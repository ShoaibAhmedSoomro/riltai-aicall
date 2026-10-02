from typing import Literal

from pydantic import BaseModel, Field


class OrganizationPreferences(BaseModel):
    test_phone_number: str | None = None
    timezone: str | None = None
    external_pbx_integrations_enabled: bool = False
    # Organization default for how long a run's recording, transcript and logs
    # are kept. None (the default) means KEEP FOREVER: the purge only ever
    # deletes data somebody deliberately gave a deadline. An agent can override.
    data_retention_days: int | None = Field(default=None, ge=1, le=3650)
    default_storage_mode: Literal["everything", "except_pii", "basic_only"] = (
        "everything"
    )
    # Call outcomes (disposition codes) that mean "do not call this person again".
    # When a call ends with one, the number joins the do-not-call list.
    do_not_call_dispositions: list[str] = Field(default_factory=list, max_length=50)
