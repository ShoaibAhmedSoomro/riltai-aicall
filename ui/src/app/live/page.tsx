'use client';

import { PhoneIncoming, PhoneOutgoing, Radio } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

import { listLiveCallsApiV1MonitorLiveCallsGet } from '@/client/sdk.gen';
import type { LiveCall } from '@/client/types.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';

import { formatElapsed } from './format';

const POLL_MS = 5000;

export default function LiveCallsPage() {
    const { loading: authLoading, isAuthenticated } = useAuth();
    const [calls, setCalls] = useState<LiveCall[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [now, setNow] = useState(() => Date.now());
    const inFlight = useRef(false);

    const load = useCallback(async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        try {
            const res = await listLiveCallsApiV1MonitorLiveCallsGet();
            if (res.error) {
                setError(detailFromError(res.error, 'Could not load live calls'));
                return;
            }
            setError(null);
            setCalls(res.data?.calls ?? []);
        } catch {
            setError('Could not reach the server');
        } finally {
            inFlight.current = false;
        }
    }, []);

    // Wait for auth before the first call: the token is attached by an interceptor
    // that only exists once auth has loaded.
    useEffect(() => {
        if (authLoading || !isAuthenticated) return;
        void load();
        const poll = setInterval(() => void load(), POLL_MS);
        return () => clearInterval(poll);
    }, [authLoading, isAuthenticated, load]);

    // Elapsed times tick every second without refetching.
    useEffect(() => {
        const tick = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(tick);
    }, []);

    return (
        <div className="container mx-auto px-4 py-8">
            <div className="mb-6 flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold">Live Calls</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Calls happening right now. Open one to read it as it unfolds
                        {calls?.length ? ` · ${calls.length} active` : ''}.
                    </p>
                </div>
                <Button asChild variant="outline">
                    <Link href="/alerts">Alerts</Link>
                </Button>
            </div>

            {error && (
                <p role="alert" className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                    {error}
                </p>
            )}

            <Card>
                <CardContent className="p-0">
                    {calls === null ? (
                        <p className="p-8 text-center text-sm text-muted-foreground">Loading…</p>
                    ) : calls.length === 0 ? (
                        <div className="flex flex-col items-center gap-2 p-10 text-center">
                            <Radio className="h-6 w-6 text-muted-foreground" aria-hidden />
                            <p className="font-medium">No calls right now</p>
                            <p className="max-w-md text-sm text-muted-foreground">
                                When an agent is on a call it shows up here within a few seconds. Place a test call from
                                an agent to see it.
                            </p>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Agent</TableHead>
                                    <TableHead>Direction</TableHead>
                                    <TableHead>Number</TableHead>
                                    <TableHead>Step</TableHead>
                                    <TableHead className="text-right">Time</TableHead>
                                    <TableHead className="w-24" />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {calls.map((c) => (
                                    <TableRow key={c.run_id}>
                                        <TableCell className="font-medium">{c.workflow_name}</TableCell>
                                        <TableCell>
                                            <Badge variant="secondary" className="gap-1">
                                                {c.call_type === 'inbound' ? (
                                                    <PhoneIncoming className="h-3 w-3" aria-hidden />
                                                ) : (
                                                    <PhoneOutgoing className="h-3 w-3" aria-hidden />
                                                )}
                                                {c.call_type === 'inbound' ? 'Inbound' : 'Outbound'}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="tabular-nums">{c.number ?? '–'}</TableCell>
                                        <TableCell className="text-muted-foreground">{c.current_node ?? '–'}</TableCell>
                                        <TableCell className="text-right tabular-nums">
                                            {formatElapsed(c.started_at, now)}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Button asChild size="sm" variant="outline">
                                                <Link href={`/live/${c.run_id}`}>Watch</Link>
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
