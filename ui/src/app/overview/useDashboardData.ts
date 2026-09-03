'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
    getApiKeysApiV1UserApiKeysGet,
    getCampaignsApiV1CampaignGet,
    getCurrentPeriodUsageApiV1OrganizationsUsageCurrentPeriodGet,
    getDailyReportApiV1OrganizationsReportsDailyGet,
    getUsageHistoryApiV1OrganizationsUsageRunsGet,
    getWorkflowCountApiV1WorkflowCountGet,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
} from '@/client/sdk.gen';
import type {
    CurrentUsageResponse,
    TelephonyConfigurationListItem,
    WorkflowCountResponse,
    WorkflowRunUsageResponse,
} from '@/client/types.gen';
import { useAuth } from '@/lib/auth';
import { getLocalTimezone } from '@/lib/dateTime';

/**
 * Every number the dashboard renders, and nothing it cannot prove.
 *
 * The constraint that shaped this file: each figure has to come from an endpoint
 * that really returns it. Surveying the API turned up several things that LOOK
 * available and are not, so they are deliberately absent here:
 *
 *   money / spend        organizations.price_per_second_usd is a nullable column
 *                        that no application code ever writes, so every USD
 *                        field is absent and /usage/daily-breakdown answers 400
 *                        unconditionally. There is no cost widget.
 *   live / concurrent    /health/active-calls and /health/autoscale-metric both
 *                        verify the X-Rilt-Devops-Secret header, so a browser
 *                        session gets 403. get_concurrent_count() exists in the
 *                        rate limiter but no route exposes it.
 *   deltas vs last month there is no previous-period endpoint, so no stat card
 *                        claims a percentage change.
 *   transfers            the daily report's xfer_count matches the literal
 *                        "XFER", which nothing in the platform writes (the real
 *                        codes are call_transferred / transfer_call), so it is
 *                        structurally zero and is not surfaced.
 *   token usage          UsageHistoryResponse.total_rilt_tokens is hardcoded 0.
 *
 * Each fetch is independent and failure-isolated: one endpoint 4xx-ing degrades
 * its own widget to an empty state instead of blanking the page. The generated
 * client resolves rather than throwing on HTTP errors, so `error` is checked
 * explicitly on every call.
 */

/** One day of call volume, from a COUNT over a single day's range. */
export interface DayVolume {
    /** ISO date, YYYY-MM-DD, in the report timezone. */
    date: string;
    calls: number;
}

export interface DispositionSlice {
    disposition: string;
    count: number;
    percentage: number;
}

export interface DurationBucket {
    bucket: string;
    count: number;
    percentage: number;
}

export interface AgentActivity {
    workflowId: number;
    workflowName: string;
    calls: number;
    seconds: number;
}

export interface DashboardData {
    loading: boolean;
    /** The timezone every date-bounded figure was computed in. */
    timezone: string;
    /** Today's date in that timezone, YYYY-MM-DD. */
    today: string;

    agents: WorkflowCountResponse | null;
    /** Org-wide lifetime run count, from a real subquery COUNT. */
    totalCalls: number | null;
    /** Calls today, from the daily report. Counts every run row, see labelling. */
    callsToday: number | null;
    period: CurrentUsageResponse | null;
    campaigns: { total: number; byState: Record<string, number>; activeRows: number } | null;
    telephony: TelephonyConfigurationListItem[] | null;
    apiKeyCount: number | null;

    dayVolume: DayVolume[] | null;
    dispositions: DispositionSlice[] | null;
    durations: DurationBucket[] | null;
    recentCalls: WorkflowRunUsageResponse[] | null;
    busiestAgents: AgentActivity[] | null;
    /** True when busiestAgents was computed from a truncated window. */
    busiestAgentsTruncated: boolean;

    refresh: () => void;
}

const TREND_DAYS = 7;
/** /usage/runs caps limit at 100 (api/routes/organization_usage.py). */
const RUNS_PAGE_MAX = 100;

/** YYYY-MM-DD for a date shifted by `offsetDays`, in the given IANA zone. */
function isoDateInZone(timezone: string, offsetDays: number, now: Date): string {
    const shifted = new Date(now.getTime() + offsetDays * 86_400_000);
    // en-CA formats as YYYY-MM-DD, which is exactly the API's date format.
    return new Intl.DateTimeFormat('en-CA', {
        timeZone: timezone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).format(shifted);
}

export function useDashboardData(timezoneOverride?: string | null): DashboardData {
    const { user, loading: authLoading } = useAuth();
    const userId = user?.id ?? null;

    const timezone = timezoneOverride || getLocalTimezone();
    // Pinned once per mount so every widget on screen describes the same instant
    // and a render at midnight cannot split the page across two days.
    const nowRef = useRef<Date | null>(null);
    if (nowRef.current === null) nowRef.current = new Date();
    const now = nowRef.current;

    const [nonce, setNonce] = useState(0);
    const refresh = useCallback(() => setNonce((n) => n + 1), []);

    const [loading, setLoading] = useState(true);
    const [agents, setAgents] = useState<WorkflowCountResponse | null>(null);
    const [totalCalls, setTotalCalls] = useState<number | null>(null);
    const [callsToday, setCallsToday] = useState<number | null>(null);
    const [period, setPeriod] = useState<CurrentUsageResponse | null>(null);
    const [campaigns, setCampaigns] = useState<DashboardData['campaigns']>(null);
    const [telephony, setTelephony] = useState<TelephonyConfigurationListItem[] | null>(null);
    const [apiKeyCount, setApiKeyCount] = useState<number | null>(null);
    const [dayVolume, setDayVolume] = useState<DayVolume[] | null>(null);
    const [dispositions, setDispositions] = useState<DispositionSlice[] | null>(null);
    const [durations, setDurations] = useState<DurationBucket[] | null>(null);
    const [recentCalls, setRecentCalls] = useState<WorkflowRunUsageResponse[] | null>(null);
    const [busiestAgents, setBusiestAgents] = useState<AgentActivity[] | null>(null);
    const [busiestTruncated, setBusiestTruncated] = useState(false);

    const today = useMemo(() => isoDateInZone(timezone, 0, now), [timezone, now]);

    useEffect(() => {
        // Fetching before auth settles sends an unauthenticated request that
        // fails silently: the bearer-token interceptor is only registered once
        // auth has finished loading.
        if (authLoading || !userId) return;

        let cancelled = false;
        setLoading(true);

        /** Run a fetch, swallow its failure, and leave that widget empty. */
        async function guarded<T>(run: () => Promise<T | null>): Promise<T | null> {
            try {
                return await run();
            } catch {
                return null;
            }
        }

        const jobs: Array<Promise<unknown>> = [];

        jobs.push(
            guarded(async () => {
                const r = await getWorkflowCountApiV1WorkflowCountGet();
                if (!cancelled && !r.error && r.data) setAgents(r.data);
                return null;
            }),
        );

        // limit=1 because only total_count is wanted. NOTE: the response's
        // total_duration_seconds sums the returned PAGE only, so it must never
        // be read here — total_count is the real COUNT over the whole filter.
        jobs.push(
            guarded(async () => {
                const r = await getUsageHistoryApiV1OrganizationsUsageRunsGet({ query: { limit: 1 } });
                if (!cancelled && !r.error && r.data) setTotalCalls(r.data.total_count);
                return null;
            }),
        );

        jobs.push(
            guarded(async () => {
                const r = await getCurrentPeriodUsageApiV1OrganizationsUsageCurrentPeriodGet();
                if (!cancelled && !r.error && r.data) setPeriod(r.data);
                return null;
            }),
        );

        // Today's report carries three things at once: the run count, the
        // disposition mix and the duration histogram.
        jobs.push(
            guarded(async () => {
                const r = await getDailyReportApiV1OrganizationsReportsDailyGet({
                    query: { date: today, timezone },
                });
                if (cancelled || r.error || !r.data) return null;
                setCallsToday(r.data.metrics?.total_runs ?? 0);
                setDispositions(
                    (r.data.disposition_distribution ?? []).map((d) => ({
                        disposition: String(d.disposition ?? 'UNKNOWN'),
                        count: Number(d.count ?? 0),
                        percentage: Number(d.percentage ?? 0),
                    })),
                );
                setDurations(
                    (r.data.call_duration_distribution ?? []).map((d) => ({
                        bucket: String(d.bucket ?? ''),
                        count: Number(d.count ?? 0),
                        percentage: Number(d.percentage ?? 0),
                    })),
                );
                return null;
            }),
        );

        // /campaign is UNPAGINATED and includes each campaign's full logs array,
        // so this is the one heavy call here. It is still one request, and it is
        // the only way to get campaign totals or per-state counts: there is no
        // /campaign/count and no state aggregate.
        jobs.push(
            guarded(async () => {
                const r = await getCampaignsApiV1CampaignGet();
                if (cancelled || r.error || !r.data) return null;
                const list = r.data.campaigns ?? [];
                const byState: Record<string, number> = {};
                let activeRows = 0;
                for (const c of list) {
                    byState[c.state] = (byState[c.state] ?? 0) + 1;
                    if (c.state === 'running') {
                        activeRows += Math.max(0, (c.total_rows ?? 0) - c.processed_rows);
                    }
                }
                setCampaigns({ total: list.length, byState, activeRows });
                return null;
            }),
        );

        jobs.push(
            guarded(async () => {
                const r = await listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet();
                if (cancelled || r.error || !r.data) return null;
                setTelephony(r.data.configurations ?? []);
                return null;
            }),
        );

        jobs.push(
            guarded(async () => {
                const r = await getApiKeysApiV1UserApiKeysGet();
                if (cancelled || r.error || !Array.isArray(r.data)) return null;
                setApiKeyCount(r.data.filter((k) => k.is_active).length);
                return null;
            }),
        );

        // Per-day volume. There is no server-side daily aggregate available on a
        // self-hosted install (/usage/daily-breakdown requires pricing, which is
        // never configured), so this is one COUNT per day over a date range.
        //
        // ponytail: TREND_DAYS count-only requests rather than one aggregate.
        // Each is a subquery COUNT with no row hydration, but workflow_runs has
        // no index on created_at, so the ceiling is a table scan per day. If this
        // ever matters, the fix is a backend GROUP BY endpoint, not more requests.
        jobs.push(
            guarded(async () => {
                const days = Array.from({ length: TREND_DAYS }, (_, i) =>
                    isoDateInZone(timezone, i - (TREND_DAYS - 1), now),
                );
                const counts = await Promise.all(
                    days.map(async (date) => {
                        const r = await getUsageHistoryApiV1OrganizationsUsageRunsGet({
                            query: {
                                limit: 1,
                                start_date: `${date}T00:00:00Z`,
                                end_date: `${date}T23:59:59Z`,
                            },
                        });
                        return r.error || !r.data ? null : r.data.total_count;
                    }),
                );
                if (cancelled || counts.some((c) => c === null)) return null;
                setDayVolume(days.map((date, i) => ({ date, calls: counts[i] as number })));
                return null;
            }),
        );

        // One page of recent runs serves two widgets: the activity list and the
        // per-agent tally. The tally is therefore over this window only, which is
        // why the UI labels it as recent activity rather than an all-time ranking.
        jobs.push(
            guarded(async () => {
                const r = await getUsageHistoryApiV1OrganizationsUsageRunsGet({
                    query: { limit: RUNS_PAGE_MAX },
                });
                if (cancelled || r.error || !r.data) return null;
                const runs = r.data.runs ?? [];
                setRecentCalls(runs.slice(0, 6));
                setBusiestTruncated(r.data.total_count > runs.length);

                const tally = new Map<number, AgentActivity>();
                for (const run of runs) {
                    const entry = tally.get(run.workflow_id) ?? {
                        workflowId: run.workflow_id,
                        workflowName: run.workflow_name || `Agent ${run.workflow_id}`,
                        calls: 0,
                        seconds: 0,
                    };
                    entry.calls += 1;
                    entry.seconds += run.call_duration_seconds ?? 0;
                    tally.set(run.workflow_id, entry);
                }
                setBusiestAgents(
                    [...tally.values()].sort((a, b) => b.calls - a.calls || b.seconds - a.seconds).slice(0, 5),
                );
                return null;
            }),
        );

        void Promise.all(jobs).then(() => {
            if (!cancelled) setLoading(false);
        });

        return () => {
            cancelled = true;
        };
        // `userId` rather than `user`: the hosted auth provider's hook can return
        // a fresh object per render, which would refetch everything each time.
    }, [authLoading, userId, timezone, today, now, nonce]);

    return {
        loading,
        timezone,
        today,
        agents,
        totalCalls,
        callsToday,
        period,
        campaigns,
        telephony,
        apiKeyCount,
        dayVolume,
        dispositions,
        durations,
        recentCalls,
        busiestAgents,
        busiestAgentsTruncated: busiestTruncated,
        refresh,
    };
}
