import { existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { findActiveNavItem, NAV_SECTIONS } from '../navConfig';

// ui/src/app, from ui/src/components/layout/__tests__
const APP_DIR = join(__dirname, '..', '..', '..', 'app');

const ALL_ITEMS = NAV_SECTIONS.flatMap((s) => s.items);
const title = (pathname: string, search = '') => findActiveNavItem(NAV_SECTIONS, pathname, search)?.title ?? null;

describe('the sidebar leads somewhere real', () => {
    /**
     * The test that fails when a nav item points nowhere. It would have caught a
     * "Coming soon" stub being linked, and it catches any route rename that forgets
     * the nav. `/foo` must have `app/foo/page.tsx`.
     */
    it.each(ALL_ITEMS.map((i) => [i.title, i.url]))('%s → %s has a page', (_title, url) => {
        const path = url.split('?')[0].replace(/^\//, '');
        expect(existsSync(join(APP_DIR, path, 'page.tsx')), `app/${path}/page.tsx`).toBe(true);
    });

    it('has no entry twice, and no two entries that go to the same place', () => {
        const titles = ALL_ITEMS.map((i) => i.title);
        const urls = ALL_ITEMS.map((i) => i.url);
        expect(new Set(titles).size).toBe(titles.length);
        expect(new Set(urls).size).toBe(urls.length);
    });

    it('keeps the grouping people navigate by', () => {
        expect(NAV_SECTIONS.map((s) => s.label ?? '(top)')).toEqual([
            '(top)', 'BUILD', 'DEPLOY', 'DATA', 'MONITOR', 'ACCOUNT',
        ]);
    });

    it('no page that was deleted is linked', () => {
        expect(ALL_ITEMS.some((i) => i.url.startsWith('/automation'))).toBe(false);
        expect(statSync(APP_DIR).isDirectory()).toBe(true);
        expect(readdirSync(APP_DIR)).not.toContain('automation');
    });
});

describe('which item is active', () => {
    it('lights only Call History at /usage, and only Chat History at /usage?channel=chat', () => {
        expect(title('/usage')).toBe('Call History');
        expect(title('/usage', 'channel=chat')).toBe('Chat History');
    });

    it('a different channel, or an applied filter, is still Call History', () => {
        expect(title('/usage', 'channel=telephony')).toBe('Call History');
        expect(title('/usage', 'filters=%5B%5D')).toBe('Call History');
    });

    it('a page inside a section keeps that section lit', () => {
        expect(title('/workflow')).toBe('Agents');
        expect(title('/workflow/12/settings')).toBe('Agents');
        expect(title('/contacts/lists')).toBe('Contacts');
        expect(title('/telephony-configurations/4')).toBe('Telephony');
    });

    it('matches on a path boundary, not a text prefix', () => {
        expect(title('/workflows-archive')).toBeNull();
        expect(title('/files-old')).toBeNull();
    });

    it('is exactly one item, never two', () => {
        for (const [path, search] of [['/usage', ''], ['/usage', 'channel=chat'], ['/workflow/1', ''], ['/settings', '']]) {
            const lit = ALL_ITEMS.filter((i) => findActiveNavItem(NAV_SECTIONS, path, search)?.url === i.url);
            expect(lit).toHaveLength(1);
        }
    });

    it('nothing is lit on a page the nav does not cover', () => {
        expect(title('/superadmin')).toBeNull();
        expect(title('/')).toBeNull();
    });

    it('the new pages are reachable and light up', () => {
        expect(title('/phone-numbers')).toBe('Phone Numbers');
        expect(title('/settings')).toBe('Settings');
        expect(title('/billing')).toBe('Billing');
        expect(title('/recordings')).toBe('Audio Clips');
        expect(title('/files')).toBe('Knowledge Base');
    });
});
