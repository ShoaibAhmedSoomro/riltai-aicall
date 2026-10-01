"""What a finished call is allowed to keep: audio, transcript, redaction.

Drives the real call-end handler, because the privacy promise lives in what it
hands to storage -- a unit test of the policy alone would pass while the handler
ignored it.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.organization_preferences import OrganizationPreferences
from api.services.governance.policy import resolve_governance_policy
from api.services.pipecat import event_handlers
from api.services.pipecat.event_handlers import register_event_handlers
from api.services.pipecat.in_memory_buffers import InMemoryLogsBuffer


class _Source:
    def __init__(self):
        self.handlers = {}

    def event_handler(self, name):
        def deco(fn):
            self.handlers[name] = fn
            return fn

        return deco


def _policy(**cfg):
    return resolve_governance_policy(
        {"governance_configuration": cfg}, OrganizationPreferences()
    )


async def _finish_a_call(monkeypatch, governance, *, context=None):
    """Run one call through connect and finish; return what reached storage."""
    task = _Source()
    task.wait_for_observers = AsyncMock()
    task.turn_trace_observer = None
    transport = _Source()
    audio_buffer = SimpleNamespace(start_recording=AsyncMock(), stop_recording=AsyncMock())
    logs = InMemoryLogsBuffer(1)
    engine = SimpleNamespace(
        get_gathered_context=AsyncMock(return_value=dict(context or {})),
        cleanup=AsyncMock(),
        is_call_disposed=lambda: False,
    )

    saved = {"updates": []}
    upload = AsyncMock()
    monkeypatch.setattr(event_handlers, "upload_workflow_run_artifacts", upload)
    monkeypatch.setattr(event_handlers, "enqueue_job", AsyncMock())
    monkeypatch.setattr(event_handlers, "_capture_call_event", AsyncMock())
    db = event_handlers.db_client
    monkeypatch.setattr(
        db, "get_workflow_run_by_id",
        AsyncMock(return_value=SimpleNamespace(gathered_context={}, workflow_id=1)),
    )
    monkeypatch.setattr(db, "add_call_disposition_code", AsyncMock())

    async def record(**kw):
        saved["updates"].append(kw)

    monkeypatch.setattr(db, "update_workflow_run", record)

    in_memory = register_event_handlers(
        task=task,
        transport=transport,
        workflow_run_id=1,
        engine=engine,
        audio_buffer=audio_buffer,
        in_memory_logs_buffer=logs,
        transcript_log_coordinator=SimpleNamespace(flush=AsyncMock()),
        pipeline_metrics_aggregator=SimpleNamespace(get_all_usage_metrics_serialized=lambda: {}),
        audio_config=SimpleNamespace(pipeline_sample_rate=16000),
        governance=governance,
    )

    await logs.append({"type": "rtf-user-transcription", "payload": {"text": "my email is sam@example.com", "final": True}})
    await logs.append({"type": "rtf-bot-text", "payload": {"text": "thanks sam, call 050 123 4567?"}})
    await logs.append({"type": "rtf-latency-measured", "payload": {"ms": 120}})
    if governance is None or governance.record_audio:
        await in_memory.mixed.append(b"\x01\x00" * 1600)

    await transport.handlers["on_client_connected"](transport, None)
    await task.handlers["on_pipeline_finished"](task, None)

    def stored(key):
        for u in saved["updates"]:
            if key in u:
                return u[key]

    return SimpleNamespace(
        upload=upload.await_args.kwargs if upload.await_args else None,
        started_recording=audio_buffer.start_recording.await_count == 1,
        events=(stored("logs") or {}).get("realtime_feedback_events"),
        extra=stored("extra"),
        context=stored("gathered_context"),
    )


def _texts(events):
    return [e["payload"].get("text") for e in events or [] if "text" in e["payload"]]


@pytest.mark.asyncio
async def test_with_no_policy_the_call_keeps_everything_as_before(monkeypatch):
    r = await _finish_a_call(monkeypatch, None)
    assert r.started_recording
    assert r.upload["mixed_audio_wav"] and r.upload["transcript_text"]
    assert "sam@example.com" in r.upload["transcript_text"]
    assert r.extra is None  # nothing redacted, so nothing recorded about it


@pytest.mark.asyncio
async def test_recording_off_never_starts_it_and_uploads_no_audio(monkeypatch):
    r = await _finish_a_call(monkeypatch, _policy(record_audio=False))
    assert not r.started_recording
    assert r.upload["mixed_audio_wav"] is None
    assert r.upload["user_audio_wav"] is None and r.upload["bot_audio_wav"] is None
    assert r.upload["transcript_text"]  # transcript is a separate switch


@pytest.mark.asyncio
async def test_transcript_off_stores_no_file_and_no_spoken_words_in_the_log(monkeypatch):
    r = await _finish_a_call(monkeypatch, _policy(store_transcript=False))
    assert r.upload["transcript_text"] is None
    assert _texts(r.events) == []  # the words are not smuggled out through the log
    assert any(e["type"] == "rtf-latency-measured" for e in r.events)  # operational events stay
    assert r.upload["mixed_audio_wav"]  # audio is its own switch


@pytest.mark.asyncio
async def test_basic_only_keeps_neither_audio_nor_words(monkeypatch):
    r = await _finish_a_call(monkeypatch, _policy(storage_mode="basic_only"))
    assert not r.started_recording
    assert r.upload["mixed_audio_wav"] is None and r.upload["transcript_text"] is None
    assert _texts(r.events) == []


@pytest.mark.asyncio
async def test_redaction_reaches_the_log_and_the_transcript_file(monkeypatch):
    r = await _finish_a_call(
        monkeypatch, _policy(storage_mode="except_pii", redaction_categories=["email", "phone"])
    )
    assert "sam@example.com" not in r.upload["transcript_text"]
    assert "[REDACTED:email]" in r.upload["transcript_text"]
    assert all("sam@example.com" not in (t or "") for t in _texts(r.events))
    assert all("050 123 4567" not in (t or "") for t in _texts(r.events))
    # and leaves proof the pass ran
    assert r.extra["redaction"]["counts"] == {"email": 1, "phone": 1}
    assert r.extra["redaction"]["categories"] == ["email", "phone"]


@pytest.mark.asyncio
async def test_gathered_context_is_left_alone_unless_asked(monkeypatch):
    ctx = {"customer_email": "sam@example.com"}
    off = await _finish_a_call(
        monkeypatch, _policy(redaction_categories=["email"]), context=ctx
    )
    assert off.context["customer_email"] == "sam@example.com"  # integrations still work

    on = await _finish_a_call(
        monkeypatch,
        _policy(redaction_categories=["email"], redact_gathered_context=True),
        context=ctx,
    )
    assert on.context["customer_email"] == "[REDACTED:email]"


# ── text chat: same policy, same code path ──────────────────────────────────

_CHAT = [
    {"type": "rtf-user-transcription", "payload": {"text": "mail me at sam@example.com", "final": True}},
    {"type": "rtf-bot-text", "payload": {"text": "ok"}},
]


@pytest.mark.asyncio
async def test_text_chat_events_follow_the_same_policy(monkeypatch):
    from api.services.workflow import text_chat_session_service as svc

    monkeypatch.setattr(svc, "build_text_chat_realtime_feedback_events", lambda sd: list(_CHAT))
    monkeypatch.setattr(svc.db_client, "get_organization_id_by_workflow_run_id", AsyncMock(return_value=7))
    monkeypatch.setattr(
        svc.db_client, "get_workflow_run_configurations",
        AsyncMock(return_value={"governance_configuration": {"redaction_categories": ["email"]}}),
    )
    events, policy, counts = await svc._governed_events(5, {})

    assert events[0]["payload"]["text"] == "mail me at [REDACTED:email]"
    assert counts == {"email": 1} and policy is not None


@pytest.mark.asyncio
async def test_text_chat_keeps_its_record_if_the_policy_cannot_be_read(monkeypatch):
    """Failing to look up a setting must not lose the conversation's record."""
    from api.services.workflow import text_chat_session_service as svc

    monkeypatch.setattr(svc, "build_text_chat_realtime_feedback_events", lambda sd: list(_CHAT))
    monkeypatch.setattr(
        svc.db_client, "get_organization_id_by_workflow_run_id",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    events, policy, counts = await svc._governed_events(5, {})

    assert events == _CHAT and policy is None and counts == {}
