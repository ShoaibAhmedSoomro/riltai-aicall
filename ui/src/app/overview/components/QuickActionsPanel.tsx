'use client';

import Link from 'next/link';

import { QUICK_ACTIONS } from '@/lib/quickActions';

import { Panel } from './Panel';

/** The same actions as the top-bar menu, laid out as a grid with descriptions. */
export function QuickActionsPanel() {
    return (
        <Panel title="Quick actions" subtitle="Jump straight to the thing you want to set up">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {QUICK_ACTIONS.map((action) => (
                    <Link
                        key={action.id}
                        href={action.href}
                        className="flex items-start gap-3 rounded-lg border border-border/60 p-3 transition-colors hover:border-border hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    >
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
                            <action.icon className="size-4 text-muted-foreground" aria-hidden />
                        </span>
                        <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">{action.label}</span>
                            <span className="block text-xs text-muted-foreground">{action.description}</span>
                        </span>
                    </Link>
                ))}
            </div>
        </Panel>
    );
}
