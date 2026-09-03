'use client';

import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

import { SampleBadge } from './SampleBadge';

/**
 * A titled dashboard panel with an optional "view all" link and a built-in
 * empty state.
 *
 * The empty state matters more than usual here: a fresh self-hosted install has
 * made no calls, so most panels on this dashboard legitimately have nothing to
 * show on day one. Each one says what would fill it rather than rendering a
 * blank box or a zeroed chart, which would read as broken.
 */
export function Panel({
    title,
    subtitle,
    action,
    sample = false,
    loading = false,
    empty,
    className,
    bodyClassName,
    children,
}: {
    title: string;
    subtitle?: ReactNode;
    action?: { label: string; href: string };
    /** Renders the Sample badge: this panel's figures are illustrative. */
    sample?: boolean;
    loading?: boolean;
    /** When set, replaces the body: a sentence saying what would fill this. */
    empty?: ReactNode;
    className?: string;
    bodyClassName?: string;
    children?: ReactNode;
}) {
    return (
        <section className={cn('flex flex-col rounded-xl border border-border/60 bg-card', className)}>
            <header className="flex items-start justify-between gap-3 border-b border-border/60 px-4 py-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <h2 className="truncate text-sm font-semibold">{title}</h2>
                        {sample && <SampleBadge />}
                    </div>
                    {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
                </div>
                {action && (
                    <Link
                        href={action.href}
                        className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    >
                        {action.label}
                        <ArrowRight className="size-3" aria-hidden />
                    </Link>
                )}
            </header>
            <div className={cn('flex-1 p-4', bodyClassName)}>
                {loading ? (
                    <div className="space-y-2">
                        <Skeleton className="h-4 w-2/3" />
                        <Skeleton className="h-4 w-1/2" />
                        <Skeleton className="h-4 w-3/4" />
                    </div>
                ) : empty ? (
                    <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>
                ) : (
                    children
                )}
            </div>
        </section>
    );
}
