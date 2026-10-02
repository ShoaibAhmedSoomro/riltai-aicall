"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
    createTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsPost,
    endTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdEndPost,
    getTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdGet,
    simulateTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdSimulatePost,
} from "@/client/sdk.gen";
import { conversationItemsFromTextChatTurns } from "@/components/workflow/conversation/adapters/fromTextChatTurns";

import { EMPTY_TEXT_CHAT_TURNS, type TextChatSession, toTextChatSession } from "./types";
import { extractSdkErrorMessage, getErrorMessage } from "./utils";

export const POLL_INTERVAL_MS = 2000;
// A simulation is at most 20 turns; if it is still going after this, stop watching
// (the run itself is ended by the server when it finishes or by the inactivity sweep).
export const MAX_WATCH_MS = 5 * 60 * 1000;
const MAX_CONSECUTIVE_POLL_FAILURES = 3;

export type SimulationPhase = "idle" | "starting" | "running" | "done" | "error";

export function useSimulatedChat({
    workflowId,
    initialContextVariables,
    disabled,
}: {
    workflowId: number;
    initialContextVariables?: Record<string, string>;
    disabled: boolean;
}) {
    const [phase, setPhase] = useState<SimulationPhase>("idle");
    const [session, setSession] = useState<TextChatSession | null>(null);
    const [error, setError] = useState<string | null>(null);
    const poll = useRef<ReturnType<typeof setInterval> | null>(null);

    const stopPolling = useCallback(() => {
        if (poll.current) clearInterval(poll.current);
        poll.current = null;
    }, []);
    useEffect(() => stopPolling, [stopPolling]);

    const watch = useCallback(
        (runId: number) => {
            const startedAt = Date.now();
            let failures = 0;
            poll.current = setInterval(async () => {
                if (Date.now() - startedAt > MAX_WATCH_MS) {
                    stopPolling();
                    setPhase("done");
                    return;
                }
                const res = await getTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdGet({
                    path: { workflow_id: workflowId, run_id: runId },
                }).catch(() => null);
                if (!res || res.error || !res.data) {
                    failures += 1;
                    if (failures >= MAX_CONSECUTIVE_POLL_FAILURES) {
                        stopPolling();
                        setError(extractSdkErrorMessage(res?.error, "Lost contact with the simulation"));
                        setPhase("error");
                    }
                    return;
                }
                failures = 0;
                const next = toTextChatSession(res.data);
                setSession(next);
                if (next.is_completed) {
                    stopPolling();
                    setPhase("done");
                }
            }, POLL_INTERVAL_MS);
        },
        [stopPolling, workflowId],
    );

    const run = useCallback(
        async (persona: string, maxTurns: number) => {
            if (disabled || phase === "starting" || phase === "running") return;
            setPhase("starting");
            setError(null);
            setSession(null);
            try {
                const created = await createTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsPost({
                    path: { workflow_id: workflowId },
                    body: {
                        initial_context: initialContextVariables ?? {},
                        annotations: { tester: { source: "workflow_editor", modality: "text", ui_mode: "simulated" } },
                    },
                });
                if (created.error || !created.data) {
                    throw new Error(extractSdkErrorMessage(created.error, "Failed to create the simulation"));
                }
                setSession(toTextChatSession(created.data));

                const started = await simulateTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdSimulatePost({
                    path: { workflow_id: workflowId, run_id: created.data.workflow_run_id },
                    body: { persona, max_turns: maxTurns },
                });
                if (started.error) {
                    throw new Error(extractSdkErrorMessage(started.error, "Failed to start the simulation"));
                }
                setPhase("running");
                watch(created.data.workflow_run_id);
            } catch (e) {
                setError(getErrorMessage(e));
                setPhase("error");
            }
        },
        [disabled, initialContextVariables, phase, watch, workflowId],
    );

    const stop = useCallback(async () => {
        if (!session) return;
        stopPolling();
        await endTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdEndPost({
            path: { workflow_id: workflowId, run_id: session.workflow_run_id },
            body: {},
        }).catch(() => null);
        setPhase("done");
    }, [session, stopPolling, workflowId]);

    const reset = useCallback(() => {
        stopPolling();
        setSession(null);
        setError(null);
        setPhase("idle");
    }, [stopPolling]);

    const turns = session?.session_data.turns ?? EMPTY_TEXT_CHAT_TURNS;
    return {
        phase,
        session,
        error,
        turns,
        items: conversationItemsFromTextChatTurns(turns),
        run,
        stop,
        reset,
    };
}
