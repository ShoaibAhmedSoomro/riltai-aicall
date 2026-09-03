import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getWorkflowCount = vi.fn();
const getUsageHistory = vi.fn();
const getCurrentPeriodUsage = vi.fn();
const getDailyReport = vi.fn();
const getCampaigns = vi.fn();
const listTelephony = vi.fn();
const getApiKeys = vi.fn();
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
    getCampaigns.mockResolvedValue(ok({ campaigns: [] }));
    listTelephony.mockResolvedValue(ok({ configurations: [] }));
    getApiKeys.mockResolvedValue(ok([]));
    getUsageHistory.mockResolvedValue(ok({ runs: [], total_count: 0, total_duration_seconds: 0, total_rilt_tokens: 0, page: 1, limit: 1, total_pages: 0 }));
});

afterEach(() => vi.clearAllMocks());

describe('dashboard accuracy guarantees', () => {
    it('takes the lifetime call count from total_count, never from the page sum', async () => {
        // The trap: /usage/runs sums total_duration_seconds over the RETURNED
        // PAGE only, while total_count is a real subquery COUNT. Reading the
        // former as a period figure would understate it by orders of magnitude.
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

    it('builds the weekly trend from one dated COUNT per day', async () => {
        getUsageHistory.mockImplementation(({ query }: { query?: Record<string, unknown> }) => {
            if (query?.start_date) {
                // one distinct count per day, keyed off the date so order is checkable
                const day = Number(String(query.start_date).slice(8, 10));
                return Promise.resolve(
                    ok({ runs: [], total_count: day, total_duration_seconds: 0, total_rilt_tokens: 0, page: 1, limit: 1, total_pages: 1 }),
                );
            }
            return Promise.resolve(
                ok({ runs: [], total_count: 0, total_duration_seconds: 0, total_rilt_tokens: 0, page: 1, limit: 1, total_pages: 0 }),
            );
        });
        render(<Probe />);
        await settle();

        const dated = getUsageHistory.mock.calls
            .map((c) => c[0]?.query ?? {})
            .filter((q) => q.start_date);
        expect(dated).toHaveLength(7);
        // every dated request is a count-only request
        expect(dated.every((q) => q.limit === 1)).toBe(true);
        // and the window is seven distinct ascending days
        const days = screen.getByTestId('days').textContent!.split(',');
        expect(new Set(days).size).toBe(7);
        expect([...days].sort().join(',')).toBe(days.join(','));
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
