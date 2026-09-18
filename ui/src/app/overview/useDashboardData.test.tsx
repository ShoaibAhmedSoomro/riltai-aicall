import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getWorkflowCount = vi.fn();
const getUsageHistory = vi.fn();
const getCurrentPeriodUsage = vi.fn();
const getDailyReport = vi.fn();
const getCampaigns = vi.fn();
const listTelephony = vi.fn();
const getApiKeys = vi.fn();
const getLiveUsage = vi.fn();
const getUsageSummary = vi.fn();
const getUsageSeries = vi.fn();
const getQueueSummary = vi.fn();
const getAlerts = vi.fn();
const useAuth = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    getWorkflowCountApiV1WorkflowCountGet: (...a: unknown[]) => getWorkflowCount(...a),
    getUsageHistoryApiV1OrganizationsUsageRunsGet: (...a: unknown[]) => getUsageHistory(...a),
    getCurrentPeriodUsageApiV1OrganizationsUsageCurrentPeriodGet: (...a: unknown[]) =>
        getCurrentPeriodUsage(...a),
    getDailyReportApiV1OrganizationsReportsDailyGet: (...a: unknown[]) => getDailyReport(...a),
    getCampaignsApiV1CampaignGet: (...a: unknown[]) => getCampaigns(...a),
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: (...a: unknown[]) =>
        listTelephony(...a),
    getApiKeysApiV1UserApiKeysGet: (...a: unknown[]) => getApiKeys(...a),
    getLiveUsageApiV1OrganizationsUsageLiveGet: (...a: unknown[]) => getLiveUsage(...a),
    getUsageSummaryApiV1OrganizationsUsageSummaryGet: (...a: unknown[]) => getUsageSummary(...a),
    getUsageSeriesApiV1OrganizationsUsageSeriesGet: (...a: unknown[]) => getUsageSeries(...a),
    getQueueSummaryApiV1CampaignQueueSummaryGet: (...a: unknown[]) => getQueueSummary(...a),
    getAlertsApiV1OrganizationsReportsAlertsGet: (...a: unknown[]) => getAlerts(...a),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));

import { useDashboardData } from './useDashboardData';

/** Renders the hook and prints the fields under test into the DOM. */
function Probe({ tz }: { tz?: string }) {
    const d = useDashboardData(tz ?? 'UTC');
    return (
        <div>
            <span data-testid="loading">{String(d.loading)}</span>
            <span data-testid="total">{String(d.totalCalls)}</span>
            <span data-testid="talk">{String(d.period?.total_duration_seconds ?? 'null')}</span>
            <span data-testid="week">{(d.dayVolume ?? []).map((x) => x.calls).join(',')}</span>
            <span data-testid="days">{(d.dayVolume ?? []).map((x) => x.date).join(',')}</span>
            <span data-testid="campaigns">{d.campaigns ? String(d.campaigns.total) : 'null'}</span>
            <span data-testid="running">{d.campaigns ? String(d.campaigns.byState.running ?? 0) : 'null'}</span>
            <span data-testid="agents">{d.busiestAgents?.map((a) => `${a.workflowName}:${a.calls}`).join('|')}</span>
            <span data-testid="truncated">{String(d.busiestAgentsTruncated)}</span>
            <span data-testid="keys">{String(d.apiKeyCount)}</span>
            <span data-testid="live">{d.live ? String(d.live.active_calls) : 'null'}</span>
            <span data-testid="limit">{d.live ? String(d.live.concurrent_call_limit) : 'null'}</span>
            <span data-testid="summary">{d.summary ? String(d.summary.total_runs) : 'null'}</span>
            <span data-testid="previous">{d.summary ? String(d.summary.previous.total_runs) : 'null'}</span>
            <span data-testid="queue">{d.queue ? String(d.queue.total) : 'null'}</span>
            <span data-testid="alerts">{d.alerts ? String(d.alerts.length) : 'null'}</span>
        </div>
    );
}

const ok = <T,>(data: T) => ({ data, error: undefined });

function settle() {
    // let the effect's Promise.all chain flush
    return new Promise((r) => setTimeout(r, 0));
}

beforeEach(() => {
    useAuth.mockReturnValue({ user: { id: 'u1' }, loading: false });
    for (const fn of [
        getWorkflowCount,
        getUsageHistory,
        getCurrentPeriodUsage,
        getDailyReport,
        getCampaigns,
        listTelephony,
        getApiKeys,
        getUsageSummary,
        getUsageSeries,
        getQueueSummary,
        getAlerts,
    ]) {
        fn.mockReset();
    }
    // Sensible defaults; individual tests override what they exercise.
    getWorkflowCount.mockResolvedValue(ok({ total: 3, active: 2, archived: 1 }));
    getCurrentPeriodUsage.mockResolvedValue(
        ok({ period_start: '2026-09-01', period_end: '2026-09-30', used_dograh_tokens: 0, total_duration_seconds: 900 }),
    );
    getDailyReport.mockResolvedValue(
        ok({ metrics: { total_runs: 4 }, disposition_distribution: [], call_duration_distribution: [] }),
    );
    getLiveUsage.mockResolvedValue(
        ok({ active_calls: 2, concurrent_call_limit: 10, running_runs: 2 }),
    );
    getCampaigns.mockResolvedValue(ok({ campaigns: [] }));
    listTelephony.mockResolvedValue(ok({ configurations: [] }));
    getApiKeys.mockResolvedValue(ok([]));
    getUsageHistory.mockResolvedValue(ok({ runs: [], total_count: 0, total_duration_seconds: 0, total_rilt_tokens: 0, page: 1, limit: 1, total_pages: 0 }));
    getUsageSummary.mockResolvedValue(
        ok({
            period_start: '2026-08-20', period_end: '2026-09-18', total_runs: 10, call_runs: 10,
            answered_runs: 6, unanswered_runs: 4, voicemail_runs: 0, qualified_runs: 2,
            transferred_runs: 1, answer_rate_pct: 60, total_duration_seconds: 600,
            total_charge_usd: null, distinct_agents: 2,
            previous: {
                period_start: '2026-07-21', period_end: '2026-08-19', total_runs: 5, call_runs: 5,
                answered_runs: 2, unanswered_runs: 3, voicemail_runs: 0, qualified_runs: 1,
                transferred_runs: 0, answer_rate_pct: 40, total_duration_seconds: 300,
                total_charge_usd: null, distinct_agents: 1,
            },
        }),
    );
    getUsageSeries.mockResolvedValue(ok({ bucket: 'day', timezone: 'UTC', truncated: false, points: [] }));
    getQueueSummary.mockResolvedValue(
        ok({ total: 0, queued: 0, processing: 0, processed: 0, failed: 0, retrying: 0, scheduled: 0, campaigns: 0 }),
    );
    getAlerts.mockResolvedValue(ok({ items: [] }));
});

afterEach(() => vi.clearAllMocks());

describe('dashboard accuracy guarantees', () => {
    it('takes the lifetime call count from total_count, never from the page sum', async () => {
        // total_duration_seconds was page-scoped when this was written, so the
        // hook reads total_count instead. The endpoint aggregates properly now,
        // but the decoy value below still proves the hook takes the count from
        // total_count rather than inferring it from anything else.
        getUsageHistory.mockResolvedValue(
            ok({
                runs: [],
                total_count: 8123,
                total_duration_seconds: 42, // page-scoped decoy
                total_rilt_tokens: 0,
                page: 1,
                limit: 1,
                total_pages: 8123,
            }),
        );
        render(<Probe />);
        await settle();

        expect(screen.getByTestId('total').textContent).toBe('8123');
        // talk time must come from the period endpoint, not the decoy above
        expect(screen.getByTestId('talk').textContent).toBe('900');
    });

    it('requests the lifetime count with limit 1 so no rows are hydrated', async () => {
        render(<Probe />);
        await settle();

        const calls = getUsageHistory.mock.calls.map((c) => c[0]?.query ?? {});
        const lifetime = calls.filter((q) => !q.start_date && q.limit === 1);
        expect(lifetime.length).toBeGreaterThan(0);
    });

    it('builds the weekly trend from one series call, not seven dated counts', async () => {
        // This used to issue TREND_DAYS count-only /usage/runs requests, each an
        // unindexed COUNT. One GROUP BY replaces them.
        render(<Probe />);
        await settle();

        expect(getUsageSeries).toHaveBeenCalledTimes(1);
        expect(getUsageSeries.mock.calls[0][0].query.bucket).toBe('day');
        const dated = getUsageHistory.mock.calls
            .map((c) => c[0]?.query ?? {})
            .filter((q) => q.start_date);
        expect(dated).toHaveLength(0);

        // Seven distinct ascending days regardless of what came back.
        const days = screen.getByTestId('days').textContent!.split(',');
        expect(new Set(days).size).toBe(7);
        expect([...days].sort().join(',')).toBe(days.join(','));
    });

    it('fills the days the series omits with zero, without shifting the rest', async () => {
        // /usage/series omits empty buckets. Reading its points straight into
        // the trend shortens the week and slides every bar left, so a quiet
        // Tuesday would silently relabel Monday's calls as Tuesday's.
        const iso = (offset: number) =>
            new Intl.DateTimeFormat('en-CA', {
                timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit',
            }).format(new Date(Date.now() + offset * 86_400_000));

        getUsageSeries.mockResolvedValue(
            ok({
                bucket: 'day',
                timezone: 'UTC',
                truncated: false,
                // Only two of the seven days had calls, and they are not adjacent.
                points: [
                    { bucket: iso(-6) + 'T00:00:00+00:00', calls: 11, duration_seconds: 60, charge_usd: null, answer_rate_pct: null },
                    { bucket: iso(0) + 'T00:00:00+00:00', calls: 22, duration_seconds: 60, charge_usd: null, answer_rate_pct: null },
                ],
            }),
        );
        render(<Probe />);
        await settle();

        expect(screen.getByTestId('week').textContent).toBe('11,0,0,0,0,0,22');
        expect(screen.getByTestId('days').textContent!.split(',')).toHaveLength(7);
    });

    it('exposes the previous window through the summary rather than copying it', async () => {
        render(<Probe />);
        await settle();
        // Two copies of one number is how they drift apart, so the hook keeps
        // exactly one: summary.previous.
        expect(screen.getByTestId('summary').textContent).toBe('10');
        expect(screen.getByTestId('previous').textContent).toBe('5');
    });

    it('an empty alerts list means nothing is wrong, not that alerts failed', async () => {
        render(<Probe />);
        await settle();
        expect(screen.getByTestId('alerts').textContent).toBe('0');

        // A failing endpoint is the other thing, and must stay distinguishable.
        getAlerts.mockResolvedValue({ data: undefined, error: { detail: 'nope' } });
        render(<Probe />);
        await settle();
        expect(screen.getAllByTestId('alerts').pop()!.textContent).toBe('null');
    });

    it('reads campaigns out of the envelope and groups them by state', async () => {
        // The endpoint returns { campaigns: [...] }, not a bare array; treating
        // it as an array silently yields zero campaigns.
        getCampaigns.mockResolvedValue(
            ok({
                campaigns: [
                    { id: 1, state: 'running', total_rows: 100, processed_rows: 40 },
                    { id: 2, state: 'running', total_rows: 10, processed_rows: 10 },
                    { id: 3, state: 'completed', total_rows: 5, processed_rows: 5 },
                ],
            }),
        );
        render(<Probe />);
        await settle();

        expect(screen.getByTestId('campaigns').textContent).toBe('3');
        expect(screen.getByTestId('running').textContent).toBe('2');
    });

    it('counts only active API keys', async () => {
        getApiKeys.mockResolvedValue(
            ok([
                { id: 1, is_active: true },
                { id: 2, is_active: false },
                { id: 3, is_active: true },
            ]),
        );
        render(<Probe />);
        await settle();

        expect(screen.getByTestId('keys').textContent).toBe('2');
    });

    it('tallies agents from the returned runs and flags a truncated window', async () => {
        getUsageHistory.mockImplementation(({ query }: { query?: Record<string, unknown> }) => {
            if (query?.limit === 100) {
                return Promise.resolve(
                    ok({
                        runs: [
                            { id: 1, workflow_id: 7, workflow_name: 'Alpha', name: 'r1', created_at: '2026-09-03T10:00:00Z', call_duration_seconds: 60, rilt_token_usage: 0 },
                            { id: 2, workflow_id: 7, workflow_name: 'Alpha', name: 'r2', created_at: '2026-09-03T10:01:00Z', call_duration_seconds: 30, rilt_token_usage: 0 },
                            { id: 3, workflow_id: 9, workflow_name: 'Beta', name: 'r3', created_at: '2026-09-03T10:02:00Z', call_duration_seconds: 10, rilt_token_usage: 0 },
                        ],
                        total_count: 500, // more than the page: window is partial
                        total_duration_seconds: 100,
                        total_rilt_tokens: 0,
                        page: 1,
                        limit: 100,
                        total_pages: 5,
                    }),
                );
            }
            return Promise.resolve(
                ok({ runs: [], total_count: 500, total_duration_seconds: 0, total_rilt_tokens: 0, page: 1, limit: 1, total_pages: 5 }),
            );
        });
        render(<Probe />);
        await settle();

        expect(screen.getByTestId('agents').textContent).toBe('Alpha:2|Beta:1');
        // The UI relabels itself when true, so this must not silently be false.
        expect(screen.getByTestId('truncated').textContent).toBe('true');
    });

    it('leaves a widget null when its own endpoint fails, without blanking the rest', async () => {
        getWorkflowCount.mockResolvedValue({ data: undefined, error: { detail: 'boom' } });
        getDailyReport.mockRejectedValue(new Error('network'));
        render(<Probe />);
        await settle();

        // the failures are isolated: the period endpoint still populated
        expect(screen.getByTestId('talk').textContent).toBe('900');
        expect(screen.getByTestId('loading').textContent).toBe('false');
    });

    it('does not call anything before auth settles', () => {
        useAuth.mockReturnValue({ user: null, loading: true });
        render(<Probe />);

        expect(getUsageHistory).not.toHaveBeenCalled();
        expect(getDailyReport).not.toHaveBeenCalled();
    });
});

describe('live concurrency', () => {
    it('exposes the live figures', async () => {
        render(<Probe />);
        await settle();
        expect(screen.getByTestId('live').textContent).toBe('2');
        expect(screen.getByTestId('limit').textContent).toBe('10');
    });

    it('keeps active_calls null when Redis could not answer', async () => {
        // The endpoint answers 200 with a null count rather than 503, because
        // this is a tile and not an autoscaling signal. null must survive to
        // the UI: rendering it as 0 would report an idle system.
        getLiveUsage.mockResolvedValue(
            ok({ active_calls: null, concurrent_call_limit: 10, running_runs: 3 }),
        );
        render(<Probe />);
        await settle();
        expect(screen.getByTestId('live').textContent).toBe('null');
        // The limit still came back, so the tile is not "unavailable" -- it is
        // available and does not know the count.
        expect(screen.getByTestId('limit').textContent).toBe('10');
    });

    it('degrades only its own tile when the request fails', async () => {
        getLiveUsage.mockResolvedValue({ error: { detail: 'nope' } });
        render(<Probe />);
        await settle();
        expect(screen.getByTestId('live').textContent).toBe('null');
        // Every other figure still loaded: one endpoint failing must not blank
        // the page.
        expect(screen.getByTestId('total').textContent).not.toBe('null');
    });
});
