import { describe, expect, it } from 'vitest';

import type { AlertEventResponse, AlertItem } from '@/client/types.gen';

import { mergeAlertFeeds, PANEL_ALERT_LIMIT, ruleAlertToItem } from './alertFeed';

const failure = (at: string, text = 'Webhook failed'): AlertItem => ({
    severity: 'error', text, href: '/reports', count: 1, occurred_at: at,
});
const event = (over: Partial<AlertEventResponse> = {}): AlertEventResponse => ({
    event_uuid: 'e', severity: 'high', title: 'Failures', detail: { condition: 'A call failed', workflow_id: 3 },
    created_at: '2026-10-02T10:00:00Z', ...over,
}) as AlertEventResponse;

describe('ruleAlertToItem', () => {
    it('maps severity to the panel’s words and links to the call when there is one', () => {
        const item = ruleAlertToItem(event({ workflow_run_id: 9 }));
        expect(item).toMatchObject({ severity: 'error', text: 'Failures: A call failed', href: '/workflow/3/run/9' });
        expect(ruleAlertToItem(event({ severity: 'medium' })).severity).toBe('warning');
        expect(ruleAlertToItem(event({ severity: 'low' })).severity).toBe('info');
    });

    it('links to the Alerts page when the alert is not about one call', () => {
        expect(ruleAlertToItem(event()).href).toBe('/alerts');
    });
});

describe('mergeAlertFeeds', () => {
    it('is unknown only when both sources are unknown', () => {
        expect(mergeAlertFeeds(null, null)).toBeNull();
        expect(mergeAlertFeeds([], null)).toEqual([]);
        expect(mergeAlertFeeds(null, [])).toEqual([]);
    });

    it('one source failing does not blank the other', () => {
        expect(mergeAlertFeeds([failure('2026-10-02T09:00:00Z')], null)).toHaveLength(1);
        expect(mergeAlertFeeds(null, [event()])).toHaveLength(1);
    });

    it('orders newest first across both', () => {
        const out = mergeAlertFeeds(
            [failure('2026-10-02T09:00:00Z', 'old'), failure('2026-10-02T11:00:00Z', 'newest')],
            [event({ created_at: '2026-10-02T10:00:00Z' })],
        );
        expect(out!.map((i) => i.text)).toEqual(['newest', 'Failures: A call failed', 'old']);
    });

    it('leaves out alerts someone has already acknowledged', () => {
        expect(mergeAlertFeeds([], [event({ acknowledged_at: '2026-10-02T10:05:00Z' })])).toEqual([]);
    });

    it('keeps the panel short', () => {
        const many = Array.from({ length: 20 }, (_, i) => failure(`2026-10-02T${String(i).padStart(2, '0')}:00:00Z`));
        expect(mergeAlertFeeds(many, [])).toHaveLength(PANEL_ALERT_LIMIT);
    });
});
