/**
 * Illustrative figures for the three dashboard panels that still have no data
 * source. Nothing in this file is real.
 *
 * Nine panels used to be fed from here. They are gone, replaced by
 * components/RealPanels.tsx reading /usage/summary, /usage/series,
 * /campaign/queue-summary and /organizations/reports/alerts. Two were deleted
 * outright rather than replaced:
 *
 *   margin vs cost   AICall never learns what an operator bills their own
 *                    end-customer, so margin is unknowable IN PRINCIPLE, not
 *                    merely unmeasured. A badged invention of it should not
 *                    persist just because the slot exists.
 *   agent health     open / in review / resolved / overdue describes an issue
 *                    tracker. No such thing is in the schema or in any planned
 *                    workstream.
 *
 * The three that remain, and why each is still sample rather than lazy:
 *
 *   contacts     no contacts table exists -- verified by enumerating every
 *                __tablename__ in api/db/models.py. That domain is separate
 *                work, not a query someone forgot to write.
 *   compliance   retention and PII settings belong to the data-governance
 *                workstream, which owns the fields this would read.
 *   regions      nothing stores a region per call. The only geo data in the
 *                tree is COUNTRY_CODES, 21 ISO-to-dial-prefix entries with an
 *                ambiguous reverse lookup; a real panel needs a
 *                number-to-country dataset, i.e. a new dependency.
 *
 * Every panel fed from here renders a "Sample" badge, and the dashboard shows
 * one banner saying so. Real and sample numbers are never mixed inside a single
 * panel.
 *
 * SAMPLE_PANEL_IDS now has exactly as many entries as SamplePanels.tsx has
 * component exports, so sampleData.test.tsx passes at 3 >= 3 with no slack.
 * That is the point: from here on, deleting a component without removing its id
 * -- or the reverse -- fails the suite loudly instead of quietly overstating or
 * understating what is measured.
 */

export const SAMPLE_PANEL_IDS = ['contacts', 'compliance', 'regions'] as const;

export type SamplePanelId = (typeof SAMPLE_PANEL_IDS)[number];

/** Four-stat operational panel. */
export const SAMPLE_CONTACTS = {
    stats: [
        { label: 'Total contacts', value: '1,084' },
        { label: 'Reachable', value: '1,152' },
        { label: 'New (MTD)', value: '24' },
        { label: 'Opted out', value: '16' },
    ],
    footer: [
        { label: 'Retention', value: '85%' },
        { label: 'Avg list age', value: '24 months' },
        { label: 'Bounce rate', value: '3.8%' },
        { label: 'Sentiment', value: '4.6 / 5' },
    ],
};

/** The three-state compliance table. */
export const SAMPLE_COMPLIANCE = [
    { item: 'Consent records', ok: 18, dueSoon: 4, overdue: 2 },
    { item: 'DNC list refresh', ok: 20, dueSoon: 3, overdue: 1 },
    { item: 'Recording retention', ok: 15, dueSoon: 6, overdue: 3 },
    { item: 'Caller ID attestation', ok: 21, dueSoon: 2, overdue: 1 },
    { item: 'Script review', ok: 16, dueSoon: 5, overdue: 3 },
];

/** Where calls are landing, standing in for the reference's map. */
export const SAMPLE_REGIONS = {
    rows: [
        { region: 'United Arab Emirates', calls: 8_420, pct: 36 },
        { region: 'United Kingdom', calls: 5_260, pct: 22 },
        { region: 'United States', calls: 4_180, pct: 18 },
        { region: 'India', calls: 3_310, pct: 14 },
        { region: 'Singapore', calls: 2_250, pct: 10 },
    ],
    numbers: 12,
    carriers: 4,
};

/** Severity-tagged alert list. */
