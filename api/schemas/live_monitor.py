from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LiveCall(BaseModel):
    run_id: int
    workflow_id: int
    workflow_name: str
    mode: str
    call_type: str
    # The other party: who rang in, or who the agent dialled.
    number: Optional[str] = None
    started_at: datetime
    # The agent step the call is in right now, when one has been reported.
    current_node: Optional[str] = None


class LiveCallsResponse(BaseModel):
    calls: list[LiveCall]
