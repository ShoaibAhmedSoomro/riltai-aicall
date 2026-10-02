import { render, screen, within } from '@testing-library/react';
import React from 'react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const nav = vi.hoisted(() => ({ pathname: '/overview', search: '' }));

vi.mock('next/navigation', () => ({
    usePathname: () => nav.pathname,
    useSearchParams: () => new URLSearchParams(nav.search),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('next/link', () => ({
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
        <a href={href} {...rest}>{children}</a>
    ),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ provider: 'local', user: { email: 'a@b.co' } }) }));
vi.mock('@/context/LeadFormsContext', () => ({ useLeadForms: () => ({ openHireExpert: vi.fn() }) }));
vi.mock('@/context/TelephonyConfigWarningsContext', () => ({
    useTelephonyConfigWarnings: () => ({ telnyxMissingWebhookPublicKeyCount: 0, vonageMissingSignatureSecretCount: 0 }),
}));
vi.mock('@/components/ThemeSwitcher', () => ({ default: () => <button>theme</button> }));
vi.mock('@/components/BrandLogo', () => ({ BrandLogo: () => <span>logo</span> }));
vi.mock('@/components/layout/SidebarTeamSwitcher', () => ({ SidebarTeamSwitcher: () => null }));

import { SidebarProvider } from '@/components/ui/sidebar';

import { AppSidebar } from '../AppSidebar';

beforeAll(() => {
    // jsdom has no matchMedia; the sidebar asks it whether the screen is small.
    window.matchMedia = ((query: string) => ({
        matches: false, media: query, onchange: null,
        addEventListener: () => undefined, removeEventListener: () => undefined,
        addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
});

function renderAt(pathname: string, search = '') {
    nav.pathname = pathname;
    nav.search = search;
    return render(<SidebarProvider><AppSidebar /></SidebarProvider>);
}

const active = () =>
    screen.getAllByRole('link').filter((l) => l.getAttribute('aria-current') === 'page').map((l) => l.textContent);

beforeEach(() => { nav.pathname = '/overview'; nav.search = ''; });

describe('AppSidebar', () => {
    it('groups the pages the way people look for them, and every entry is a link', () => {
        renderAt('/overview');
        for (const [label, href] of [
            ['Agents', '/workflow'], ['Knowledge Base', '/files'], ['Audio Clips', '/recordings'],
            ['Phone Numbers', '/phone-numbers'], ['Telephony', '/telephony-configurations'],
            ['Contacts', '/contacts'], ['Campaigns', '/campaigns'],
            ['Call History', '/usage'], ['Chat History', '/usage?channel=chat'],
            ['Live Calls', '/live'], ['Alerts', '/alerts'], ['Reports', '/reports'], ['Billing', '/billing'], ['Settings', '/settings'], ['Developers', '/api-keys'],
        ]) {
            expect(screen.getByRole('link', { name: label }).getAttribute('href'), label).toBe(href);
        }
        for (const heading of ['BUILD', 'DEPLOY', 'DATA', 'MONITOR', 'ACCOUNT']) {
            expect(screen.getByText(heading)).toBeDefined();
        }
    });

    it('lights exactly one entry on /usage, and the other on /usage?channel=chat', () => {
        const { unmount } = renderAt('/usage');
        expect(active()).toEqual(['Call History']);
        unmount();

        renderAt('/usage', 'channel=chat');
        expect(active()).toEqual(['Chat History']);
    });

    it('keeps Agents lit inside an agent', () => {
        renderAt('/workflow/12/settings');
        expect(active()).toEqual(['Agents']);
    });

    it('lights nothing for a page the nav does not list', () => {
        renderAt('/superadmin');
        expect(active()).toEqual([]);
    });

    it('does not carry an account menu of its own: that is the header\'s, once', () => {
        renderAt('/overview');
        expect(screen.queryByText(/sign out/i)).toBeNull();
        expect(screen.queryByText(/platform settings/i)).toBeNull();
        expect(screen.queryByRole('button', { name: /account menu/i })).toBeNull();
    });

    it('keeps the two things that are unique to the footer', () => {
        renderAt('/overview');
        expect(screen.getByRole('button', { name: /hire an expert/i })).toBeDefined();
        expect(screen.getByRole('button', { name: 'theme' })).toBeDefined();
    });

    it('has the nav as one landmark list per group', () => {
        renderAt('/overview');
        const lists = screen.getAllByRole('list');
        expect(lists.length).toBeGreaterThanOrEqual(6);
        expect(within(lists[0]).getByRole('link', { name: 'Overview' })).toBeDefined();
    });
});
