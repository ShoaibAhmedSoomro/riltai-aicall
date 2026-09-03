import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getCurrentPeriodUsage = vi.fn();
const useAuth = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    getCurrentPeriodUsageApiV1OrganizationsUsageCurrentPeriodGet: (...args: unknown[]) =>
        getCurrentPeriodUsage(...args),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('next/navigation', () => ({ usePathname: () => '/overview' }));

import { formatDuration, formatMoney, formatPeriod, PeriodUsageMeter } from './PeriodUsageMeter';

const usage = {
    period_start: '2026-09-01T00:00:00Z',
    period_end: '2026-09-30T23:59:59Z',
    used_dograh_tokens: 0,
    total_duration_seconds: 744,
    used_amount_usd: null as number | null,
    currency: null as string | null,
    price_per_second_usd: null as number | null,
};

describe('period usage formatting', () => {
    it('keeps a decimal under ten minutes so short usage is not shown as zero', () => {
        // 24s of calls is real usage; flooring it to "0 min" would read as
        // "nothing ran", which is the whole point of not reusing the
        // per-call formatter here.
        expect(formatDuration(24)).toBe('0.4 min');
        expect(formatDuration(324)).toBe('5.4 min');
    });

    it('drops the decimal at ten minutes and above', () => {
        expect(formatDuration(744)).toBe('12 min');
        expect(formatDuration(30 * 60)).toBe('30 min');
    });

    it('switches to hours with a zero-padded remainder', () => {
        expect(formatDuration(60 * 60)).toBe('1h 00m');
        expect(formatDuration(2 * 3600 + 4 * 60)).toBe('2h 04m');
        expect(formatDuration(3 * 3600 + 3 * 60)).toBe('3h 03m');
    });

    it('treats missing, zero and nonsense durations as zero rather than NaN', () => {
        for (const value of [0, -5, Number.NaN, Number.POSITIVE_INFINITY]) {
            expect(formatDuration(value)).toBe('0 min');
        }
    });

    it('formats money in the given currency and defaults to USD', () => {
        expect(formatMoney(1.5, 'USD')).toContain('1.50');
        expect(formatMoney(1.5, null)).toContain('1.50');
        expect(formatMoney(1.5, 'usd')).toContain('1.50');
    });

    it('survives a currency code Intl does not know', () => {
        // Intl.NumberFormat throws a RangeError on an invalid code; the amount
        // still has to reach the operator.
        const out = formatMoney(12.34, 'NOTACURRENCY');
        expect(out).toContain('12.34');
        expect(out).toContain('NOTACURRENCY');
    });

    it('returns null for an unparseable period instead of "Invalid Date"', () => {
        expect(formatPeriod('not-a-date', 'also-not')).toBeNull();
        expect(formatPeriod(usage.period_start, usage.period_end)).toBeTruthy();
    });
});

describe('PeriodUsageMeter', () => {
    beforeEach(() => {
        useAuth.mockReturnValue({ user: { id: 'u1' }, loading: false });
        getCurrentPeriodUsage.mockReset();
    });

    afterEach(() => {
        vi.clearAllMocks();
    });

    async function renderAndSettle() {
        render(<PeriodUsageMeter />);
        // let the effect's promise resolve and React commit the result
        await vi.waitFor(() => expect(getCurrentPeriodUsage).toHaveBeenCalled());
        await new Promise((r) => setTimeout(r, 0));
    }

    it('shows the period duration once usage loads', async () => {
        getCurrentPeriodUsage.mockResolvedValue({ data: usage, error: undefined });
        await renderAndSettle();

        expect(await screen.findByText('12 min')).toBeDefined();
        expect(screen.getByRole('link')).toHaveProperty('href', expect.stringContaining('/usage'));
    });

    it('adds spend only when the period is actually priced', async () => {
        getCurrentPeriodUsage.mockResolvedValue({
            data: { ...usage, used_amount_usd: 4.2, currency: 'USD' },
            error: undefined,
        });
        await renderAndSettle();

        expect(await screen.findByText('12 min')).toBeDefined();
        expect(screen.getByText(/4\.20/)).toBeDefined();
    });

    it('renders nothing for a BYOK install with no priced amount', async () => {
        getCurrentPeriodUsage.mockResolvedValue({ data: usage, error: undefined });
        await renderAndSettle();

        // duration still shows, but no currency figure is invented
        expect(screen.queryByText(/\$/)).toBeNull();
    });

    // The generated client RESOLVES on 4xx/5xx rather than throwing, so an
    // unchecked `error` would have rendered a meter built from undefined.
    it('renders nothing when the request returns an error payload', async () => {
        getCurrentPeriodUsage.mockResolvedValue({
            data: undefined,
            error: { detail: 'No organization selected' },
        });
        await renderAndSettle();

        expect(screen.queryByRole('link')).toBeNull();
    });

    it('renders nothing when the request throws outright', async () => {
        getCurrentPeriodUsage.mockRejectedValue(new Error('network down'));
        await renderAndSettle();

        expect(screen.queryByRole('link')).toBeNull();
    });

    it('does not refetch when the auth provider hands back a new user object', async () => {
        // The hosted auth path gets `user` from the Stack SDK's own hook. If that
        // returns a fresh object per render, keying the effect off the object
        // would fire a request on every render of the app header.
        getCurrentPeriodUsage.mockResolvedValue({ data: usage, error: undefined });
        const { rerender } = render(<PeriodUsageMeter />);
        await vi.waitFor(() => expect(getCurrentPeriodUsage).toHaveBeenCalledTimes(1));

        for (let i = 0; i < 3; i += 1) {
            // same id, different identity each time
            useAuth.mockReturnValue({ user: { id: 'u1' }, loading: false });
            rerender(<PeriodUsageMeter />);
            await new Promise((r) => setTimeout(r, 0));
        }

        expect(getCurrentPeriodUsage).toHaveBeenCalledTimes(1);
    });

    it('does not call the API before auth has finished loading', () => {
        useAuth.mockReturnValue({ user: null, loading: true });
        render(<PeriodUsageMeter />);

        // Fetching before the auth interceptor is registered sends an
        // unauthenticated request that fails silently.
        expect(getCurrentPeriodUsage).not.toHaveBeenCalled();
        expect(screen.queryByRole('link')).toBeNull();
    });
});
