import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';

import type { UsageSummaryResponse } from '@/client/types.gen';

import {
    AlertsPanel,
    AnswerRatePanel,
    ContactRatePanel,
    PipelinePanel,
    SpendPanel,
    UnitEconomicsPanel,
} from './RealPanels';

/**
 * The one rule these panels exist to keep: unknown is never drawn as zero.
 *
 * Nine sample panels were retired into these. The sample versions could show a
 * confident $0.00 or 0% because the figures were invented; the real ones get a
 * null from the API whenever nothing was priced or no calls were placed, and a
 * null rendered as zero is a stronger claim than the sample badge ever made --
 * it says "we measured this, and it is nothing".
 *
 * A failed fetch is a third state again, and must stay distinguishable from
 * both. All three are asserted below.
 */

beforeAll(() => {
    // recharts' ResponsiveContainer observes its box; jsdom has no
    // ResizeObserver, and without it every chart panel throws on render.
    if (!('ResizeObserver' in globalThis)) {
        (globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
            observe() {}
            unobserve() {}
            disconnect() {}
        };
    }
});

const WINDOW = {
    period_start: '2026-08-20',
    period_end: '2026-09-18',
    total_runs: 0,
    call_runs: 0,
    answered_runs: 0,
    unanswered_runs: 0,
    voicemail_runs: 0,
    qualified_runs: 0,
    transferred_runs: 0,
    answer_rate_pct: null,
    total_duration_seconds: 0,
    avg_duration_seconds: null,
    total_charge_usd: null,
    distinct_agents: 0,
};

const summary = (over: Partial<UsageSummaryResponse> = {}): UsageSummaryResponse =>
    ({ ...WINDOW, previous: { ...WINDOW }, ...over }) as UsageSummaryResponse;

const series = (points: Record<string, unknown>[] = []) =>
    ({ bucket: 'day', timezone: 'UTC', truncated: false, points }) as never;

const queue = (over: Record<string, number> = {}) =>
    ({
        total: 0,
        queued: 0,
        processing: 0,
        processed: 0,
        failed: 0,
        retrying: 0,
        scheduled: 0,
        campaigns: 0,
        ...over,
    }) as never;

describe('unknown is never rendered as zero', () => {
    it('unpriced calls say so instead of showing $0.00', () => {
        render(
            <SpendPanel
                summary={summary({ total_runs: 12, total_charge_usd: null })}
                series={series()}
                loading={false}
            />,
        );
        expect(screen.getByText(/no calls have been priced yet/i)).toBeTruthy();
        expect(screen.queryByText('$0.00')).toBeNull();
    });

    it('no calls placed says so instead of showing a 0% answer rate', () => {
        render(<AnswerRatePanel summary={summary()} series={series()} loading={false} />);
        // "0%" would be a claim that calls were placed and none connected.
        expect(screen.getByText(/no calls were placed/i)).toBeTruthy();
        expect(screen.queryByText('0%')).toBeNull();
    });

    it('a failed fetch is distinguishable from an empty one', () => {
        const { unmount } = render(<SpendPanel summary={null} series={null} loading={false} />);
        expect(screen.getByText(/could not be loaded/i)).toBeTruthy();
        unmount();

        render(
            <SpendPanel summary={summary()} series={series()} loading={false} />,
        );
        expect(screen.queryByText(/could not be loaded/i)).toBeNull();
        expect(screen.getByText(/no calls have been priced yet/i)).toBeTruthy();
    });

    it('unit economics names the missing source per row rather than zeroing it', () => {
        render(
            <UnitEconomicsPanel
                summary={summary({ total_runs: 5, avg_duration_seconds: 90 })}
                series={series()}
                loading={false}
            />,
        );
        // Duration is measured, cost is not -- so one row has a value and the
        // others say what they need. Neither is $0.00.
        expect(screen.getByText('1m 30s')).toBeTruthy();
        expect(screen.getAllByText(/needs a rate card/i).length).toBe(2);
        expect(screen.queryByText('$0.00')).toBeNull();
    });
});

describe('alerts', () => {
    it('an empty list means nothing is wrong, which is not the same as a failure', () => {
        const { unmount } = render(<AlertsPanel alerts={[]} loading={false} />);
        expect(screen.getByText(/nothing needs attention/i)).toBeTruthy();
        unmount();

        render(<AlertsPanel alerts={null} loading={false} />);
        expect(screen.getByText(/could not be loaded/i)).toBeTruthy();
    });

    it('renders an unrecognised severity rather than crashing on it', () => {
        // The endpoint emits error/warning today. A value added later must not
        // take the panel down with it.
        render(
            <AlertsPanel
                alerts={[{ severity: 'catastrophe', text: 'the roof is on fire', href: '/usage', count: 1 }]}
                loading={false}
            />,
        );
        expect(screen.getByText('the roof is on fire')).toBeTruthy();
    });
});

describe('queue-backed panels', () => {
    it('the contact rate says it counts campaign audiences, not people', () => {
        // There is no contact entity in this system, so an unqualified
        // "contact rate" would read as a per-person figure.
        render(<ContactRatePanel queue={queue({ total: 10, processed: 4, queued: 6 })} loading={false} />);
        expect(screen.getByText(/campaign audience rows/i)).toBeTruthy();
        expect(screen.getByText('40%')).toBeTruthy();
    });

    it('keeps retrying and scheduled out of the segments they overlap', () => {
        // retrying and scheduled are views over `queued`, not states beside it.
        // Counting them as segments would make the ring exceed the total.
        render(
            <PipelinePanel
                queue={queue({ total: 10, queued: 6, processed: 4, retrying: 2, scheduled: 3 })}
                loading={false}
            />,
        );
        expect(screen.getByText(/retrying \(of queued\)/i)).toBeTruthy();
        expect(screen.getByText(/scheduled \(of queued\)/i)).toBeTruthy();

        // The real check: the segment percentages are a partition, so they sum
        // to 100. Promoting retrying or scheduled to a segment pushes this to
        // 150 while every individual number still looks plausible.
        const pcts = screen.getAllByText(/^\d+%$/).map((el) => Number(el.textContent!.replace('%', '')));
        expect(pcts.reduce((a, b) => a + b, 0)).toBe(100);
        // 6 queued + 4 processed = the 10 in the middle.
        expect(screen.getByText('10')).toBeTruthy();
    });
});
