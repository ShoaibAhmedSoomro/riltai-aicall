'use client';

import { Bell, Check } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { acknowledgeEventApiV1AlertsEventsEventUuidAcknowledgePost, listEventsApiV1AlertsEventsGet } from '@/client/sdk.gen';
import type { AlertEventResponse } from '@/client/types.gen';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';
import { formatDateTime } from '@/lib/dateTime';

import { AlertsTabs } from './AlertsTabs';
import { SeverityChip } from './SeverityChip';

export default function AlertsPage() {
    const { loading: authLoading, isAuthenticated } = useAuth();
    const [events, setEvents] = useState<AlertEventResponse[] | null>(null);
    const [severity, setSeverity] = useState<string>('all');
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        const res = await listEventsApiV1AlertsEventsGet({
            query: { limit: 100, ...(severity !== 'all' ? { severity: severity as 'low' | 'medium' | 'high' } : {}) },
        });
        if (res.error) {
            setError(detailFromError(res.error, 'Could not load alerts'));
            return;
        }
        setError(null);
        setEvents(res.data?.events ?? []);
    }, [severity]);

    useEffect(() => {
        if (authLoading || !isAuthenticated) return;
        void load();
    }, [authLoading, isAuthenticated, load]);

    const acknowledge = async (event: AlertEventResponse) => {
        const res = await acknowledgeEventApiV1AlertsEventsEventUuidAcknowledgePost({
            path: { event_uuid: event.event_uuid },
        });
        if (res.error || !res.data) {
            toast.error(detailFromError(res.error, 'Could not acknowledge the alert'));
            return;
        }
        setEvents((prev) => prev?.map((e) => (e.event_uuid === event.event_uuid ? res.data! : e)) ?? prev);
    };

    return (
        <div className="container mx-auto px-4 py-8">
            <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold">Alerts</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        What your rules have caught. Newest first.
                    </p>
                </div>
                <Select value={severity} onValueChange={setSeverity}>
                    <SelectTrigger className="w-40" aria-label="Filter by severity">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">All severities</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="low">Low</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <AlertsTabs />

            {error && (
                <p role="alert" className="mb-4 text-sm text-destructive">
                    {error}
                </p>
            )}

            <Card>
                <CardContent className="p-0">
                    {events === null ? (
                        <p className="p-8 text-center text-sm text-muted-foreground">Loading…</p>
                    ) : events.length === 0 ? (
                        <div className="flex flex-col items-center gap-2 p-10 text-center">
                            <Bell className="h-6 w-6 text-muted-foreground" aria-hidden />
                            <p className="font-medium">No alerts</p>
                            <p className="max-w-md text-sm text-muted-foreground">
                                Create a rule to be notified when a call fails or a metric moves.
                            </p>
                            <Button asChild size="sm" variant="outline">
                                <Link href="/alerts/rules/new">Create a rule</Link>
                            </Button>
                        </div>
                    ) : (
                        <ul className="divide-y">
                            {events.map((e) => {
                                const workflowId = (e.detail as { workflow_id?: number }).workflow_id;
                                const condition = (e.detail as { condition?: string }).condition;
                                return (
                                    <li key={e.event_uuid} className="flex items-start gap-3 px-4 py-3">
                                        <SeverityChip severity={e.severity} />
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium">{e.title}</p>
                                            {condition && <p className="text-sm text-muted-foreground">{condition}</p>}
                                            <p className="mt-0.5 text-xs text-muted-foreground">
                                                {formatDateTime(e.created_at)}
                                                {e.workflow_run_id && workflowId ? (
                                                    <>
                                                        {' · '}
                                                        <Link
                                                            href={`/workflow/${workflowId}/run/${e.workflow_run_id}`}
                                                            className="underline-offset-2 hover:underline"
                                                        >
                                                            View the call
                                                        </Link>
                                                    </>
                                                ) : null}
                                            </p>
                                        </div>
                                        {e.acknowledged_at ? (
                                            <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                                                <Check className="h-3 w-3" aria-hidden /> Seen
                                            </span>
                                        ) : (
                                            <Button size="sm" variant="outline" onClick={() => acknowledge(e)}>
                                                Acknowledge
                                            </Button>
                                        )}
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
