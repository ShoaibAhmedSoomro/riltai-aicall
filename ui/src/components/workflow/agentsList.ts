/** Pure logic for the agents list: finding, labelling and acting on agents. */

export type AgentRow = {
    id: number;
    name: string;
    status: string;
    created_at: string;
    total_runs?: number | null;
    folder_id?: number | null;
    released_version_number?: number | null;
    has_unpublished_draft?: boolean;
};

export type StatusFilter = "active" | "archived" | "all";
/** A folder id as a string, or one of these two. */
export type FolderFilter = "all" | "none" | string;

export type AgentFilter = {
    query: string;
    status: StatusFilter;
    folder: FolderFilter;
};

export const DEFAULT_FILTER: AgentFilter = { query: "", status: "active", folder: "all" };

/** Grouping is only kept when nothing is narrowing the list. */
export function isNarrowing(filter: AgentFilter): boolean {
    return filter.query.trim() !== "" || filter.folder !== "all";
}

/**
 * Agents matching the filter.
 *
 * The query matches the name (case-insensitively, anywhere in it) or the exact
 * numeric id, so pasting an id from a log or a URL finds the agent. It does NOT
 * match ids as a substring: "1" must not return agents 10 through 19.
 *
 * A folder id that no agent has returns nothing rather than everything.
 */
export function filterAgents<T extends AgentRow>(agents: T[], filter: AgentFilter): T[] {
    const q = filter.query.trim().toLowerCase();
    return agents.filter((a) => {
        if (filter.status !== "all" && a.status !== filter.status) return false;
        if (filter.folder === "none") {
            if (a.folder_id != null) return false;
        } else if (filter.folder !== "all") {
            if (String(a.folder_id ?? "") !== filter.folder) return false;
        }
        if (!q) return true;
        return a.name.toLowerCase().includes(q) || String(a.id) === q;
    });
}

/** Newest first, the order the list has always used. */
export function newestFirst<T extends AgentRow>(agents: T[]): T[] {
    return [...agents].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
}

/**
 * What a live call runs versus what the editor opens.
 *
 * The editor shows the draft when there is one, so an agent can look different
 * in the editor than it behaves on the phone. This says so.
 */
export function versionLabel(a: Pick<AgentRow, "released_version_number" | "has_unpublished_draft">): {
    text: string;
    tone: "live" | "draft" | "pending";
} {
    const live = a.released_version_number;
    if (live == null) return { text: "Draft", tone: "draft" };
    if (a.has_unpublished_draft) return { text: `Live v${live} · Draft`, tone: "pending" };
    return { text: `Live v${live}`, tone: "live" };
}

export type BulkResult = { ok: number; failed: number };

/**
 * Run one request per selected agent and report how many worked.
 *
 * ponytail: N requests rather than a bulk endpoint. The ceiling is a selection
 * large enough to hit connection limits, or one that applies only partly; the
 * upgrade path is POST /workflow/bulk-status and /workflow/bulk-folder wrapping
 * the same calls in one transaction, worth building once someone selects hundreds.
 * One failing never stops the rest, and the count says exactly what happened.
 */
export async function runBulk(ids: number[], action: (id: number) => Promise<boolean>): Promise<BulkResult> {
    const settled = await Promise.allSettled(ids.map((id) => action(id)));
    const ok = settled.filter((r) => r.status === "fulfilled" && r.value === true).length;
    return { ok, failed: ids.length - ok };
}

/** "7 archived, 1 failed" / "3 moved" / "Nothing was archived". */
export function bulkSummary(pastTense: string, { ok, failed }: BulkResult): string {
    if (ok === 0 && failed === 0) return `Nothing was ${pastTense}`;
    if (failed === 0) return `${ok} ${pastTense}`;
    if (ok === 0) return `${failed} failed, none ${pastTense}`;
    return `${ok} ${pastTense}, ${failed} failed`;
}
