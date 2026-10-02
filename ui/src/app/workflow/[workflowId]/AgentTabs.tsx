"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { getWorkflowsSummaryApiV1WorkflowSummaryGet } from "@/client/sdk.gen";
import { cn } from "@/lib/utils";

import { activeAgentTab, AGENT_TABS, agentTabHref } from "./agentRoutes";

/**
 * One way to move between an agent's Editor, Call History and Settings.
 *
 * Pass `name` to show it, `null` to show no name (a page that already has its own
 * heading), or leave it out to look the name up. The editor itself is left alone:
 * it suppresses the app header to give the canvas full height, and its own header
 * already carries the name, Publish and Duplicate.
 */
export function AgentTabs({
    workflowId,
    name,
    className,
}: {
    workflowId: number;
    name?: string | null;
    className?: string;
}) {
    const pathname = usePathname();
    const active = activeAgentTab(pathname, workflowId);
    const [looked, setLooked] = useState<string | null>(null);

    useEffect(() => {
        if (name !== undefined) return;
        let cancelled = false;
        void getWorkflowsSummaryApiV1WorkflowSummaryGet().then((res) => {
            const hit = (res.data ?? []).find((w) => w.id === workflowId);
            if (!cancelled && hit) setLooked(hit.name);
        });
        return () => { cancelled = true; };
    }, [name, workflowId]);

    const shown = name === undefined ? looked : name;

    return (
        <div className={cn("flex flex-wrap items-center gap-x-6 gap-y-1 border-b px-6", className)}>
            {shown && <span className="py-3 text-sm font-semibold">{shown}</span>}
            <nav aria-label="Agent" className="flex items-center gap-1">
                {AGENT_TABS.map((tab) => (
                    <Link
                        key={tab.key}
                        href={agentTabHref(workflowId, tab.key)}
                        aria-current={active === tab.key ? "page" : undefined}
                        className={cn(
                            "-mb-px border-b-2 px-3 py-3 text-sm transition-colors",
                            active === tab.key
                                ? "border-primary font-medium text-foreground"
                                : "border-transparent text-muted-foreground hover:text-foreground",
                        )}
                    >
                        {tab.label}
                    </Link>
                ))}
            </nav>
        </div>
    );
}
