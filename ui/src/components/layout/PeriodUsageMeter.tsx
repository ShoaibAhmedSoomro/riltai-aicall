"use client";

import { Clock } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { getCurrentPeriodUsageApiV1OrganizationsUsageCurrentPeriodGet } from "@/client/sdk.gen";
import type { CurrentUsageResponse } from "@/client/types.gen";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

// These deliberately do NOT reuse the page-local helpers elsewhere in the app,
// because both have a different contract:
//   usage/page.tsx formatDuration  -> seconds-precise for ONE call ("3m 20s"),
//                                     which becomes "183m 20s" over a period
//   billing/page.tsx formatAmount  -> takes MINOR units (cents), while
//                                     used_amount_usd is already in dollars
// Reconciling all three into one helper would change how those pages render,
// which is a bigger change than this header needs. Exported for the test.

/** Seconds to a compact period total: "0 min", "12.4 min", "2h 04m". */
export function formatDuration(seconds: number): string {
    if (!Number.isFinite(seconds) || seconds <= 0) return "0 min";
    const minutes = seconds / 60;
    if (minutes < 60) {
        // A decimal only under ten minutes. Above that it is noise, but below
        // it a whole-minute round would turn 24 seconds of real calls into
        // "0 min", which reads as "nothing ran".
        return `${minutes < 10 ? minutes.toFixed(1) : Math.round(minutes)} min`;
    }
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${String(Math.round(minutes % 60)).padStart(2, "0")}m`;
}

export function formatMoney(amount: number, currency: string | null | undefined): string {
    const code = (currency || "USD").toUpperCase();
    try {
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency: code,
            maximumFractionDigits: amount < 10 ? 2 : 0,
        }).format(amount);
    } catch {
        // Intl throws on a currency code it does not know; the number still
        // carries the useful information.
        return `${amount.toFixed(2)} ${code}`;
    }
}

export function formatPeriod(start: string, end: string): string | null {
    const from = new Date(start);
    const to = new Date(end);
    if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return null;
    const fmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
    return `${fmt.format(from)} – ${fmt.format(to)}`;
}

/**
 * Call volume and spend for the current billing period, in the app header.
 *
 * This replaced two outbound promo links (a community invite and a GitHub star
 * badge) that told the operator nothing about their own account. Minutes are
 * the number that matters on a calling platform and they were previously only
 * visible by navigating to Agent Runs.
 *
 * `/usage/current-period` already existed, was already typed into the generated
 * client, and had no caller — so this surfaces data the backend was already
 * computing rather than adding an endpoint.
 *
 * It renders NOTHING on any failure. A self-hosted install with no organization
 * selected gets a 400 here, and BYOK installs have no priced amount at all; a
 * header ornament must never turn either into a visible error.
 */
export function PeriodUsageMeter({ className }: { className?: string }) {
    const { user, loading: authLoading } = useAuth();
    const pathname = usePathname();
    const [usage, setUsage] = useState<CurrentUsageResponse | null>(null);
    // Guards the double-invoked effect in React strict mode and any overlapping
    // request. It does NOT guard repeat renders, which is why the effect keys off
    // the id below rather than the user object.
    const inFlight = useRef(false);

    // A stable primitive, deliberately not the `user` object: on the hosted auth
    // path `user` comes from the Stack SDK's own hook, and if that returns a
    // fresh object per render this effect would refetch on every render.
    const userId = user?.id ?? null;

    useEffect(() => {
        // The auth interceptor that attaches the bearer token is only registered
        // once auth has finished loading; fetching earlier sends an
        // unauthenticated request that silently fails.
        if (authLoading || !userId || inFlight.current) return;

        inFlight.current = true;
        void (async () => {
            try {
                const response = await getCurrentPeriodUsageApiV1OrganizationsUsageCurrentPeriodGet();
                // The generated client resolves rather than throwing on 4xx/5xx,
                // so `error` has to be checked explicitly.
                setUsage(response.error || !response.data ? null : response.data);
            } catch {
                setUsage(null);
            } finally {
                inFlight.current = false;
            }
        })();
        // ponytail: refetches on navigation instead of polling or watching focus.
        // Navigations are user-paced and this is a cheap aggregate. If it ever
        // shows up in request volume, add a timestamp guard here.
    }, [authLoading, userId, pathname]);

    if (!usage) return null;

    const duration = formatDuration(usage.total_duration_seconds);
    const spend =
        typeof usage.used_amount_usd === "number" && usage.used_amount_usd > 0
            ? formatMoney(usage.used_amount_usd, usage.currency)
            : null;
    const period = formatPeriod(usage.period_start, usage.period_end);

    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <Link
                    href="/usage"
                    aria-label={`Usage this period: ${duration}${spend ? `, ${spend}` : ""}. View agent runs.`}
                    className={cn(
                        "inline-flex items-center gap-2 rounded-md border border-border/60 bg-muted/50 px-2.5 py-1.5",
                        "text-sm leading-none tabular-nums transition-colors hover:bg-accent hover:text-accent-foreground",
                        "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                        className,
                    )}
                >
                    <Clock className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="font-medium">{duration}</span>
                    {spend && (
                        <>
                            {/* muted-foreground, not border: --border is white at
                                10% in the dark theme, which made the separator
                                read as a rendering artefact rather than a divider. */}
                            <span aria-hidden className="text-muted-foreground/70">·</span>
                            <span className="hidden font-medium sm:inline">{spend}</span>
                        </>
                    )}
                </Link>
            </TooltipTrigger>
            <TooltipContent side="bottom">
                <p className="font-medium">Usage this period</p>
                {period && <p className="text-xs opacity-80">{period}</p>}
                <p className="text-xs opacity-80">
                    {duration} of calls
                    {spend ? ` · ${spend}` : ""}
                    {usage.used_dograh_tokens > 0
                        ? ` · ${Math.round(usage.used_dograh_tokens).toLocaleString()} RiltAI Tokens`
                        : ""}
                </p>
            </TooltipContent>
        </Tooltip>
    );
}
