import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AnalysisResults } from './AnalysisResults';

/**
 * Three states, not two.
 *
 * A configured field or check can have passed, failed, or never been assessed.
 * "Not analysed" happens for real reasons — the model omitted the key, the
 * value would not coerce to its declared type, or the analysis call failed —
 * and rendering any of those as a value is a stronger claim than the raw JSON
 * dump this replaces ever made.
 *
 * The two easy ways to break it are both pinned below: treating a falsy value
 * as missing, and treating a missing check as a failing one.
 */

const analysis = (a: Record<string, unknown>) => ({ qa_node1: { analysis: a } });

describe('what was asked vs what came back', () => {
    it('renders a configured field the model never returned as not analysed', () => {
        render(
            <AnalysisResults
                annotations={analysis({
                    fields: [
                        { name: 'caller_email', type: 'string' },
                        { name: 'ticket_count', type: 'number' },
                    ],
                    extracted: { caller_email: 'a@b.com' },
                })}
            />,
        );
        expect(screen.getByText('a@b.com')).toBeTruthy();
        expect(screen.getByText('ticket_count')).toBeTruthy();
        expect(screen.getAllByText(/not analysed/i)).toHaveLength(1);
    });

    it('renders a real false and a real zero as values, not as missing', () => {
        // `if (!value)` discards both. They are answers.
        render(
            <AnalysisResults
                annotations={analysis({
                    fields: [
                        { name: 'consented', type: 'boolean' },
                        { name: 'ticket_count', type: 'number' },
                    ],
                    extracted: { consented: false, ticket_count: 0 },
                })}
            />,
        );
        expect(screen.getByText('No')).toBeTruthy();
        expect(screen.getByText('0')).toBeTruthy();
        expect(screen.queryByText(/not analysed/i)).toBeNull();
    });

    it('shows an unassessed check as neither passed nor failed', () => {
        const { container } = render(
            <AnalysisResults
                annotations={analysis({
                    checks_configured: ['greeted', 'disclosed', 'unassessed'],
                    checks: [
                        { name: 'greeted', passed: true, reason: 'said hello' },
                        { name: 'disclosed', passed: false, reason: 'no disclosure' },
                    ],
                })}
            />,
        );
        // All three are listed, because all three were asked.
        for (const name of ['greeted', 'disclosed', 'unassessed']) {
            expect(screen.getByText(name)).toBeTruthy();
        }
        expect(screen.getByText('no disclosure')).toBeTruthy();
        expect(screen.getAllByText(/not analysed/i)).toHaveLength(1);

        // The ICON is what a reader actually reads, and it is the easy thing to
        // get wrong: a `check?.passed ? pass : fail` ternary paints an
        // unassessed check with the failure mark, asserting a verdict nobody
        // reached. Exactly one pass mark and one failure mark, for the two
        // checks that have verdicts.
        expect(container.querySelectorAll('.text-emerald-600')).toHaveLength(1);
        expect(container.querySelectorAll('.text-destructive')).toHaveLength(1);
        // And the mark itself, which is the only state signal a check without
        // reason text has: an unassessed check must not carry the failure mark.
        expect(screen.getByLabelText('Passed')).toBeTruthy();
        expect(screen.getByLabelText('Failed')).toBeTruthy();
        expect(screen.getByLabelText('Not analysed')).toBeTruthy();
    });

    it('shows a score only when one was returned, and keeps a zero', () => {
        render(
            <AnalysisResults
                annotations={analysis({
                    checks_configured: ['scored', 'unscored', 'zeroed'],
                    checks: [
                        { name: 'scored', passed: true, score: 87 },
                        { name: 'unscored', passed: true, score: null },
                        { name: 'zeroed', passed: false, score: 0 },
                    ],
                })}
            />,
        );
        expect(screen.getByText('87')).toBeTruthy();
        // A legitimate 0 must render; `score && ...` would drop it.
        expect(screen.getByText('0')).toBeTruthy();
    });
});

describe('what it declines to render', () => {
    it('renders nothing when no QA node configured any analysis', () => {
        const { container } = render(
            <AnalysisResults annotations={{ qa_node1: { analysis: {} }, embed: { source: 'x' } }} />,
        );
        expect(container.textContent).toBe('');
    });

    it('renders nothing for annotations that are not QA analysis', () => {
        // `annotations` is a shared merge target: run_completion_handlers
        // merges third-party integration results into the same column. One of
        // those carrying a key called `analysis` must not be rendered as QA
        // output -- only `qa_*` entries are.
        const { container } = render(
            <AnalysisResults
                annotations={{
                    embed: { source: 'embed_widget' },
                    noveum: { analysis: { fields: [{ name: 'not_ours', type: 'string' }] } },
                }}
            />,
        );
        expect(container.textContent).toBe('');
    });

    it('renders nothing when there are no annotations at all', () => {
        const { container } = render(<AnalysisResults annotations={null} />);
        expect(container.textContent).toBe('');
    });

    it('says the analysis did not complete rather than showing empty results', () => {
        render(
            <AnalysisResults
                annotations={analysis({
                    fields: [{ name: 'caller_email', type: 'string' }],
                    checks_configured: [],
                    error: 'provider exploded',
                })}
            />,
        );
        expect(screen.getByText(/did not complete/i)).toBeTruthy();
        expect(screen.getByText(/not analysed/i)).toBeTruthy();
        // The upstream error text is not shown: it is an internal provider
        // message, not something the reader can act on.
        expect(screen.queryByText(/provider exploded/i)).toBeNull();
    });
});
