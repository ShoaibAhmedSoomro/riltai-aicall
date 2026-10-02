/** The three places inside one agent, and how to tell which one you are on. */

export type AgentTabKey = "editor" | "history" | "settings";

export const AGENT_TABS: { key: AgentTabKey; label: string; path: string }[] = [
    { key: "editor", label: "Editor", path: "" },
    { key: "history", label: "Call History", path: "/runs" },
    { key: "settings", label: "Settings", path: "/settings" },
];

export function agentTabHref(workflowId: number | string, key: AgentTabKey): string {
    const tab = AGENT_TABS.find((t) => t.key === key)!;
    return `/workflow/${workflowId}${tab.path}`;
}

export function agentTabLabel(key: AgentTabKey): string {
    return AGENT_TABS.find((t) => t.key === key)!.label;
}

/**
 * The tab a path belongs to, or null when it is not one of this agent's pages.
 * A single call (`/run/<id>`) belongs to Call History, so reading a call keeps
 * the right tab lit.
 */
export function activeAgentTab(pathname: string, workflowId: number | string): AgentTabKey | null {
    const base = `/workflow/${workflowId}`;
    const rest = pathname.replace(/\/+$/, "");
    if (rest === base) return "editor";
    if (rest === `${base}/settings` || rest.startsWith(`${base}/settings/`)) return "settings";
    if (rest === `${base}/runs` || rest.startsWith(`${base}/runs/`) || rest.startsWith(`${base}/run/`)) {
        return "history";
    }
    return null;
}
