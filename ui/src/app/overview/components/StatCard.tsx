'use client';

import type { LucideIcon } from 'lucide-react';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

/**
 * One KPI tile.
 *
 * Deliberately has no delta / "vs last month" slot. The reference dashboard this
 * is modelled on shows one on every tile, but no endpoint here returns a
 * previous-period figure, so a delta could only be invented. When a
 * previous-period aggregate exists, add it here rather than computing it in a
 * page.
 *
 * `href` makes the whole tile a link, which is how the dashboard stays navigable
 * rather than decorative: every number leads to the page that explains it.
 */
export function StatCard({
    label,
    value,
    hint,
    icon: Icon,
    href,
    loading = false,
    unavailable,
}: {
    label: string;
    value: ReactNode;
    /** Small line under the number: a breakdown, a unit, or a scope note. */
    hint?: ReactNode;
    icon: LucideIcon;
    href?: string;
    loading?: boolean;
    /** Shown instead of the value when the source could not be read. */
    unavailable?: string;
}) {
    const body = (
        <>
            <div className="flex items-start justify-between gap-3">
                <span className="text-sm font-medium text-muted-foreground">{label}</span>
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted">
                    <Icon className="size-4 text-muted-foreground" aria-hidden />
                </span>
            </div>
            <div className="mt-3">
                {loading ? (
                    <Skeleton className="h-8 w-20" />
                ) : unavailable ? (
                    <span className="text-sm text-muted-foreground">{unavailable}</span>
                ) : (
                    <span className="block text-2xl font-semibold tabular-nums tracking-tight">{value}</span>
                )}
                {hint && !loading && !unavailable && (
                    <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>
                )}
            </div>
        </>
    );

    const shell = cn(
        'rounded-xl border border-border/60 bg-card p-4 transition-colors',
        href && 'hover:border-border hover:bg-accent/40',
    );

    if (!href) return <div className={shell}>{body}</div>;

    return (
        <Link
            href={href}
            className={cn(
                shell,
                'block focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50',
            )}
        >
            {body}
        </Link>
    );
}
