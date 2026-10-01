'use client';

import { ArrowUpRight, type LucideIcon } from 'lucide-react';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

/**
 * One KPI card, in two forms.
 *
 * `variant` "purple" | "blue" | "ink" is the large gradient card for the
 * headline figures: icon and title top-left, an arrow top-right, the figure
 * itself big and light along the bottom. The default is the quiet tile for
 * everything else, same anatomy on a plain surface.
 *
 * Deliberately has no delta / "vs last month" slot. No endpoint here returns a
 * previous-period figure for these tiles, so a delta could only be invented.
 * When one exists, add it here rather than computing it in a page.
 *
 * `href` makes the whole card a link, so every number leads to the page that
 * explains it.
 */
export type StatCardVariant = 'purple' | 'blue' | 'ink';

export function StatCard({
    label,
    value,
    hint,
    caption,
    icon: Icon,
    href,
    variant,
    loading = false,
    unavailable,
}: {
    label: string;
    value: ReactNode;
    /** Small line: a breakdown, a unit, or a scope note. */
    hint?: ReactNode;
    /** Tiny label above the figure on a gradient card ("Today"). */
    caption?: string;
    icon: LucideIcon;
    href?: string;
    variant?: StatCardVariant;
    loading?: boolean;
    /** Shown instead of the value when the source could not be read. */
    unavailable?: string;
}) {
    const feature = variant !== undefined;
    const showValue = !loading && !unavailable;

    const figure = loading ? (
        <Skeleton className={cn('h-10 w-28', feature && 'bg-white/20')} />
    ) : unavailable ? (
        <span className={cn('text-sm', feature ? 'text-white/70' : 'text-muted-foreground')}>{unavailable}</span>
    ) : (
        <span
            className={cn(
                'block font-light tabular-nums leading-none tracking-tight',
                feature ? 'text-4xl sm:text-[2.6rem]' : 'text-3xl',
            )}
        >
            {value}
        </span>
    );

    const body = (
        <div className={cn('flex h-full flex-col', feature ? 'min-h-[150px] justify-between' : 'gap-5')}>
            <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                    <span
                        className={cn(
                            'flex shrink-0 items-center justify-center rounded-full border',
                            feature ? 'size-9 border-white/30 text-white' : 'size-8 border-border text-muted-foreground',
                        )}
                    >
                        <Icon className="size-4" aria-hidden />
                    </span>
                    {feature && (
                        <span className="min-w-0">
                            <span className="block truncate text-sm font-medium leading-tight">{label}</span>
                            {showValue && hint && (
                                <span className="block truncate text-xs leading-tight text-white/70">{hint}</span>
                            )}
                        </span>
                    )}
                </div>
                {href && (
                    <span
                        aria-hidden
                        className={cn(
                            'flex shrink-0 items-center justify-center rounded-full transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5',
                            feature ? 'size-9 bg-black text-white' : 'size-8 bg-muted text-muted-foreground',
                        )}
                    >
                        <ArrowUpRight className="size-4" />
                    </span>
                )}
            </div>

            {feature ? (
                <div className="flex items-end justify-between gap-3">
                    <div className="min-w-0">
                        {caption && <span className="mb-1 block text-xs text-white/70">{caption}</span>}
                        {figure}
                    </div>
                </div>
            ) : (
                <div>
                    <span className="mb-2 block text-sm font-medium">{label}</span>
                    {figure}
                    {showValue && hint && (
                        <span className="mt-2 block text-xs text-muted-foreground">{hint}</span>
                    )}
                </div>
            )}
        </div>
    );

    const shell = cn(
        'group relative block overflow-hidden transition-[transform,box-shadow,border-color]',
        feature
            ? cn('rounded-3xl p-5 text-white shadow-md', `card-grad-${variant}`)
            : 'rounded-2xl border bg-card p-5 text-card-foreground',
        href && !feature && 'hover:border-ring/50',
        href && feature && 'hover:shadow-lg',
    );

    if (!href) return <div className={shell}>{body}</div>;

    return (
        <Link
            href={href}
            className={cn(
                shell,
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
            )}
        >
            {body}
        </Link>
    );
}
