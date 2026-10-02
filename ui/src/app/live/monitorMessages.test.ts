import { describe, expect, it } from 'vitest';

import type { RealtimeFeedbackMessage } from '@/components/workflow/conversation/types';

import { applyMonitorEvent, applyMonitorEvents, parseAudioFrame } from './monitorMessages';

const run = (events: { type: string; payload?: Record<string, unknown> }[]): RealtimeFeedbackMessage[] =>
    applyMonitorEvents([], events, 1000);

describe('transcript messages from monitor events', () => {
    it('joins the agent’s words into one sentence until it stops speaking', () => {
        const out = run([
            { type: 'rtf-bot-text', payload: { text: 'Hello' } },
            { type: 'rtf-bot-text', payload: { text: 'there' } },
        ]);
        expect(out).toHaveLength(1);
        expect(out[0].text).toBe('Hello there');
        expect(out[0].final).toBe(false);

        const done = applyMonitorEvent(out, { type: 'rtf-bot-stopped-speaking' });
        expect(done[0].final).toBe(true);
    });

    it('starts a new sentence after one has finished', () => {
        const out = run([
            { type: 'rtf-bot-text', payload: { text: 'One' } },
            { type: 'rtf-bot-stopped-speaking' },
            { type: 'rtf-bot-text', payload: { text: 'Two' } },
        ]);
        expect(out.map((m) => m.text)).toEqual(['One', 'Two']);
    });

    it('a caller line closes the agent’s sentence and replaces interim text', () => {
        const out = run([
            { type: 'rtf-bot-text', payload: { text: 'Can I help?' } },
            { type: 'rtf-user-transcription', payload: { text: 'yes pl', final: false } },
            { type: 'rtf-user-transcription', payload: { text: 'yes please', final: true } },
        ]);
        expect(out.map((m) => [m.type, m.text, m.final])).toEqual([
            ['bot-text', 'Can I help?', true],
            ['user-transcription', 'yes please', true],
        ]);
    });

    it('tracks a tool call from start to result, once', () => {
        const start = { type: 'rtf-function-call-start', payload: { function_name: 'lookup', tool_call_id: 't1', arguments: { a: 1 } } };
        const out = run([start, start, { type: 'rtf-function-call-end', payload: { tool_call_id: 't1', result: 'found' } }]);
        expect(out).toHaveLength(1);
        expect(out[0]).toMatchObject({ type: 'function-call', status: 'completed', result: 'found' });
    });

    it('records step changes and errors', () => {
        const out = run([
            { type: 'rtf-node-transition', payload: { node_id: 'n2', node_name: 'Qualify', previous_node_name: 'Greeting' } },
            { type: 'rtf-pipeline-error', payload: { error: 'TTS failed', fatal: true } },
        ]);
        expect(out[0]).toMatchObject({ type: 'node-transition', nodeName: 'Qualify', previousNode: 'Greeting' });
        expect(out[1]).toMatchObject({ type: 'pipeline-error', text: 'TTS failed', fatal: true });
    });

    it('ignores events that are not transcript, so a newer server never breaks the page', () => {
        const base = run([{ type: 'rtf-bot-text', payload: { text: 'x' } }]);
        for (const type of ['rtf-latency-measured', 'rtf-user-mute-started', 'rtf-something-new']) {
            expect(applyMonitorEvent(base, { type })).toBe(base);
        }
    });

    it('never throws on a malformed payload', () => {
        expect(() => run([{ type: 'rtf-bot-text' }, { type: 'rtf-node-transition', payload: { node_name: 5 } }])).not.toThrow();
    });
});

function frame(direction: number, sampleRate: number, samples: number[]): ArrayBuffer {
    const buf = new ArrayBuffer(5 + samples.length * 2);
    const view = new DataView(buf);
    view.setUint8(0, direction);
    view.setUint32(1, sampleRate, false);
    samples.forEach((s, i) => view.setInt16(5 + i * 2, s, true));
    return buf;
}

describe('listen-in audio frames', () => {
    it('reads direction, rate and PCM16 samples', () => {
        const out = parseAudioFrame(frame(1, 16000, [0, 16384, -32768]));
        expect(out?.direction).toBe('bot');
        expect(out?.sampleRate).toBe(16000);
        expect(Array.from(out!.samples)).toEqual([0, 0.5, -1]);
        expect(parseAudioFrame(frame(0, 8000, [1, 2]))?.direction).toBe('user');
    });

    it('refuses a frame that is too short or has an absurd rate', () => {
        expect(parseAudioFrame(new ArrayBuffer(3))).toBeNull();
        expect(parseAudioFrame(frame(0, 12, [1, 2]))).toBeNull();
        expect(parseAudioFrame(frame(0, 999999, [1, 2]))).toBeNull();
    });
});
