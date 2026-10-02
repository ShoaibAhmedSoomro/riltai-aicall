'use client';

import { ArrowLeft, HeadphoneOff,Headphones } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RealtimeFeedback } from '@/components/workflow/conversation/RealtimeFeedback';

import { type MonitorStatus, useLiveMonitor } from '../useLiveMonitor';

const STATUS_LABEL: Record<MonitorStatus, string> = {
    connecting: 'Connecting…',
    live: 'Live',
    ended: 'Call ended',
    error: 'Connection lost',
};

export default function LiveCallPage() {
    const { runId } = useParams<{ runId: string }>();
    const id = Number(runId);
    const { messages, status, canListen, listenAllowed, transcriptShown, listening, setListening, reconnect } =
        useLiveMonitor(id);

    return (
        <div className="container mx-auto flex h-[calc(100vh-4rem)] flex-col gap-4 px-4 py-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                    <Button asChild variant="ghost" size="sm">
                        <Link href="/live">
                            <ArrowLeft className="mr-1 h-4 w-4" aria-hidden />
                            Live calls
                        </Link>
                    </Button>
                    <h1 className="text-lg font-semibold">Call {id}</h1>
                    <Badge variant={status === 'live' ? 'default' : 'secondary'} aria-live="polite">
                        {STATUS_LABEL[status]}
                    </Badge>
                </div>

                <div className="flex items-center gap-2">
                    {status === 'error' && (
                        <Button size="sm" variant="outline" onClick={reconnect}>
                            Reconnect
                        </Button>
                    )}
                    {canListen && status === 'live' && (
                        <Button
                            size="sm"
                            variant={listening ? 'default' : 'outline'}
                            disabled={!listenAllowed}
                            aria-pressed={listening}
                            title={
                                listenAllowed
                                    ? undefined
                                    : "This agent's data policy keeps its audio off the monitor."
                            }
                            onClick={() => setListening(!listening)}
                        >
                            {listening ? (
                                <HeadphoneOff className="mr-1 h-4 w-4" aria-hidden />
                            ) : (
                                <Headphones className="mr-1 h-4 w-4" aria-hidden />
                            )}
                            {listening ? 'Stop listening' : 'Listen in'}
                        </Button>
                    )}
                </div>
            </div>

            {!transcriptShown && (
                <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                    This agent&apos;s data policy keeps what is said off the monitor. You can follow the steps the
                    call goes through.
                </p>
            )}
            {canListen && !listenAllowed && (
                <p className="text-xs text-muted-foreground">
                    Listening in is off for this call because its data policy withholds or redacts the audio.
                </p>
            )}

            <div className="min-h-0 flex-1 overflow-hidden rounded-xl border bg-card">
                <RealtimeFeedback
                    mode="live"
                    messages={messages}
                    isCallActive={status === 'live'}
                    isCallCompleted={status === 'ended'}
                />
            </div>
        </div>
    );
}
