import type { AlertEventResponse, AlertItem } from '@/client/types.gen';

/** The panel shows the most recent few; the Alerts page is for the rest. */
export const PANEL_ALERT_LIMIT = 8;

// The failure feed speaks error/warning; rules speak high/medium/low.
const SEVERITY: Record<string, string> = { high: 'error', medium: 'warning', low: 'info' };

/** A rule alert as a panel row. Acknowledged alerts are left out: seen is done. */
export function ruleAlertToItem(event: AlertEventResponse): AlertItem {
    const detail = event.detail as { condition?: string; workflow_id?: number };
    return {
        severity: SEVERITY[event.severity] ?? 'info',
        text: detail.condition ? `${event.title}: ${detail.condition}` : event.title,
        href:
            event.workflow_run_id && detail.workflow_id
                ? `/workflow/${detail.workflow_id}/run/${event.workflow_run_id}`
                : '/alerts',
        count: 1,
        occurred_at: event.created_at,
    };
}

/**
 * One feed from the two sources, newest first. Either may be missing (null) because
 * each loads on its own and one failing must not blank the other; only when both are
 * missing is the whole feed unknown, which is different from "nothing needs attention".
 */
export function mergeAlertFeeds(
    failures: AlertItem[] | null,
    ruleEvents: AlertEventResponse[] | null,
): AlertItem[] | null {
    if (failures === null && ruleEvents === null) return null;
    const fromRules = (ruleEvents ?? []).filter((e) => !e.acknowledged_at).map(ruleAlertToItem);
    const when = (i: AlertItem) => (i.occurred_at ? Date.parse(i.occurred_at) || 0 : 0);
    return [...(failures ?? []), ...fromRules].sort((a, b) => when(b) - when(a)).slice(0, PANEL_ALERT_LIMIT);
}
