/**
 * Illustrative figures for the dashboard panels that have no data source.
 *
 * READ THIS BEFORE USING ANY VALUE HERE.
 *
 * Nothing in this file is real. It exists because several panels on the
 * reference dashboard this layout follows describe things the platform does not
 * measure, and the alternative to sample numbers was leaving those slots empty:
 *
 *   revenue, cost, margin      organizations.price_per_second_usd is a nullable
 *                              column no application code ever writes, so every
 *                              money field the API can return is absent and
 *                              /usage/daily-breakdown answers 400 always
 *   answer rate, conversion    the daily report exposes only total_runs and
 *                              xfer_count; there is no answered/connected count
 *   live concurrency           /health/active-calls is gated on a devops header
 *   period-over-period deltas  there is no previous-period endpoint anywhere
 *   contact and agent health   no such domain objects exist
 *   geography                  nothing stores a region for a call
 *
 * Every panel fed from here renders a "Sample" badge, and the dashboard shows
 * one banner saying so. Real and sample numbers are never mixed inside a single
 * panel: a tile that shows a real count shows no invented delta or sparkline
 * beside it.
 *
 * When a real source appears, delete the corresponding export and the panel's
 * `sample` prop. `SAMPLE_PANEL_IDS` lists what is still illustrative, so the
 * banner and the count in it cannot fall out of step with reality.
 */

export const SAMPLE_PANEL_IDS = [
    'revenue',
    'cost-vs-margin',
    'answer-rate',
    'performance',
    'pipeline',
    'conversion',
    'agent-health',
    'contacts',
    'compliance',
    'unit-economics',
    'regions',
    'alerts',
] as const;

export type SamplePanelId = (typeof SAMPLE_PANEL_IDS)[number];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];

/** Monthly revenue with a projection footer. */
export const SAMPLE_REVENUE = {
    total: 187_400,
    currency: 'USD',
    deltaPct: 8.6,
    ytd: 984_200,
    projected: 2_246_000,
    projectedDeltaPct: 9.3,
    series: MONTHS.map((month, i) => ({
        month,
        revenue: [96_000, 118_000, 132_000, 151_000, 168_000, 187_400][i],
    })),
};

/** Platform cost against gross margin, the two-series bar panel. */
export const SAMPLE_COST_VS_MARGIN = {
    series: MONTHS.map((month, i) => ({
        month,
        margin: [58_000, 71_000, 79_000, 94_000, 104_000, 116_000][i],
        cost: [38_000, 47_000, 53_000, 57_000, 64_000, 71_400][i],
    })),
    ytdMargin: 522_000,
    ytdMarginDeltaPct: 12.4,
    ytdCost: 462_200,
    ytdCostDeltaPct: 8.7,
};

/** The radial gauge and its legend. */
export const SAMPLE_ANSWER_RATE = {
    ratePct: 92.4,
    answered: 1_152,
    unanswered: 96,
    voicemail: 87,
    trendPct: 2.7,
    trend: [88, 89, 90, 89, 91, 92, 92.4],
};

/** Three-series performance line chart. */
export const SAMPLE_PERFORMANCE = {
    series: [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ].map((month, i) => ({
        month,
        calls: [1200, 1450, 1610, 1520, 1780, 1910, 2050, 1980, 2140, 2260, 2180, 2340][i],
        qualified: [420, 510, 590, 560, 660, 720, 780, 750, 820, 880, 840, 910][i],
        transferred: [180, 210, 240, 230, 280, 300, 330, 320, 350, 380, 360, 400][i],
    })),
    totalCalls: 23_420,
    qualifiedRate: 38.9,
    transferRate: 16.2,
};

/** Campaign pipeline donut. */
export const SAMPLE_PIPELINE = {
    total: 312,
    segments: [
        { label: 'Queued', count: 148, pct: 48, tone: 'neutral' as const },
        { label: 'In progress', count: 68, pct: 22, tone: 'positive' as const },
        { label: 'Retrying', count: 54, pct: 17, tone: 'neutral' as const },
        { label: 'Exhausted', count: 42, pct: 13, tone: 'negative' as const },
    ],
    dueToday: 42,
    atRisk: 12,
};

/** Conversion donut with the three stat columns beside it. */
export const SAMPLE_CONVERSION = {
    ratePct: 92.3,
    reached: 17_200,
    pending: 1_500,
    failed: 2_100,
    ytdRatePct: 94.1,
    ytdDeltaPct: 3.2,
    noContact: 23,
    noContactDeltaPct: 4,
};

/** Four-stat operational panels. */
export const SAMPLE_AGENT_HEALTH = {
    stats: [
        { label: 'Open issues', value: '128' },
        { label: 'In review', value: '76' },
        { label: 'Resolved (MTD)', value: '142' },
        { label: 'Overdue', value: '18' },
    ],
    footer: [
        { label: 'Cost (MTD)', value: '$620K' },
        { label: 'Planned work', value: '$1.2M' },
        { label: 'Avg resolution', value: '3.6 days' },
        { label: 'Satisfaction', value: '92%' },
    ],
};

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

/** Label, value and a sparkline per row. */
export const SAMPLE_UNIT_ECONOMICS = [
    { label: 'Cost per call', value: '$0.42', trend: [52, 49, 47, 45, 44, 43, 42], good: true },
    { label: 'Cost per qualified lead', value: '$11.20', trend: [14, 13.4, 12.8, 12.1, 11.8, 11.4, 11.2], good: true },
    { label: 'Avg handle time', value: '2m 18s', trend: [155, 150, 146, 142, 140, 139, 138], good: true },
    { label: 'Gross margin', value: '36.4%', trend: [29, 30, 32, 33, 34, 36, 36.4], good: true },
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
export const SAMPLE_ALERTS = [
    { severity: 'high' as const, text: 'Campaign "Q3 Renewals" retry budget nearly exhausted', meta: '7 lists', when: '10m ago' },
    { severity: 'high' as const, text: 'Carrier rejected 3 caller IDs on outbound trunk', meta: '3 numbers', when: '38m ago' },
    { severity: 'medium' as const, text: 'Answer rate down 6% versus the trailing week', meta: '2 agents', when: '1h ago' },
    { severity: 'medium' as const, text: 'Average handle time above target on "Support Triage"', meta: '1 agent', when: '3h ago' },
    { severity: 'low' as const, text: 'Recording retention window expires in 15 days', meta: '128 files', when: '5h ago' },
];
