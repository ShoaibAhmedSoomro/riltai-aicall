'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
    getAlertsApiV1OrganizationsReportsAlertsGet,
    getApiKeysApiV1UserApiKeysGet,
    getCampaignsApiV1CampaignGet,
    getCurrentPeriodUsageApiV1OrganizationsUsageCurrentPeriodGet,
    getDailyReportApiV1OrganizationsReportsDailyGet,
    getLiveUsageApiV1OrganizationsUsageLiveGet,
    getQueueSummaryApiV1CampaignQueueSummaryGet,
    getUsageHistoryApiV1OrganizationsUsageRunsGet,
    getUsageSeriesApiV1OrganizationsUsageSeriesGet,
    getUsageSummaryApiV1OrganizationsUsageSummaryGet,
    getWorkflowCountApiV1WorkflowCountGet,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
} from '@/client/sdk.gen';
import type {
    AlertItem,
    CurrentUsageResponse,
    LiveUsageResponse,
    QueueSummaryResponse,
    TelephonyConfigurationListItem,
    UsageSeriesResponse,
    UsageSummaryResponse,
    WorkflowCountResponse,
    WorkflowRunUsageResponse,
} from '@/client/types.gen';
import { useAuth } from '@/lib/auth';
import { getLocalTimezone } from '@/lib/dateTime';

/**
 * Every number the dashboard renders, and nothing it cannot prove.
 *
 * The constraint that shaped this file: each figure has to come from an endpoint
 * that really returns it. An earlier version of this note listed money, deltas,
 * live concurrency and transfers as structurally unobtainable. None of that is
 * true any more, so the list is gone rather than left to mislead.
 *
 * What each source is good for, and what it is NOT:
 *
 *   /usage/summary     a 30-day window plus `previous`, an equal-length window
 *                      immediately before it. That is what makes a delta
 *                      honest -- both halves come from one query over one
 *                      filter set, so they cannot disagree. Read the previous
 *                      window through `summary.previous`; it is not lifted to
 *                      a separate field, because two copies of one number is
 *                      how they drift apart.
 *   /usage/series      per-bucket calls, duration, charge and answer rate.
 *                      It OMITS empty buckets, so a trend line has to fill its
 *                      own gaps -- see `dayVolume`.
 *   /usage/runs        rows. Still the only source for the activity list and
 *                      the per-agent tally, and the only lifetime count.
 *   /campaign/queue-summary, /organizations/reports/alerts
 *                      queued work and current problems, both org-wide.
 *
 * Nullable means unknown, everywhere in here. `summary.total_charge_usd` is
 * null when nothing was priced, `series` points carry a null charge for the
 * same reason, and `live.active_calls` is null when Redis could not answer.
 * None of those are zero, and a panel that renders them as zero is lying.
 *
 * Each fetch is independent and failure-isolated: one endpoint 4xx-ing degrades
 * its own widget to an empty state instead of blanking the page. The generated
 * client resolves rather than throwing on HTTP errors, so `error` is checked
 * explicitly on every call.
 */

/** One day of call volume, from the day buckets of /usage/series. */
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
    /**
     * Live concurrency. `active_calls` is itself nullable INSIDE this:
     * null means Redis could not answer, which is not the same as zero
     * calls and must not be rendered as an idle system.
     */
    live: LiveUsageResponse | null;
    campaigns: { total: number; byState: Record<string, number>; activeRows: number } | null;
    /**
     * 30-day headline figures, with the equal-length window before them under
     * `.previous`. Money and answer rate inside are nullable: unknown, not zero.
     */
    summary: UsageSummaryResponse | null;
    /** Day buckets over the same 30 days. Empty days are absent from `points`. */
    series: UsageSeriesResponse | null;
    /** Queued work across every campaign in the org. */
    queue: QueueSummaryResponse | null;
    /** Current problems. An empty array means nothing is wrong -- a real answer. */
    alerts: AlertItem[] | null;
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
/** The window /usage/summary and /usage/series are asked for. */
const SUMMARY_DAYS = 30;
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
    const [live, setLive] = useState<LiveUsageResponse | null>(null);
    const [campaigns, setCampaigns] = useState<DashboardData['campaigns']>(null);
    const [telephony, setTelephony] = useState<TelephonyConfigurationListItem[] | null>(null);
    const [apiKeyCount, setApiKeyCount] = useState<number | null>(null);
    const [dayVolume, setDayVolume] = useState<DayVolume[] | null>(null);
    const [dispositions, setDispositions] = useState<DispositionSlice[] | null>(null);
    const [durations, setDurations] = useState<DurationBucket[] | null>(null);
    const [recentCalls, setRecentCalls] = useState<WorkflowRunUsageResponse[] | null>(null);
    const [busiestAgents, setBusiestAgents] = useState<AgentActivity[] | null>(null);
    const [busiestTruncated, setBusiestTruncated] = useState(false);
    const [summary, setSummary] = useState<UsageSummaryResponse | null>(null);
    const [series, setSeries] = useState<UsageSeriesResponse | null>(null);
    const [queue, setQueue] = useState<QueueSummaryResponse | null>(null);
    const [alerts, setAlerts] = useState<AlertItem[] | null>(null);

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

        // limit=1 because only total_count is wanted, and this is the LIFETIME
        // count -- /usage/summary is windowed, so it cannot answer this.
        jobs.push(
            guarded(async () => {
                const r = await getUsageHistoryApiV1OrganizationsUsageRunsGet({ query: { limit: 1 } });
                if (!cancelled && !r.error && r.data) setTotalCalls(r.data.total_count);
                return null;
            }),
        );

        jobs.push(
            guarded(async () => {
                const r = await getLiveUsageApiV1OrganizationsUsageLiveGet();
                if (!cancelled && !r.error && r.data) setLive(r.data);
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

        // Headline figures and the equal-length window before them, for deltas.
        jobs.push(
            guarded(async () => {
                const r = await getUsageSummaryApiV1OrganizationsUsageSummaryGet({
                    query: {
                        start_date: `${isoDateInZone(timezone, -(SUMMARY_DAYS - 1), now)}T00:00:00Z`,
                        end_date: `${today}T23:59:59Z`,
                    },
                });
                if (!cancelled && !r.error && r.data) setSummary(r.data);
                return null;
            }),
        );

        // One GROUP BY, where this used to issue TREND_DAYS count-only requests
        // -- each a subquery COUNT over a column with no index, so seven table
        // scans to draw one sparkline. The same call also carries duration,
        // charge and answer rate per bucket, which the count-only reads could
        // not have supplied at any price.
        jobs.push(
            guarded(async () => {
                const r = await getUsageSeriesApiV1OrganizationsUsageSeriesGet({
                    query: {
                        bucket: 'day',
                        start_date: `${isoDateInZone(timezone, -(SUMMARY_DAYS - 1), now)}T00:00:00Z`,
                        end_date: `${today}T23:59:59Z`,
                    },
                });
                if (cancelled || r.error || !r.data) return null;
                setSeries(r.data);

                // The series OMITS empty buckets, so reading points straight
                // into a trend line silently shortens the week and shifts every
                // bar left. Lay the points over a fixed run of days instead: a
                // day with no calls is a real zero, unlike a null charge.
                const byDate = new Map(
                    r.data.points.map((p) => [String(p.bucket ?? '').slice(0, 10), p.calls]),
                );
                setDayVolume(
                    Array.from({ length: TREND_DAYS }, (_, i) => {
                        const date = isoDateInZone(timezone, i - (TREND_DAYS - 1), now);
                        return { date, calls: byDate.get(date) ?? 0 };
                    }),
                );
                return null;
            }),
        );

        jobs.push(
            guarded(async () => {
                const r = await getQueueSummaryApiV1CampaignQueueSummaryGet();
                if (!cancelled && !r.error && r.data) setQueue(r.data);
                return null;
            }),
        );

        jobs.push(
            guarded(async () => {
                const r = await getAlertsApiV1OrganizationsReportsAlertsGet();
                if (!cancelled && !r.error && r.data) setAlerts(r.data.items);
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
        live,
        campaigns,
        summary,
        series,
        queue,
        alerts,
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
