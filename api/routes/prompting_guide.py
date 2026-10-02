"""HTTP view of the voice-prompting guide.

The same topics the MCP tool serves, so the editor can offer "Insert starter
handbook" without a second copy of the text. `starter_template` on a topic is the
ready-to-paste body; `content` is the explanation around it.

Endpoints:
    GET /prompting-guide             -> index of topics
    GET /prompting-guide/{topic_id}  -> one topic in full
"""

from fastapi import APIRouter, Depends, HTTPException

from api.db.models import UserModel
from api.sdk_expose import sdk_expose
from api.services.auth.depends import get_user
from api.services.voice_prompting_guide import get_topic, list_topic_index

router = APIRouter(prefix="/prompting-guide")


@router.get(
    "",
    **sdk_expose(
        method="list_prompting_guide_topics",
        description="List the voice-prompting guide topics (id and title).",
    ),
)
async def list_prompting_guide(_user: UserModel = Depends(get_user)) -> list[dict]:
    return list_topic_index()


@router.get(
    "/{topic_id}",
    **sdk_expose(
        method="get_prompting_guide_topic",
        description="Fetch one voice-prompting topic, including its starter_template when it has one.",
    ),
)
async def get_prompting_guide_topic(
    topic_id: str, _user: UserModel = Depends(get_user)
) -> dict:
    topic = get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Unknown topic: {topic_id!r}")
    return topic.to_deep_dict()
