'use client';

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import type { DayVolume } from '../useDashboardData';

/**
 * Calls per day over the trend window.
 *
 * Each bar is a server-side COUNT over that day's range, not a client-side tally
 * of fetched rows, so the figure is exact even when a day has more runs than any
 * page could return.
 */
export function CallVolumeChart({ data, timezone }: { data: DayVolume[]; timezone: string }) {
    const rows = data.map((d) => ({
        ...d,
        // "Mon 3" — the axis needs to stay legible at seven ticks.
        label: new Intl.DateTimeFormat(undefined, {
            weekday: 'short',
            day: 'numeric',
            timeZone: 'UTC', // the date string is already resolved in `timezone`
        }).format(new Date(`${d.date}T12:00:00Z`)),
    }));

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
                                    {row.calls.toLocaleString()} {row.calls === 1 ? 'call' : 'calls'}
                                </p>
                                <p className="text-xs text-muted-foreground">{timezone}</p>
                            </div>
                        );
                    }}
                />
                <Bar dataKey="calls" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={44} />
            </BarChart>
        </ResponsiveContainer>
    );
}
