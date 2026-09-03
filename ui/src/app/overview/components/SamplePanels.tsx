'use client';

import { ArrowDownRight, ArrowUpRight, CheckCircle2, Clock, Users, Wrench } from 'lucide-react';
import {
    Area,
    AreaChart,
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    Line,
    LineChart,
    Pie,
    PieChart,
    RadialBar,
    RadialBarChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';

import { cn } from '@/lib/utils';

import {
    SAMPLE_AGENT_HEALTH,
    SAMPLE_ALERTS,
    SAMPLE_ANSWER_RATE,
    SAMPLE_COMPLIANCE,
    SAMPLE_CONTACTS,
    SAMPLE_CONVERSION,
    SAMPLE_COST_VS_MARGIN,
    SAMPLE_PERFORMANCE,
    SAMPLE_PIPELINE,
    SAMPLE_REGIONS,
    SAMPLE_REVENUE,
    SAMPLE_UNIT_ECONOMICS,
} from '../sampleData';
import { Panel } from './Panel';

/**
 * The panels with no data source behind them, drawn from sampleData.ts.
 *
 * Every one passes `sample` to Panel, which renders the Sample badge. They are
 * grouped in a single file so the illustrative surface is one import and one
 * deletion when real sources arrive, rather than something to hunt for.
 *
 * These are the only place on the dashboard where a delta or a sparkline
 * appears, because a delta needs a previous period and no endpoint returns one.
 * Real panels show measured values with no invented movement beside them.
 */

const money = (n: number, currency = 'USD') =>
    new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
        notation: n >= 100_000 ? 'compact' : 'standard',
        maximumFractionDigits: n >= 100_000 ? 1 : 0,
    }).format(n);

/** Green up / red down, matching the sign convention of the reference design. */
function Delta({ pct, invert = false }: { pct: number; invert?: boolean }) {
    const good = invert ? pct < 0 : pct > 0;
    const Icon = pct >= 0 ? ArrowUpRight : ArrowDownRight;
    return (
        <span
            className={cn(
                'inline-flex items-center gap-0.5 text-xs font-medium tabular-nums',
                good ? 'text-[var(--chart-2)]' : 'text-destructive',
            )}
        >
            <Icon className="size-3" aria-hidden />
            {Math.abs(pct)}%
        </span>
    );
}

function FooterStat({
    label,
    value,
    delta,
    invert = false,
}: {
    label: string;
    value: string;
    delta?: number;
    /** For cost-shaped metrics, where a fall is the good direction. */
    invert?: boolean;
}) {
    return (
        <div className="min-w-0 rounded-lg bg-muted/50 px-3 py-2">
            <p className="truncate text-[11px] text-muted-foreground">{label}</p>
            <div className="mt-0.5 flex items-baseline gap-2">
                <span className="truncate text-sm font-semibold tabular-nums">{value}</span>
                {delta !== undefined && <Delta pct={delta} invert={invert} />}
            </div>
        </div>
    );
}

/** Tiny inline sparkline; sample-only, so no real number sits beside one. */
function Spark({ points, tone = 'var(--chart-1)' }: { points: number[]; tone?: string }) {
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

// ─────────────────────────────────────────────────────────────────────────────

export function RevenuePanel() {
    const d = SAMPLE_REVENUE;
    return (
        <Panel title="Revenue" subtitle="This month" sample action={{ label: 'Billing', href: '/billing' }}>
            <div className="flex items-baseline gap-2">
                <span className="text-2xl font-semibold tabular-nums">{money(d.total, d.currency)}</span>
                <Delta pct={d.deltaPct} />
            </div>
            <div className="mt-3 h-[132px]">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={d.series} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                        <defs>
                            <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                                <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                        <XAxis dataKey="month" {...axis} />
                        <YAxis {...axis} axisLine={false} tickFormatter={(v) => `${v / 1000}k`} />
                        <Tooltip {...chartTooltip} formatter={(v: number) => money(v, d.currency)} />
                        <Area
                            type="monotone"
                            dataKey="revenue"
                            stroke="var(--chart-1)"
                            strokeWidth={2}
                            fill="url(#rev)"
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
                <FooterStat label="Year to date" value={money(d.ytd, d.currency)} />
                <FooterStat label="Projected (year)" value={money(d.projected, d.currency)} delta={d.projectedDeltaPct} />
            </div>
        </Panel>
    );
}

export function CostVsMarginPanel() {
    const d = SAMPLE_COST_VS_MARGIN;
    return (
        <Panel title="Margin vs cost" subtitle="This month" sample>
            <div className="flex items-center gap-4 text-xs">
                <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden className="size-2.5 rounded-sm bg-[var(--chart-2)]" /> Margin
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden className="size-2.5 rounded-sm bg-[var(--chart-5)]" /> Cost
                </span>
            </div>
            <div className="mt-2 h-[142px]">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.series} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                        <XAxis dataKey="month" {...axis} />
                        <YAxis {...axis} axisLine={false} tickFormatter={(v) => `${v / 1000}k`} />
                        <Tooltip {...chartTooltip} formatter={(v: number) => money(v)} />
                        <Bar dataKey="margin" fill="var(--chart-2)" radius={[3, 3, 0, 0]} maxBarSize={14} />
                        <Bar dataKey="cost" fill="var(--chart-5)" radius={[3, 3, 0, 0]} maxBarSize={14} />
                    </BarChart>
                </ResponsiveContainer>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
                <FooterStat label="YTD margin" value={money(d.ytdMargin)} delta={d.ytdMarginDeltaPct} />
                <FooterStat label="YTD cost" value={money(d.ytdCost)} delta={d.ytdCostDeltaPct} invert />
            </div>
        </Panel>
    );
}

export function AnswerRatePanel() {
    const d = SAMPLE_ANSWER_RATE;
    const gauge = [{ name: 'answered', value: d.ratePct, fill: 'var(--chart-2)' }];
    return (
        <Panel title="Answer rate" sample action={{ label: 'Reports', href: '/reports' }}>
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
                            <RadialBar dataKey="value" background={{ fill: 'var(--muted)' }} cornerRadius={8} />
                        </RadialBarChart>
                    </ResponsiveContainer>
                    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-2xl font-semibold tabular-nums">{d.ratePct}%</span>
                        <span className="text-[11px] text-muted-foreground">answered</span>
                    </div>
                </div>
                <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
                    {[
                        { label: 'Answered', value: d.answered, color: 'var(--chart-2)' },
                        { label: 'No answer', value: d.unanswered, color: 'var(--chart-1)' },
                        { label: 'Voicemail', value: d.voicemail, color: 'var(--chart-4)' },
                    ].map((row) => (
                        <li key={row.label} className="flex items-center gap-2">
                            <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ background: row.color }} />
                            <span className="min-w-0 flex-1 truncate">{row.label}</span>
                            <span className="tabular-nums font-medium">{row.value.toLocaleString()}</span>
                        </li>
                    ))}
                </ul>
            </div>
            <div className="mt-3 flex items-center justify-between rounded-lg bg-muted/50 px-3 py-2">
                <span className="text-[11px] text-muted-foreground">Trend</span>
                <div className="mx-3 w-28"><Spark points={d.trend} tone="var(--chart-2)" /></div>
                <Delta pct={d.trendPct} />
            </div>
        </Panel>
    );
}

export function PerformancePanel() {
    const d = SAMPLE_PERFORMANCE;
    return (
        <Panel title="Performance" subtitle="This year" sample>
            <div className="flex flex-wrap items-center gap-4 text-xs">
                {[
                    { k: 'calls', label: 'Calls', c: 'var(--chart-1)' },
                    { k: 'qualified', label: 'Qualified', c: 'var(--chart-2)' },
                    { k: 'transferred', label: 'Transferred', c: 'var(--chart-4)' },
                ].map((s) => (
                    <span key={s.k} className="inline-flex items-center gap-1.5">
                        <span aria-hidden className="size-2.5 rounded-sm" style={{ background: s.c }} /> {s.label}
                    </span>
                ))}
            </div>
            <div className="mt-2 h-[160px]">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={d.series} margin={{ top: 4, right: 6, left: -22, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                        <XAxis dataKey="month" {...axis} interval={1} />
                        <YAxis {...axis} axisLine={false} />
                        <Tooltip {...chartTooltip} />
                        <Line type="monotone" dataKey="calls" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="qualified" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="transferred" stroke="var(--chart-4)" strokeWidth={2} dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
                <FooterStat label="Total calls" value={d.totalCalls.toLocaleString()} />
                <FooterStat label="Qualified rate" value={`${d.qualifiedRate}%`} />
                <FooterStat label="Transfer rate" value={`${d.transferRate}%`} />
            </div>
        </Panel>
    );
}

const TONE_COLOR = {
    positive: 'var(--chart-2)',
    neutral: 'var(--chart-1)',
    negative: 'var(--destructive)',
} as const;

export function PipelinePanel() {
    const d = SAMPLE_PIPELINE;
    return (
        <Panel title="Campaign pipeline" sample action={{ label: 'Campaigns', href: '/campaigns' }}>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <div className="relative mx-auto size-[150px] shrink-0">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={d.segments}
                                dataKey="count"
                                nameKey="label"
                                innerRadius={48}
                                outerRadius={73}
                                paddingAngle={2}
                                strokeWidth={0}
                            >
                                {d.segments.map((s) => (
                                    <Cell key={s.label} fill={TONE_COLOR[s.tone]} />
                                ))}
                            </Pie>
                            <Tooltip {...chartTooltip} />
                        </PieChart>
                    </ResponsiveContainer>
                    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-xl font-semibold tabular-nums">{d.total}</span>
                        <span className="text-[11px] text-muted-foreground">in flight</span>
                    </div>
                </div>
                <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
                    {d.segments.map((s) => (
                        <li key={s.label} className="flex items-center gap-2">
                            <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ background: TONE_COLOR[s.tone] }} />
                            <span className="min-w-0 flex-1 truncate">{s.label}</span>
                            <span className="tabular-nums font-medium">{s.count}</span>
                            <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">{s.pct}%</span>
                        </li>
                    ))}
                </ul>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
                <FooterStat label="Due today" value={`${d.dueToday} lists`} />
                <FooterStat label="At risk" value={`${d.atRisk} lists`} />
            </div>
        </Panel>
    );
}

export function ConversionPanel() {
    const d = SAMPLE_CONVERSION;
    const segments = [
        { label: 'Reached', value: d.reached, color: 'var(--chart-2)' },
        { label: 'Pending', value: d.pending, color: 'var(--chart-1)' },
        { label: 'Failed', value: d.failed, color: 'var(--destructive)' },
    ];
    return (
        <Panel title="Contact rate" sample action={{ label: 'Agent runs', href: '/usage' }}>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <div className="relative mx-auto size-[132px] shrink-0">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie data={segments} dataKey="value" nameKey="label" innerRadius={42} outerRadius={64} paddingAngle={2} strokeWidth={0}>
                                {segments.map((s) => (
                                    <Cell key={s.label} fill={s.color} />
                                ))}
                            </Pie>
                            <Tooltip {...chartTooltip} />
                        </PieChart>
                    </ResponsiveContainer>
                    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-lg font-semibold tabular-nums">{d.ratePct}%</span>
                        <span className="text-[10px] text-muted-foreground">reached</span>
                    </div>
                </div>
                <div className="grid min-w-0 flex-1 grid-cols-3 gap-2">
                    {segments.map((s) => (
                        <div key={s.label} className="min-w-0">
                            <p className="truncate text-[11px] text-muted-foreground">{s.label}</p>
                            <p className="truncate text-sm font-semibold tabular-nums" style={{ color: s.color }}>
                                {s.value.toLocaleString()}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
                <FooterStat label="YTD contact rate" value={`${d.ytdRatePct}%`} delta={d.ytdDeltaPct} />
                <FooterStat label="Never reached" value={`${d.noContact} lists`} delta={d.noContactDeltaPct} invert />
            </div>
        </Panel>
    );
}

function FourStatPanel({
    title,
    icon: Icon,
    data,
    href,
}: {
    title: string;
    icon: typeof Wrench;
    data: { stats: { label: string; value: string }[]; footer: { label: string; value: string }[] };
    href?: string;
}) {
    return (
        <Panel title={title} sample action={href ? { label: 'Open', href } : undefined}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {data.stats.map((s) => (
                    <div key={s.label} className="min-w-0">
                        <span className="mb-1 flex size-7 items-center justify-center rounded-md bg-muted">
                            <Icon className="size-3.5 text-muted-foreground" aria-hidden />
                        </span>
                        <p className="truncate text-[11px] text-muted-foreground">{s.label}</p>
                        <p className="text-base font-semibold tabular-nums">{s.value}</p>
                    </div>
                ))}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {data.footer.map((s) => (
                    <FooterStat key={s.label} label={s.label} value={s.value} />
                ))}
            </div>
        </Panel>
    );
}

export function AgentHealthPanel() {
    return <FourStatPanel title="Agent health" icon={Wrench} data={SAMPLE_AGENT_HEALTH} href="/workflow" />;
}

export function ContactsPanel() {
    return <FourStatPanel title="Contacts" icon={Users} data={SAMPLE_CONTACTS} href="/campaigns" />;
}

export function CompliancePanel() {
    return (
        <Panel title="Risk & compliance" sample bodyClassName="p-0">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-border/60 text-[11px] uppercase tracking-wide text-muted-foreground">
                        <th className="px-4 py-2 text-left font-medium">Item</th>
                        <th className="px-2 py-2 text-right font-medium">OK</th>
                        <th className="px-2 py-2 text-right font-medium">Due soon</th>
                        <th className="px-4 py-2 text-right font-medium">Overdue</th>
                    </tr>
                </thead>
                <tbody>
                    {SAMPLE_COMPLIANCE.map((row) => (
                        <tr key={row.item} className="border-b border-border/40 last:border-0">
                            <td className="truncate px-4 py-2">{row.item}</td>
                            <td className="px-2 py-2 text-right tabular-nums">
                                <span className="rounded bg-[var(--chart-2)]/15 px-1.5 py-0.5 text-[var(--chart-2)]">{row.ok}</span>
                            </td>
                            <td className="px-2 py-2 text-right tabular-nums">
                                <span className="rounded bg-[var(--chart-4)]/15 px-1.5 py-0.5 text-[var(--chart-4)]">{row.dueSoon}</span>
                            </td>
                            <td className="px-4 py-2 text-right tabular-nums">
                                <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-destructive">{row.overdue}</span>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </Panel>
    );
}

export function UnitEconomicsPanel() {
    return (
        <Panel title="Unit economics" sample bodyClassName="p-0">
            <ul className="divide-y divide-border/60">
                {SAMPLE_UNIT_ECONOMICS.map((row) => (
                    <li key={row.label} className="flex items-center gap-3 px-4 py-2.5">
                        <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs text-muted-foreground">{row.label}</span>
                            <span className="block text-sm font-semibold tabular-nums">{row.value}</span>
                        </span>
                        <span className="w-24 shrink-0">
                            <Spark points={row.trend} tone={row.good ? 'var(--chart-2)' : 'var(--destructive)'} />
                        </span>
                    </li>
                ))}
            </ul>
        </Panel>
    );
}

export function RegionsPanel() {
    const d = SAMPLE_REGIONS;
    return (
        <Panel
            title="Where calls land"
            subtitle={`${d.numbers} numbers across ${d.carriers} carriers`}
            sample
            action={{ label: 'Telephony', href: '/telephony-configurations' }}
        >
            <ul className="space-y-3">
                {d.rows.map((row) => (
                    <li key={row.region}>
                        <div className="flex items-baseline justify-between gap-3">
                            <span className="min-w-0 truncate text-sm">{row.region}</span>
                            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                                {row.calls.toLocaleString()} · {row.pct}%
                            </span>
                        </div>
                        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full bg-[var(--chart-3)]" style={{ width: `${row.pct * 2.7}%` }} />
                        </div>
                    </li>
                ))}
            </ul>
        </Panel>
    );
}

const SEVERITY = {
    high: { label: 'High', className: 'bg-destructive/15 text-destructive' },
    medium: { label: 'Medium', className: 'bg-[var(--chart-4)]/15 text-[var(--chart-4)]' },
    low: { label: 'Low', className: 'bg-muted text-muted-foreground' },
} as const;

export function AlertsPanel() {
    return (
        <Panel title="Alerts" sample bodyClassName="p-0">
            <ul className="divide-y divide-border/60">
                {SAMPLE_ALERTS.map((alert) => (
                    <li key={alert.text} className="flex items-start gap-3 px-4 py-2.5">
                        <span
                            className={cn(
                                'mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase',
                                SEVERITY[alert.severity].className,
                            )}
                        >
                            {SEVERITY[alert.severity].label}
                        </span>
                        <span className="min-w-0 flex-1">
                            <span className="block text-sm">{alert.text}</span>
                            <span className="block text-xs text-muted-foreground">
                                {alert.meta} · {alert.when}
                            </span>
                        </span>
                    </li>
                ))}
            </ul>
        </Panel>
    );
}

/** The two extra KPI tiles that only sample data can fill. */
export function SampleKpiTiles() {
    const tiles = [
        {
            label: 'Revenue (MTD)',
            value: money(SAMPLE_REVENUE.total, SAMPLE_REVENUE.currency),
            delta: SAMPLE_REVENUE.deltaPct,
            icon: CheckCircle2,
            spark: SAMPLE_REVENUE.series.map((s) => s.revenue),
        },
        {
            label: 'Answer rate',
            value: `${SAMPLE_ANSWER_RATE.ratePct}%`,
            delta: SAMPLE_ANSWER_RATE.trendPct,
            icon: Clock,
            spark: SAMPLE_ANSWER_RATE.trend,
        },
    ];
    return (
        <>
            {tiles.map((t) => (
                <div key={t.label} className="rounded-xl border border-border/60 bg-card p-4">
                    <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium text-muted-foreground">{t.label}</span>
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[var(--chart-4)]/40 bg-[var(--chart-4)]/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--chart-4)]">
                            Sample
                        </span>
                    </div>
                    <div className="mt-3 flex items-baseline gap-2">
                        <span className="text-2xl font-semibold tabular-nums tracking-tight">{t.value}</span>
                        <Delta pct={t.delta} />
                    </div>
                    <div className="mt-1"><Spark points={t.spark} /></div>
                </div>
            ))}
        </>
    );
}
