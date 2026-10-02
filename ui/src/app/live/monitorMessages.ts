import type { RealtimeFeedbackMessage } from '@/components/workflow/conversation/types';

/**
 * Turns the monitor socket's events into the messages the shared transcript already
 * renders. It mirrors what useWebSocketRTC does for the caller's own browser, because
 * the server sends supervisors the same `rtf-*` events. It is pure so the rules
 * (interim text replaced, bot words joined, a finished sentence closed) are tested.
 */
export interface MonitorEvent {
    type: string;
    payload?: Record<string, unknown>;
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '');

function stamp(event: MonitorEvent, now: number): string {
    const t = event.payload?.timestamp;
    return typeof t === 'string' ? t : new Date(now).toISOString();
}

function finalizeLastBot(prev: RealtimeFeedbackMessage[]): RealtimeFeedbackMessage[] {
    const last = prev[prev.length - 1];
    if (last && last.type === 'bot-text' && !last.final) {
        return [...prev.slice(0, -1), { ...last, final: true }];
    }
    return prev;
}

export function applyMonitorEvent(
    prev: RealtimeFeedbackMessage[],
    event: MonitorEvent,
    now: number = Date.now(),
): RealtimeFeedbackMessage[] {
    const p = event.payload ?? {};
    const id = `${event.type}-${now}-${prev.length}`;
    const timestamp = stamp(event, now);

    switch (event.type) {
        case 'rtf-user-transcription': {
            // The caller started talking, so the agent's sentence is over; and a
            // newer transcription replaces any interim one.
            const closed = finalizeLastBot(prev).filter(
                (m) => !(m.type === 'user-transcription' && !m.final),
            );
            return [...closed, {
                id, type: 'user-transcription', text: str(p.text), final: p.final !== false, timestamp,
            }];
        }
        case 'rtf-bot-text': {
            const last = prev[prev.length - 1];
            if (last && last.type === 'bot-text' && !last.final) {
                return [...prev.slice(0, -1), { ...last, text: `${last.text} ${str(p.text)}` }];
            }
            return [...prev, { id, type: 'bot-text', text: str(p.text), final: false, timestamp }];
        }
        case 'rtf-bot-stopped-speaking':
            return finalizeLastBot(prev);
        case 'rtf-function-call-start': {
            const callId = str(p.tool_call_id);
            const msgId = callId ? `func-${callId}` : id;
            if (prev.some((m) => m.id === msgId)) return prev;
            return [...prev, {
                id: msgId, type: 'function-call', text: str(p.function_name) || 'tool',
                functionName: str(p.function_name) || 'tool', toolCallId: callId || undefined,
                arguments: p.arguments, status: 'running', timestamp,
            }];
        }
        case 'rtf-function-call-end': {
            const msgId = `func-${str(p.tool_call_id)}`;
            return prev.map((m) =>
                m.id === msgId
                    ? { ...m, status: 'completed' as const, result: p.result, text: str(p.result) || m.text }
                    : m,
            );
        }
        case 'rtf-node-transition': {
            const name = str(p.node_name) || 'Step';
            return [...prev, {
                id, type: 'node-transition', text: name, nodeId: str(p.node_id) || undefined,
                nodeName: name, previousNodeId: str(p.previous_node_id) || undefined,
                previousNode: str(p.previous_node_name) || undefined,
                allowInterrupt: typeof p.allow_interrupt === 'boolean' ? p.allow_interrupt : undefined,
                timestamp,
            }];
        }
        case 'rtf-pipeline-error':
            return [...prev, {
                id, type: 'pipeline-error', text: str(p.error) || 'Pipeline error',
                fatal: p.fatal === true, processor: str(p.processor) || undefined, timestamp,
            }];
        default:
            // Latency, mute state, speaking state and anything newer: not transcript.
            return prev;
    }
}

export function applyMonitorEvents(
    prev: RealtimeFeedbackMessage[],
    events: MonitorEvent[],
    now: number = Date.now(),
): RealtimeFeedbackMessage[] {
    return events.reduce((acc, e, i) => applyMonitorEvent(acc, e, now + i), prev);
}

/** One listen-in audio frame: 1 byte direction (0 caller, 1 agent), 4 bytes sample rate
 *  (big-endian), then raw signed 16-bit little-endian mono PCM. */
export interface AudioFrame {
    direction: 'user' | 'bot';
    sampleRate: number;
    samples: Float32Array;
}

export function parseAudioFrame(buffer: ArrayBuffer): AudioFrame | null {
    if (buffer.byteLength < 7) return null;
    const view = new DataView(buffer);
    const sampleRate = view.getUint32(1, false);
    if (sampleRate < 8000 || sampleRate > 48000) return null;
    const count = Math.floor((buffer.byteLength - 5) / 2);
    const samples = new Float32Array(count);
    for (let i = 0; i < count; i += 1) {
        samples[i] = view.getInt16(5 + i * 2, true) / 32768;
    }
    return { direction: view.getUint8(0) === 0 ? 'user' : 'bot', sampleRate, samples };
}
