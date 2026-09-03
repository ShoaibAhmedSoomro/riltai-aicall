'use client';

import { Phone } from 'lucide-react';
import Link from 'next/link';

import type { WorkflowRunUsageResponse } from '@/client/types.gen';

import { Panel } from './Panel';

/** "42s", "3m 20s" — per-call precision, unlike the period totals elsewhere. */
function callLength(seconds: number): string {
    if (!seconds) return '0s';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    if (!m) return `${s}s`;
    return s ? `${m}m ${s}s` : `${m}m`;
}

/** "4m ago", "3h ago", "2d ago" — falls back to a date beyond a week. */
function relativeTime(iso: string): string {
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return '';
    const mins = Math.floor((Date.now() - then) / 60_000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    return new Date(iso).toLocaleDateString();
}

/**
 * The last few runs, each linking to its own transcript and recording.
 *
 * Rows come from /organizations/usage/runs, which only returns runs that have
 * usage_info, so an in-flight call does not appear here until it has recorded
 * something.
 */
export function RecentCallsPanel({
    runs,
    loading,
}: {
    runs: WorkflowRunUsageResponse[] | null;
    loading: boolean;
}) {
    return (
        <Panel
            title="Recent calls"
            action={{ label: 'All runs', href: '/usage' }}
            loading={loading}
            empty={
                runs && runs.length === 0
                    ? 'No calls yet. Runs appear here once an agent takes or places its first call.'
                    : undefined
            }
            bodyClassName="p-0"
        >
            <ul className="divide-y divide-border/60">
                {(runs ?? []).map((run) => (
                    <li key={run.id}>
                        <Link
                            href={`/workflow/${run.workflow_id}/run/${run.id}`}
                            className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                        >
                            <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted">
                                <Phone className="size-3.5 text-muted-foreground" aria-hidden />
                            </span>
                            <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-medium">
                                    {run.workflow_name || `Agent ${run.workflow_id}`}
                                </span>
                                <span className="block truncate text-xs text-muted-foreground">
                                    {run.name} · {relativeTime(run.created_at)}
                                </span>
                            </span>
                            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                                {callLength(run.call_duration_seconds)}
                            </span>
                        </Link>
                    </li>
                ))}
            </ul>
        </Panel>
    );
}
