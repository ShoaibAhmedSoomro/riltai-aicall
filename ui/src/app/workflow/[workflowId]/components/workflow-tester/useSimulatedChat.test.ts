import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({
    create: vi.fn(),
    simulate: vi.fn(),
    get: vi.fn(),
    end: vi.fn(),
}));

vi.mock('@/client/sdk.gen', () => ({
    createTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsPost: sdk.create,
    simulateTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdSimulatePost: sdk.simulate,
    getTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdGet: sdk.get,
    endTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdEndPost: sdk.end,
}));

import { MAX_WATCH_MS, POLL_INTERVAL_MS, useSimulatedChat } from './useSimulatedChat';

const session = (over: Record<string, unknown> = {}, turns: unknown[] = []) => ({
    workflow_run_id: 42,
    workflow_id: 1,
    is_completed: false,
    session_data: { version: 1, status: 'pending', cursor_turn_id: null, turns, discarded_future: [], simulator: { enabled: false, config: {} } },
    checkpoint: {},
    ...over,
});
const turn = (user: string | null, agent: string) => ({
    id: `t-${agent}`, status: 'completed', created_at: 'x',
    user_message: user ? { text: user, created_at: 'x' } : null,
    assistant_message: { text: agent, created_at: 'x' },
    events: [], usage: {},
});

const tick = async (ms: number) => {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
    });
};

beforeEach(() => {
    vi.useFakeTimers();
    Object.values(sdk).forEach((f) => f.mockReset());
    sdk.create.mockResolvedValue({ data: session() });
    sdk.simulate.mockResolvedValue({ data: session() });
    sdk.end.mockResolvedValue({ data: session({ is_completed: true }) });
});
afterEach(() => vi.useRealTimers());

const setup = (disabled = false) =>
    renderHook(() => useSimulatedChat({ workflowId: 1, initialContextVariables: { name: 'Sam' }, disabled }));

describe('useSimulatedChat', () => {
    it('creates a session, starts the simulation with the persona, and watches it', async () => {
        const { result } = setup();
        await act(async () => {
            await result.current.run('An angry caller', 6);
        });

        expect(sdk.create.mock.calls[0][0].body.initial_context).toEqual({ name: 'Sam' });
        expect(sdk.create.mock.calls[0][0].body.annotations.tester.ui_mode).toBe('simulated');
        expect(sdk.simulate.mock.calls[0][0]).toMatchObject({
            path: { workflow_id: 1, run_id: 42 },
            body: { persona: 'An angry caller', max_turns: 6 },
        });
        expect(result.current.phase).toBe('running');
    });

    it('shows turns as they arrive and finishes when the session completes', async () => {
        sdk.get
            .mockResolvedValueOnce({ data: session({}, [turn(null, 'Hello'), turn('Hi', 'How can I help?')]) })
            .mockResolvedValueOnce({ data: session({ is_completed: true }, [turn(null, 'Hello'), turn('Hi', 'How can I help?'), turn('Bye', 'Goodbye')]) });
        const { result } = setup();
        await act(async () => {
            await result.current.run('p', 5);
        });

        await tick(POLL_INTERVAL_MS);
        expect(result.current.turns).toHaveLength(2);
        expect(result.current.phase).toBe('running');

        await tick(POLL_INTERVAL_MS);
        expect(result.current.turns).toHaveLength(3);
        expect(result.current.phase).toBe('done');

        await tick(POLL_INTERVAL_MS * 3);
        expect(sdk.get).toHaveBeenCalledTimes(2); // it stopped asking
    });

    it('reports a failed start and lets the person try again', async () => {
        sdk.create.mockResolvedValue({ error: { detail: 'Quota exceeded' } });
        const { result } = setup();
        await act(async () => {
            await result.current.run('p', 5);
        });
        expect(result.current.phase).toBe('error');
        expect(result.current.error).toBeTruthy();
        expect(sdk.simulate).not.toHaveBeenCalled();
    });

    it('gives up after repeated polling failures instead of spinning forever', async () => {
        sdk.get.mockResolvedValue({ error: { detail: 'boom' } });
        const { result } = setup();
        await act(async () => {
            await result.current.run('p', 5);
        });
        await tick(POLL_INTERVAL_MS * 4);
        expect(result.current.phase).toBe('error');
    });

    it('stops watching after a long wait', async () => {
        sdk.get.mockResolvedValue({ data: session() });
        const { result } = setup();
        await act(async () => {
            await result.current.run('p', 5);
        });
        await tick(MAX_WATCH_MS + POLL_INTERVAL_MS * 2);
        expect(result.current.phase).toBe('done');
    });

    it('Stop ends the session and stops polling', async () => {
        sdk.get.mockResolvedValue({ data: session() });
        const { result } = setup();
        await act(async () => {
            await result.current.run('p', 5);
        });
        await act(async () => {
            await result.current.stop();
        });
        const callsAfterStop = sdk.get.mock.calls.length;
        await tick(POLL_INTERVAL_MS * 3);

        expect(sdk.end).toHaveBeenCalledTimes(1);
        expect(result.current.phase).toBe('done');
        expect(sdk.get.mock.calls.length).toBe(callsAfterStop);
    });

    it('does nothing while testing is blocked', async () => {
        const { result } = setup(true);
        await act(async () => {
            await result.current.run('p', 5);
        });
        expect(sdk.create).not.toHaveBeenCalled();
        expect(result.current.phase).toBe('idle');
    });
});
