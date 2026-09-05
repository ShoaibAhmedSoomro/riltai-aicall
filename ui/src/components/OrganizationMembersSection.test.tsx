import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The members screen, where the failures are quiet rather than loud.
 *
 * A failed load that renders an empty table reads as "you are alone in this
 * organization". A non-admin shown editable controls gets a 403 they cannot
 * explain. And the only-admin row must not offer a change the server will
 * refuse — the guard exists because an org with no admin needs database
 * surgery to recover.
 */

const listMembers = vi.fn();
const updateRole = vi.fn();
const useAuth = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    listMembersApiV1OrganizationsMembersGet: (...a: unknown[]) => listMembers(...a),
    updateMemberRoleApiV1OrganizationsMembersUserIdPatch: (...a: unknown[]) => updateRole(...a),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { OrganizationMembersSection } from './OrganizationMembersSection';

const ADMIN = { user_id: 1, email: 'a@x.com', name: 'Ada', role: 'admin', is_superuser: false, is_self: true };
const OTHER_ADMIN = { user_id: 2, email: 'b@x.com', name: 'Ben', role: 'admin', is_superuser: false, is_self: false };
const MEMBER = { user_id: 3, email: 'c@x.com', name: 'Cleo', role: 'member', is_superuser: false, is_self: false };

function mount(data: unknown[], error?: unknown) {
    listMembers.mockResolvedValue(error ? { error } : { data });
    return render(<OrganizationMembersSection />);
}

beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1 }, loading: false });
    updateRole.mockResolvedValue({ data: {} });
});

describe('OrganizationMembersSection', () => {
    it('lists every member with their role', async () => {
        mount([ADMIN, OTHER_ADMIN, MEMBER]);
        await waitFor(() => expect(screen.getByText('Ada')).toBeDefined());
        expect(screen.getByText('Ben')).toBeDefined();
        expect(screen.getByText('Cleo')).toBeDefined();
    });

    it('marks which row is you', async () => {
        mount([ADMIN, MEMBER]);
        await waitFor(() => expect(screen.getByText('You')).toBeDefined());
    });

    it('shows an error instead of an empty organization when the load fails', async () => {
        // The generated client resolves on HTTP errors rather than throwing, so
        // an unchecked failure would render a member list of nobody — which
        // reads as fact rather than as a failure.
        mount([], { detail: 'Boom' });
        await waitFor(() => expect(screen.getByText('Boom')).toBeDefined());
        expect(screen.queryByRole('table')).toBeNull();
    });

    it('gives an admin a control to change roles', async () => {
        mount([ADMIN, OTHER_ADMIN, MEMBER]);
        await waitFor(() => expect(screen.getByText('Cleo')).toBeDefined());
        // Radix Select renders its trigger as a combobox.
        expect(screen.getAllByRole('combobox').length).toBe(3);
    });

    it('shows a member read-only badges and says who to ask', async () => {
        const asMember = { ...MEMBER, is_self: true };
        mount([{ ...ADMIN, is_self: false }, asMember]);
        await waitFor(() => expect(screen.getByText('Cleo')).toBeDefined());
        expect(screen.queryByRole('combobox')).toBeNull();
        expect(screen.getByText(/Only an admin can change roles/)).toBeDefined();
    });

    it('will not offer to change the only admin, and says why', async () => {
        // Matches the server's last-admin guard rather than letting the user
        // discover it as a rejected request.
        mount([ADMIN, MEMBER]);
        await waitFor(() => expect(screen.getByText('Ada')).toBeDefined());
        const triggers = screen.getAllByRole('combobox');
        expect(triggers.some((t) => t.hasAttribute('disabled'))).toBe(true);
        expect(screen.getByText(/one admin, so that role cannot be changed/)).toBeDefined();
    });

    it('treats a superuser as able to manage roles even without the org role', async () => {
        // The platform tier spans every org and passes require_admin, so the UI
        // must not present itself as read-only to someone the API will accept.
        const su = { ...MEMBER, is_self: true, is_superuser: true };
        mount([{ ...ADMIN, is_self: false }, OTHER_ADMIN, su]);
        await waitFor(() => expect(screen.getByText('Cleo')).toBeDefined());
        expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0);
    });
});
