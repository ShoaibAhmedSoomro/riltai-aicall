'use client';

import Link from 'next/link';

import type { AgentActivity } from '../useDashboardData';
import { Panel } from './Panel';

function minutes(seconds: number): string {
    const m = seconds / 60;
    if (m < 10) return `${m.toFixed(1)}m`;
    return `${Math.round(m)}m`;
}

/**
 * Which agents are handling the calls.
 *
 * Counted from the most recent page of runs, NOT all time: there is no
 * group-by-workflow endpoint, and the only alternative would be one request per
 * agent. The subtitle states the window explicitly, and `truncated` says so
 * when there are more runs than the page could hold, because an unqualified
 * "top agents" would be a claim the data does not support.
 */
export function BusiestAgentsPanel({
    agents,
    truncated,
    windowSize,
    loading,
}: {
    agents: AgentActivity[] | null;
    truncated: boolean;
    windowSize: number;
    loading: boolean;
}) {
    const max = Math.max(1, ...(agents ?? []).map((a) => a.calls));

    return (
        <Panel
            title="Busiest agents"
            subtitle={
                loading
                    ? undefined
                    : truncated
                      ? `Across the last ${windowSize} runs`
                      : 'Across all runs so far'
            }
            action={{ label: 'All agents', href: '/workflow' }}
            loading={loading}
            empty={
                agents && agents.length === 0
                    ? 'No runs to rank yet. This fills in once your agents start taking calls.'
                    : undefined
            }
        >
            <ul className="space-y-3">
                {(agents ?? []).map((agent) => (
                    <li key={agent.workflowId}>
                        <Link
                            href={`/workflow/${agent.workflowId}/runs`}
                            className="group block focus-visible:outline-none"
                        >
                            <div className="flex items-baseline justify-between gap-3">
                                <span className="min-w-0 truncate text-sm font-medium group-hover:underline">
                                    {agent.workflowName}
                                </span>
                                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                                    {agent.calls.toLocaleString()} · {minutes(agent.seconds)}
                                </span>
                            </div>
                            <div
                                className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"
                                role="presentation"
                            >
                                <div
                                    className="h-full rounded-full bg-[var(--chart-1)]"
                                    style={{ width: `${Math.max(4, (agent.calls / max) * 100)}%` }}
                                />
                            </div>
                        </Link>
                    </li>
                ))}
            </ul>
        </Panel>
    );
}
