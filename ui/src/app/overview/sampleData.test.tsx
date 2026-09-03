import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';

import * as SamplePanels from './components/SamplePanels';
import { SAMPLE_PANEL_IDS } from './sampleData';

/**
 * The honesty invariant.
 *
 * Filling the unmeasured panels with placeholder figures is only acceptable
 * while every one of them says so on screen. A panel that quietly loses its
 * badge becomes a fabricated number presented as measured, which is the one
 * outcome this whole arrangement exists to prevent. So it is asserted, not
 * trusted to review.
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

/** Every exported component in SamplePanels, so a new one cannot slip through. */
const EXPORTED = Object.entries(SamplePanels).filter(
    ([name, value]) => typeof value === 'function' && /^[A-Z]/.test(name),
) as [string, () => React.ReactElement][];

describe('sample panels', () => {
    it('exports something for every declared sample panel id', () => {
        // SAMPLE_PANEL_IDS drives the count in the page banner, so it drifting
        // from reality would understate or overstate what is illustrative.
        expect(EXPORTED.length).toBeGreaterThanOrEqual(SAMPLE_PANEL_IDS.length);
    });

    it.each(EXPORTED)('%s is labelled as sample', (_name, Component) => {
        render(<Component />);
        // Either the Panel badge or the inline tile badge; both read "Sample".
        expect(screen.getAllByText(/^sample$/i).length).toBeGreaterThan(0);
    });

    it('renders no panel without a badge', () => {
        for (const [name, Component] of EXPORTED) {
            const { unmount } = render(<Component />);
            const badges = screen.queryAllByText(/^sample$/i);
            expect(badges.length, `${name} rendered no Sample badge`).toBeGreaterThan(0);
            unmount();
        }
    });
});

describe('sample data hygiene', () => {
    it('never reaches the real data path', () => {
        // If useDashboardData ever imported sampleData, a placeholder could
        // surface inside a panel that presents itself as measured. The source
        // is asserted directly rather than the runtime graph, because an unused
        // import would still be a loaded gun.
        // readFileSync rather than a ?raw import: vite resolves ?raw but tsc
        // has no type for it, and this matches publicEmbedWidget.test.ts.
        const hook = readFileSync(
            resolve(process.cwd(), 'src/app/overview/useDashboardData.ts'),
            'utf8',
        );
        expect(hook).toContain('getUsageHistoryApiV1');
        expect(hook).not.toMatch(/from '\.\/sampleData'/);
        expect(hook.toLowerCase()).not.toContain('sample_');
    });

    it('declares every sample panel id in one list the banner can count', () => {
        expect(new Set(SAMPLE_PANEL_IDS).size).toBe(SAMPLE_PANEL_IDS.length);
        expect(SAMPLE_PANEL_IDS.length).toBeGreaterThan(0);
    });
});
