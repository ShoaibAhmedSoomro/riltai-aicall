'use client';

import { Users } from 'lucide-react';

import { SAMPLE_COMPLIANCE, SAMPLE_CONTACTS, SAMPLE_REGIONS } from '../sampleData';
import { Panel } from './Panel';

/**
 * The three panels with no data source behind them, drawn from sampleData.ts.
 *
 * Every one passes `sample` to Panel, which renders the Sample badge.
 * sampleData.test.tsx counts the capitalized exports of THIS file against
 * SAMPLE_PANEL_IDS, so a real panel must not be added here -- it would be
 * counted as illustrative. Real ones live in RealPanels.tsx.
 *
 * Nine panels used to be here; sampleData.ts records what happened to each.
 */

export function ContactsPanel() {
    const data = SAMPLE_CONTACTS;
    return (
        <Panel title="Contacts" sample action={{ label: 'Open', href: '/campaigns' }}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {data.stats.map((s) => (
                    <div key={s.label} className="min-w-0">
                        <span className="mb-1 flex size-7 items-center justify-center rounded-md bg-muted">
                            <Users className="size-3.5 text-muted-foreground" aria-hidden />
                        </span>
                        <p className="truncate text-[11px] text-muted-foreground">{s.label}</p>
                        <p className="text-base font-semibold tabular-nums">{s.value}</p>
                    </div>
                ))}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {data.footer.map((s) => (
                    <div key={s.label} className="min-w-0 rounded-lg bg-muted/50 px-3 py-2">
                        <p className="truncate text-[11px] text-muted-foreground">{s.label}</p>
                        <p className="mt-0.5 truncate text-sm font-semibold tabular-nums">{s.value}</p>
                    </div>
                ))}
            </div>
        </Panel>
    );
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
