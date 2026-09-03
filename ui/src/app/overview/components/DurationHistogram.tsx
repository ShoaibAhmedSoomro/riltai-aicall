'use client';

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import type { DurationBucket } from '../useDashboardData';

/** The API's six fixed buckets, in seconds, rendered as readable ranges. */
const BUCKET_LABELS: Record<string, string> = {
    '0-10': '0–10s',
    '10-30': '10–30s',
    '30-60': '30–60s',
    '60-120': '1–2m',
    '120-180': '2–3m',
    '>180': '3m+',
};

/**
 * How long today's calls ran.
 *
 * The buckets are fixed server-side (api/services/reports/daily_report.py), so
 * this chart cannot be re-bucketed from the client. Only runs that recorded a
 * duration are counted, which is why the totals here can be lower than the
 * call count: percentages are over calls WITH a duration, not all calls.
 */
export function DurationHistogram({ data }: { data: DurationBucket[] }) {
    const rows = data.map((d) => ({ ...d, label: BUCKET_LABELS[d.bucket] ?? d.bucket }));

    return (
        <ResponsiveContainer width="100%" height={220}>
            <BarChart data={rows} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    stroke="var(--border)"
                    tickLine={false}
                />
                <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    stroke="var(--border)"
                    tickLine={false}
                    axisLine={false}
                />
                <Tooltip
                    cursor={{ fill: 'var(--accent)' }}
                    content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const row = payload[0].payload as (typeof rows)[number];
                        return (
                            <div className="rounded-lg border border-border bg-popover px-3 py-2 text-popover-foreground shadow-md">
                                <p className="text-sm font-medium">{row.label}</p>
                                <p className="text-xs text-muted-foreground">
                                    {row.count.toLocaleString()} {row.count === 1 ? 'call' : 'calls'} · {row.percentage}%
                                </p>
                            </div>
                        );
                    }}
                />
                <Bar dataKey="count" fill="var(--chart-3)" radius={[4, 4, 0, 0]} maxBarSize={44} />
            </BarChart>
        </ResponsiveContainer>
    );
}
