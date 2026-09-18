'use client';

import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import {
    Area,
    AreaChart,
    CartesianGrid,
    Cell,
    Line,
    LineChart,
    Pie,
    PieChart,
    PolarAngleAxis,
    RadialBar,
    RadialBarChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';

import type {
    AlertItem,
    QueueSummaryResponse,
    UsageSeriesResponse,
    UsageSummaryResponse,
} from '@/client/types.gen';
import { cn } from '@/lib/utils';

import { Panel } from './Panel';

/**
 * The panels that replaced sample ones, each fed from a real endpoint.
 *
 * These live apart from SamplePanels.tsx deliberately: sampleData.test.tsx
 * counts the capitalized exports of THAT file against SAMPLE_PANEL_IDS, so a
 * real panel left in there would be counted as illustrative.
 *
 * The rule every panel here follows: nullable means unknown, and unknown is
 * never drawn as zero. `total_charge_usd` is null when nothing was priced,
 * `answer_rate_pct` is null when there were no calls to answer. Each of those
 * gets a sentence saying what would fill it -- Panel's `empty` prop -- rather
 * than a $0.00 or a 0% that reads as measured.
 *
 * A delta is only shown against `summary.previous`, an equal-length window
 * immediately before the current one that arrives from the same query. No
 * delta is computed from anything else, because two windows assembled
 * separately can disagree.
 */

const WINDOW = 'Last 30 days';

const usdFmt = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    // At a per-minute rate a short call rounds to $0.00 at two decimals.
    maximumFractionDigits: 4,
});
const money = (n: number) => usdFmt.format(n);

const int = (n: number) => n.toLocaleString();

/** Percent change, or null when the baseline is zero or unknown. */
function delta(now: number | null | undefined, before: number | null | undefined) {
    if (now == null || before == null || before === 0) return null;
    return Math.round(((now - before) / before) * 100);
}

function Delta({ pct, invert = false }: { pct: number; invert?: boolean }) {
    const good = invert ? pct < 0 : pct > 0;
    const Icon = pct >= 0 ? ArrowUpRight : ArrowDownRight;
    return (
        <span
            className={cn(
                'inline-flex items-center gap-0.5 text-xs font-medium tabular-nums',
                pct === 0 ? 'text-muted-foreground' : good ? 'text-[var(--chart-2)]' : 'text-destructive',
            )}
            title="vs the equal-length window before this one"
        >
            <Icon className="size-3" aria-hidden />
            {Math.abs(pct)}%
        </span>
    );
}

function FooterStat({
    label,
    value,
    pct,
    invert = false,
}: {
    label: string;
    value: string;
    pct?: number | null;
    invert?: boolean;
}) {
    return (
        <div className="min-w-0 rounded-lg bg-muted/50 px-3 py-2">
            <p className="truncate text-[11px] text-muted-foreground">{label}</p>
            <div className="mt-0.5 flex items-baseline gap-2">
                <span className="truncate text-sm font-semibold tabular-nums">{value}</span>
                {pct != null && <Delta pct={pct} invert={invert} />}
            </div>
        </div>
    );
}

/** Tiny inline sparkline. Returns null rather than a flat line for <2 points. */
function Spark({ points, tone = 'var(--chart-1)' }: { points: number[]; tone?: string }) {
    if (points.length < 2) return null;
    const min = Math.min(...points);
    const max = Math.max(...points);
    const span = max - min || 1;
    const d = points
        .map((p, i) => `${(i / (points.length - 1)) * 100},${28 - ((p - min) / span) * 24}`)
        .join(' ');
    return (
        <svg viewBox="0 0 100 28" preserveAspectRatio="none" className="h-7 w-full" aria-hidden>
            <polyline points={d} fill="none" stroke={tone} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        </svg>
    );
}

const chartTooltip = {
    contentStyle: {
        background: 'var(--popover)',
        border: '1px solid var(--border)',
        borderRadius: '0.5rem',
        color: 'var(--popover-foreground)',
        fontSize: 12,
    },
    labelStyle: { color: 'var(--popover-foreground)', fontWeight: 600 },
};

const axis = {
    tick: { fontSize: 11, fill: 'var(--muted-foreground)' },
    stroke: 'var(--border)',
    tickLine: false,
};

/** YYYY-MM-DD (or a full timestamp) to a short axis label. */
const shortDay = (bucket: string | null | undefined) => String(bucket ?? '').slice(5, 10);

// ─────────────────────────────────────────────────────────────────────────────

export function SpendPanel({
    summary,
    series,
    loading,
}: {
    summary: UsageSummaryResponse | null;
    series: UsageSeriesResponse | null;
    loading: boolean;
}) {
    const spend = summary?.total_charge_usd ?? null;
    // Inside a window that HAS priced calls, a bucket with no charge is a day
    // with no priced calls, which is genuinely zero spend. Outside one, the
    // whole panel is empty instead -- see `empty` below.
    const points = (series?.points ?? []).map((p) => ({
        day: shortDay(p.bucket),
        spend: p.charge_usd ?? 0,
    }));

    return (
        <Panel
            title="Spend"
            subtitle={WINDOW}
            action={{ label: 'Usage', href: '/usage' }}
            loading={loading && summary === null}
            empty={
                !loading && summary === null
                    ? 'Spend could not be loaded.'
                    : summary && spend === null
                      ? 'No calls have been priced yet. Set a rate card on the Usage page and completed calls will start recording a cost.'
                      : undefined
            }
        >
            {summary && spend !== null && (
                <>
                    <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-semibold tabular-nums">{money(spend)}</span>
                        {(() => {
                            const pct = delta(spend, summary.previous.total_charge_usd);
                            return pct == null ? null : <Delta pct={pct} />;
                        })()}
                    </div>
                    <div className="mt-3 h-[132px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={points} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="realSpend" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                                        <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                                <XAxis dataKey="day" {...axis} minTickGap={24} />
                                <YAxis {...axis} axisLine={false} width={44} />
                                <Tooltip {...chartTooltip} formatter={(v: number) => money(v)} />
                                <Area
                                    type="monotone"
                                    dataKey="spend"
                                    name="Spend"
                                    stroke="var(--chart-1)"
                                    strokeWidth={2}
                                    fill="url(#realSpend)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                        <FooterStat
                            label="Cost per call"
                            value={summary.total_runs ? money(spend / summary.total_runs) : '—'}
                        />
                        <FooterStat
                            label="Calls"
                            value={int(summary.total_runs)}
                            pct={delta(summary.total_runs, summary.previous.total_runs)}
                        />
                    </div>
                </>
            )}
        </Panel>
    );
}

export function AnswerRatePanel({
    summary,
    series,
    loading,
}: {
    summary: UsageSummaryResponse | null;
    series: UsageSeriesResponse | null;
    loading: boolean;
}) {
    const rate = summary?.answer_rate_pct ?? null;
    const gauge = [{ name: 'answered', value: rate ?? 0, fill: 'var(--chart-2)' }];
    const trend = (series?.points ?? [])
        .map((p) => p.answer_rate_pct)
        .filter((v): v is number => v != null);

    return (
        <Panel
            title="Answer rate"
            subtitle={WINDOW}
            action={{ label: 'Reports', href: '/reports' }}
            loading={loading && summary === null}
            empty={
                !loading && summary === null
                    ? 'The answer rate could not be loaded.'
                    : summary && rate === null
                      ? 'No calls were placed in the last 30 days. A 0% answer rate would claim calls were placed and none connected.'
                      : undefined
            }
        >
            {summary && rate !== null && (
                <>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                        <div className="relative mx-auto size-[150px] shrink-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <RadialBarChart
                                    data={gauge}
                                    innerRadius="72%"
                                    outerRadius="100%"
                                    startAngle={210}
                                    endAngle={-30}
                                >
                                    {/* The axis is what fixes the scale. Without
                                        it recharts scales the single bar to its
                                        own value, so every rate from 1% to 100%
                                        draws as a full ring. */}
                                    <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                                    <RadialBar dataKey="value" background={{ fill: 'var(--muted)' }} cornerRadius={8} />
                                </RadialBarChart>
                            </ResponsiveContainer>
                            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                                <span className="text-2xl font-semibold tabular-nums">{rate}%</span>
                                <span className="text-[11px] text-muted-foreground">answered</span>
                            </div>
                        </div>
                        <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
                            {[
                                { label: 'Answered', value: summary.answered_runs, color: 'var(--chart-2)' },
                                { label: 'No answer', value: summary.unanswered_runs, color: 'var(--chart-1)' },
                            ].map((row) => (
                                <li key={row.label} className="flex items-center gap-2">
                                    <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ background: row.color }} />
                                    <span className="min-w-0 flex-1 truncate">{row.label}</span>
                                    <span className="tabular-nums font-medium">{int(row.value)}</span>
                                </li>
                            ))}
                            {/* Voicemail is NOT a third slice. A machine picking up
                                is a connection, so these runs are already inside
                                "answered"; listing them alongside would double-count
                                and make the three rows disagree with the ring. */}
                            <li className="flex items-center gap-2 pl-[18px] text-xs text-muted-foreground">
                                <span className="min-w-0 flex-1 truncate">of which voicemail</span>
                                <span className="tabular-nums">{int(summary.voicemail_runs)}</span>
                            </li>
                            <li className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
                                <span className="min-w-0 flex-1 truncate">
                                    Out of {int(summary.call_runs)} calls; text chats excluded
                                </span>
                            </li>
                        </ul>
                    </div>
                    <div className="mt-3 flex items-center justify-between rounded-lg bg-muted/50 px-3 py-2">
                        <span className="text-[11px] text-muted-foreground">Trend</span>
                        <div className="mx-3 w-28"><Spark points={trend} tone="var(--chart-2)" /></div>
                        {(() => {
                            const pct = delta(rate, summary.previous.answer_rate_pct);
                            return pct == null ? null : <Delta pct={pct} />;
                        })()}
                    </div>
                </>
            )}
        </Panel>
    );
}

export function PerformancePanel({
    summary,
    series,
    loading,
}: {
    summary: UsageSummaryResponse | null;
    series: UsageSeriesResponse | null;
    loading: boolean;
}) {
    const points = (series?.points ?? []).map((p) => ({
        day: shortDay(p.bucket),
        calls: p.calls,
        qualified: p.qualified_runs ?? 0,
        transferred: p.transferred_runs ?? 0,
    }));
    const rate = (n: number) =>
        summary && summary.total_runs ? `${Math.round((n / summary.total_runs) * 100)}%` : '—';

    return (
        <Panel
            title="Performance"
            subtitle={WINDOW}
            loading={loading && series === null}
            empty={
                !loading && series === null
                    ? 'Performance could not be loaded.'
                    : series && points.length === 0
                      ? 'No calls in the last 30 days.'
                      : undefined
            }
        >
            {points.length > 0 && (
                <>
                    <div className="flex flex-wrap items-center gap-4 text-xs">
                        {[
                            { label: 'Calls', c: 'var(--chart-1)' },
                            { label: 'Qualified', c: 'var(--chart-2)' },
                            { label: 'Transferred', c: 'var(--chart-4)' },
                        ].map((s) => (
                            <span key={s.label} className="inline-flex items-center gap-1.5">
                                <span aria-hidden className="size-2.5 rounded-sm" style={{ background: s.c }} /> {s.label}
                            </span>
                        ))}
                    </div>
                    <div className="mt-2 h-[160px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={points} margin={{ top: 4, right: 6, left: -22, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                                <XAxis dataKey="day" {...axis} minTickGap={24} />
                                <YAxis {...axis} axisLine={false} allowDecimals={false} />
                                <Tooltip {...chartTooltip} />
                                <Line type="monotone" dataKey="calls" name="Calls" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="qualified" name="Qualified" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="transferred" name="Transferred" stroke="var(--chart-4)" strokeWidth={2} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                    {summary && (
                        <div className="mt-3 grid grid-cols-3 gap-2">
                            <FooterStat
                                label="Total calls"
                                value={int(summary.total_runs)}
                                pct={delta(summary.total_runs, summary.previous.total_runs)}
                            />
                            <FooterStat label="Qualified rate" value={rate(summary.qualified_runs)} />
                            <FooterStat label="Transfer rate" value={rate(summary.transferred_runs)} />
                        </div>
                    )}
                </>
            )}
        </Panel>
    );
}

/**
 * The queued_run_state enum, in the order work moves through it.
 *
 * These four partition the queue. `retrying` and `scheduled` do NOT -- they are
 * views over `queued` -- so they sit in the footer rather than the ring, where
 * they would make the segments overcount.
 */
const QUEUE_SEGMENTS = [
    { key: 'queued', label: 'Queued', color: 'var(--chart-1)' },
    { key: 'processing', label: 'Processing', color: 'var(--chart-4)' },
    { key: 'processed', label: 'Processed', color: 'var(--chart-2)' },
    { key: 'failed', label: 'Failed', color: 'var(--destructive)' },
] as const;

export function PipelinePanel({
    queue,
    loading,
}: {
    queue: QueueSummaryResponse | null;
    loading: boolean;
}) {
    const segments = QUEUE_SEGMENTS.map((s) => ({ ...s, count: queue?.[s.key] ?? 0 })).filter(
        (s) => s.count > 0,
    );

    return (
        <Panel
            title="Campaign pipeline"
            subtitle={queue ? `${int(queue.campaigns)} ${queue.campaigns === 1 ? 'campaign' : 'campaigns'}` : undefined}
            action={{ label: 'Campaigns', href: '/campaigns' }}
            loading={loading && queue === null}
            empty={
                !loading && queue === null
                    ? 'The queue could not be loaded.'
                    : queue && queue.total === 0
                      ? 'No campaign work has been queued.'
                      : undefined
            }
        >
            {queue && queue.total > 0 && (
                <>
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                        <div className="relative mx-auto size-[150px] shrink-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={segments}
                                        dataKey="count"
                                        nameKey="label"
                                        innerRadius={48}
                                        outerRadius={73}
                                        paddingAngle={2}
                                        strokeWidth={0}
                                    >
                                        {segments.map((s) => (
                                            <Cell key={s.key} fill={s.color} />
                                        ))}
                                    </Pie>
                                    <Tooltip {...chartTooltip} />
                                </PieChart>
                            </ResponsiveContainer>
                            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                                <span className="text-xl font-semibold tabular-nums">{int(queue.total)}</span>
                                <span className="text-[11px] text-muted-foreground">rows</span>
                            </div>
                        </div>
                        <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
                            {QUEUE_SEGMENTS.map((s) => (
                                <li key={s.key} className="flex items-center gap-2">
                                    <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ background: s.color }} />
                                    <span className="min-w-0 flex-1 truncate">{s.label}</span>
                                    <span className="tabular-nums font-medium">{int(queue[s.key])}</span>
                                    <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
                                        {Math.round((queue[s.key] / queue.total) * 100)}%
                                    </span>
                                </li>
                            ))}
                        </ul>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                        <FooterStat label="Retrying (of queued)" value={int(queue.retrying)} />
                        <FooterStat label="Scheduled (of queued)" value={int(queue.scheduled)} />
                    </div>
                </>
            )}
        </Panel>
    );
}

export function ContactRatePanel({
    queue,
    loading,
}: {
    queue: QueueSummaryResponse | null;
    loading: boolean;
}) {
    const segments = [
        { label: 'Reached', value: queue?.processed ?? 0, color: 'var(--chart-2)' },
        { label: 'Pending', value: queue?.queued ?? 0, color: 'var(--chart-1)' },
        { label: 'Failed', value: queue?.failed ?? 0, color: 'var(--destructive)' },
    ];
    const ratePct = queue && queue.total ? Math.round((queue.processed / queue.total) * 100) : null;

    return (
        <Panel
            title="Contact rate"
            // There is no contact entity in this system. This counts rows in
            // campaign audiences, and saying so is the difference between a
            // real figure and one that looks like a per-person rate.
            subtitle="Campaign audience rows"
            action={{ label: 'Campaigns', href: '/campaigns' }}
            loading={loading && queue === null}
            empty={
                !loading && queue === null
                    ? 'The contact rate could not be loaded.'
                    : queue && queue.total === 0
                      ? 'No campaign audiences have been loaded.'
                      : undefined
            }
        >
            {queue && ratePct !== null && (
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                    <div className="relative mx-auto size-[132px] shrink-0">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={segments.filter((s) => s.value > 0)}
                                    dataKey="value"
                                    nameKey="label"
                                    innerRadius={42}
                                    outerRadius={64}
                                    paddingAngle={2}
                                    strokeWidth={0}
                                >
                                    {segments
                                        .filter((s) => s.value > 0)
                                        .map((s) => (
                                            <Cell key={s.label} fill={s.color} />
                                        ))}
                                </Pie>
                                <Tooltip {...chartTooltip} />
                            </PieChart>
                        </ResponsiveContainer>
                        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                            <span className="text-lg font-semibold tabular-nums">{ratePct}%</span>
                            <span className="text-[10px] text-muted-foreground">reached</span>
                        </div>
                    </div>
                    <div className="grid min-w-0 flex-1 grid-cols-3 gap-2">
                        {segments.map((s) => (
                            <div key={s.label} className="min-w-0">
                                <p className="truncate text-[11px] text-muted-foreground">{s.label}</p>
                                <p className="truncate text-sm font-semibold tabular-nums" style={{ color: s.color }}>
                                    {int(s.value)}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </Panel>
    );
}

/** mm:ss for a duration in seconds. */
function handleTime(seconds: number) {
    const whole = Math.round(seconds);
    return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, '0')}s`;
}

export function UnitEconomicsPanel({
    summary,
    series,
    loading,
}: {
    summary: UsageSummaryResponse | null;
    series: UsageSeriesResponse | null;
    loading: boolean;
}) {
    // The last week of buckets, so a sparkline is a week rather than a month
    // compressed into 100px.
    const recent = (series?.points ?? []).slice(-7);
    const spend = summary?.total_charge_usd ?? null;

    // Gross margin is deliberately absent, here and everywhere: AICall never
    // learns what an operator bills their own end-customer, so margin is
    // unknowable in principle rather than merely unmeasured.
    const rows =
        summary === null
            ? []
            : [
                  {
                      label: 'Cost per call',
                      value: spend !== null && summary.total_runs ? money(spend / summary.total_runs) : null,
                      trend: recent.map((p) => (p.calls ? (p.charge_usd ?? 0) / p.calls : 0)),
                      // Cheaper is better.
                      good: true,
                  },
                  {
                      label: 'Cost per qualified lead',
                      value:
                          spend !== null && summary.qualified_runs
                              ? money(spend / summary.qualified_runs)
                              : null,
                      trend: recent.map((p) =>
                          p.qualified_runs ? (p.charge_usd ?? 0) / p.qualified_runs : 0,
                      ),
                      good: true,
                  },
                  {
                      label: 'Average handle time',
                      value:
                          summary.avg_duration_seconds != null
                              ? handleTime(summary.avg_duration_seconds)
                              : null,
                      trend: recent.map((p) => (p.calls ? p.duration_seconds / p.calls : 0)),
                      good: true,
                  },
              ];

    return (
        <Panel
            title="Unit economics"
            subtitle={WINDOW}
            bodyClassName="p-0"
            loading={loading && summary === null}
            empty={
                !loading && summary === null ? 'Unit economics could not be loaded.' : undefined
            }
        >
            <ul className="divide-y divide-border/60">
                {rows.map((row) => (
                    <li key={row.label} className="flex items-center gap-3 px-4 py-2.5">
                        <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs text-muted-foreground">{row.label}</span>
                            {row.value === null ? (
                                <span className="block text-sm text-muted-foreground">
                                    {row.label.startsWith('Cost')
                                        ? 'Needs a rate card and a priced call'
                                        : 'No calls yet'}
                                </span>
                            ) : (
                                <span className="block text-sm font-semibold tabular-nums">{row.value}</span>
                            )}
                        </span>
                        {row.value !== null && (
                            <span className="w-24 shrink-0">
                                <Spark points={row.trend} tone={row.good ? 'var(--chart-2)' : 'var(--destructive)'} />
                            </span>
                        )}
                    </li>
                ))}
            </ul>
        </Panel>
    );
}

/**
 * Severity as the alerts endpoint emits it. Anything unrecognised falls back to
 * the neutral style rather than crashing the panel on a value added later.
 */
const SEVERITY: Record<string, { label: string; className: string }> = {
    error: { label: 'Error', className: 'bg-destructive/15 text-destructive' },
    warning: { label: 'Warning', className: 'bg-[var(--chart-4)]/15 text-[var(--chart-4)]' },
};
const NEUTRAL_SEVERITY = { label: 'Info', className: 'bg-muted text-muted-foreground' };

export function AlertsPanel({ alerts, loading }: { alerts: AlertItem[] | null; loading: boolean }) {
    return (
        <Panel
            title="Alerts"
            bodyClassName="p-0"
            loading={loading && alerts === null}
            empty={
                !loading && alerts === null
                    ? 'Alerts could not be loaded.'
                    : // An empty list is a real answer, and a different one from
                      // a failed fetch. The panel this replaced could say neither.
                      alerts && alerts.length === 0
                      ? 'Nothing needs attention.'
                      : undefined
            }
        >
            <ul className="divide-y divide-border/60">
                {(alerts ?? []).map((alert, i) => {
                    const severity = SEVERITY[alert.severity] ?? NEUTRAL_SEVERITY;
                    return (
                        <li key={`${alert.href}-${i}`}>
                            <Link
                                href={alert.href}
                                className="flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-accent/40"
                            >
                                <span
                                    className={cn(
                                        'mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase',
                                        severity.className,
                                    )}
                                >
                                    {severity.label}
                                </span>
                                <span className="min-w-0 flex-1">
                                    <span className="block text-sm">{alert.text}</span>
                                    {alert.occurred_at && (
                                        <span className="block text-xs text-muted-foreground">
                                            {new Date(alert.occurred_at).toLocaleString()}
                                        </span>
                                    )}
                                </span>
                            </Link>
                        </li>
                    );
                })}
            </ul>
        </Panel>
    );
}
