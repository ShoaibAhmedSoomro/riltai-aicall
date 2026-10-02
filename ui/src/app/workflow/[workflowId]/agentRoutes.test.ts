import { describe, expect, it } from 'vitest';

import { activeAgentTab, agentTabHref, agentTabLabel } from './agentRoutes';

describe('agent tabs', () => {
    it('link to the three pages an agent has', () => {
        expect(agentTabHref(7, 'editor')).toBe('/workflow/7');
        expect(agentTabHref(7, 'history')).toBe('/workflow/7/runs');
        expect(agentTabHref('7', 'settings')).toBe('/workflow/7/settings');
    });

    it('call the history what the rest of the product calls it', () => {
        expect(agentTabLabel('history')).toBe('Call History');
    });

    it('know which page you are on, including a single call', () => {
        expect(activeAgentTab('/workflow/7', 7)).toBe('editor');
        expect(activeAgentTab('/workflow/7/', 7)).toBe('editor');
        expect(activeAgentTab('/workflow/7/runs', 7)).toBe('history');
        expect(activeAgentTab('/workflow/7/run/99', 7)).toBe('history');
        expect(activeAgentTab('/workflow/7/settings', 7)).toBe('settings');
    });

    it('never lights a tab for a different agent or an unrelated page', () => {
        expect(activeAgentTab('/workflow/70/runs', 7)).toBeNull();
        expect(activeAgentTab('/workflow/7/something-else', 7)).toBeNull();
        expect(activeAgentTab('/usage', 7)).toBeNull();
    });
});
