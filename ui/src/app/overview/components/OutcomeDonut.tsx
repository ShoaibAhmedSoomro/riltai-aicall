'use client';

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import { dispositionLabel, dispositionPalette } from '@/lib/dispositionLabels';

import type { DispositionSlice } from '../useDashboardData';

/**
 * How today's calls ended.
 *
 * Two properties of the source shape the display. The API returns at most six
 * rows: the five most common dispositions plus a synthetic "Other" lump, so this
 * is not a full breakdown and the legend says so. And the labels arrive as raw
 * codes like user_hangup, so every one goes through dispositionLabel().
 */
export function OutcomeDonut({ data, total }: { data: DispositionSlice[]; total: number }) {
    const colors = dispositionPalette(data.map((d) => d.disposition));
    const rows = data.map((d) => ({ ...d, label: dispositionLabel(d.disposition) }));

    return (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="relative mx-auto size-[160px] shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={rows}
                            dataKey="count"
                            nameKey="label"
                            innerRadius={52}
                            outerRadius={78}
                            paddingAngle={2}
                            strokeWidth={0}
                        >
                            {rows.map((row) => (
                                <Cell key={row.disposition} fill={colors[row.disposition]} />
                            ))}
                        </Pie>
                        <Tooltip
                            content={({ active, payload }) => {
                                if (!active || !payload?.length) return null;
                                const row = payload[0].payload as (typeof rows)[number];
                                return (
                                    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-popover-foreground shadow-md">
                                        <p className="text-sm font-medium">{row.label}</p>
                                        <p className="text-xs text-muted-foreground">
                                            {row.count.toLocaleString()} · {row.percentage}%
                                        </p>
                                    </div>
                                );
                            }}
                        />
                    </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-xl font-semibold tabular-nums">{total.toLocaleString()}</span>
                    <span className="text-[11px] text-muted-foreground">calls today</span>
                </div>
            </div>

            <ul className="min-w-0 flex-1 space-y-1.5">
                {rows.map((row) => (
                    <li key={row.disposition} className="flex items-center gap-2 text-sm">
                        <span
                            aria-hidden
                            className="size-2.5 shrink-0 rounded-sm"
                            style={{ background: colors[row.disposition] }}
                        />
                        <span className="min-w-0 flex-1 truncate">{row.label}</span>
                        <span className="shrink-0 tabular-nums font-medium">{row.count.toLocaleString()}</span>
                        <span className="w-12 shrink-0 text-right tabular-nums text-xs text-muted-foreground">
                            {row.percentage}%
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
