'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { client } from '@/client/client.gen';
import type { RealtimeFeedbackMessage } from '@/components/workflow/conversation/types';
import { resolveBrowserBackendUrl } from '@/lib/apiClient';
import { useAuth } from '@/lib/auth';

import { applyMonitorEvent, applyMonitorEvents, type MonitorEvent, parseAudioFrame } from './monitorMessages';

export type MonitorStatus = 'connecting' | 'live' | 'ended' | 'error';

interface Backfill {
    type: 'monitor-backfill';
    events: MonitorEvent[];
    meta?: { listen_in?: boolean; transcript?: boolean } | null;
    can_listen?: boolean;
}

/**
 * Watch one live call. Opens the monitor socket, keeps the transcript, and (for an
 * admin, on a call whose data policy allows it) plays the audio when listening is on.
 * Audio plays only after a click: browsers refuse to start sound otherwise.
 */
export function useLiveMonitor(runId: number) {
    const { loading: authLoading, isAuthenticated, getAccessToken } = useAuth();
    const [messages, setMessages] = useState<RealtimeFeedbackMessage[]>([]);
    const [status, setStatus] = useState<MonitorStatus>('connecting');
    const [canListen, setCanListen] = useState(false);
    const [listenAllowed, setListenAllowed] = useState(true);
    const [transcriptShown, setTranscriptShown] = useState(true);
    const [listening, setListeningState] = useState(false);
    const [attempt, setAttempt] = useState(0);

    const wsRef = useRef<WebSocket | null>(null);
    const audioRef = useRef<AudioContext | null>(null);
    const nextTimeRef = useRef<{ user: number; bot: number }>({ user: 0, bot: 0 });
    const listeningRef = useRef(false);

    const playChunk = useCallback((buffer: ArrayBuffer) => {
        const ctx = audioRef.current;
        const frame = parseAudioFrame(buffer);
        if (!ctx || !frame || !listeningRef.current) return;
        const audio = ctx.createBuffer(1, frame.samples.length, frame.sampleRate);
        audio.getChannelData(0).set(frame.samples);
        const source = ctx.createBufferSource();
        source.buffer = audio;
        source.connect(ctx.destination);
        // Each side keeps its own playhead so chunks queue back to back without gaps,
        // and a little lead-in absorbs network jitter.
        const next = nextTimeRef.current;
        const startAt = Math.max(ctx.currentTime + 0.08, next[frame.direction]);
        source.start(startAt);
        next[frame.direction] = startAt + audio.duration;
    }, []);

    useEffect(() => {
        if (authLoading || !isAuthenticated) return;
        let cancelled = false;
        let ws: WebSocket | null = null;

        (async () => {
            const token = await getAccessToken();
            if (cancelled || !token) return;
            const base = (client.getConfig().baseUrl || resolveBrowserBackendUrl()).replace(/^http/, 'ws');
            ws = new WebSocket(`${base}/api/v1/monitor/ws/${runId}?token=${encodeURIComponent(token)}`);
            ws.binaryType = 'arraybuffer';
            wsRef.current = ws;
            setStatus('connecting');

            ws.onmessage = (e) => {
                if (e.data instanceof ArrayBuffer) {
                    playChunk(e.data);
                    return;
                }
                let msg: MonitorEvent & Partial<Backfill>;
                try {
                    msg = JSON.parse(e.data);
                } catch {
                    return;
                }
                if (msg.type === 'monitor-backfill') {
                    setMessages(applyMonitorEvents([], msg.events ?? []));
                    setCanListen(Boolean(msg.can_listen));
                    setListenAllowed(msg.meta?.listen_in !== false);
                    setTranscriptShown(msg.meta?.transcript !== false);
                    setStatus('live');
                } else if (msg.type === 'monitor-ended') {
                    setStatus('ended');
                } else {
                    setMessages((prev) => applyMonitorEvent(prev, msg));
                }
            };
            ws.onclose = (e) => {
                // 1000 is the server saying the call finished; anything else is a drop.
                setStatus((s) => (s === 'ended' || e.code === 1000 ? 'ended' : 'error'));
            };
            ws.onerror = () => setStatus((s) => (s === 'ended' ? s : 'error'));
        })();

        return () => {
            cancelled = true;
            ws?.close();
            wsRef.current = null;
        };
    }, [authLoading, isAuthenticated, getAccessToken, runId, attempt, playChunk]);

    // Stop the sound when leaving the page.
    useEffect(
        () => () => {
            void audioRef.current?.close();
            audioRef.current = null;
        },
        [],
    );

    const setListening = useCallback((on: boolean) => {
        if (on && !audioRef.current) {
            const Ctor =
                window.AudioContext ||
                (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
            if (!Ctor) return;
            audioRef.current = new Ctor();
        }
        if (on) void audioRef.current?.resume();
        nextTimeRef.current = { user: 0, bot: 0 };
        listeningRef.current = on;
        setListeningState(on);
        wsRef.current?.send(JSON.stringify({ type: 'listen', on }));
    }, []);

    const reconnect = useCallback(() => setAttempt((n) => n + 1), []);

    return { messages, status, canListen, listenAllowed, transcriptShown, listening, setListening, reconnect };
}
