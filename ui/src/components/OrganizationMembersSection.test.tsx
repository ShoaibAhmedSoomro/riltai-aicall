import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The members screen, where the failures are quiet rather than loud.
 *
 * A failed load that renders an empty table reads as "you are alone in this
 * organization". A non-admin shown editable controls gets a 403 they cannot
 * explain. And the only-admin row must not offer a change the server will
 * refuse — the guard exists because an org with no admin needs database
 * surgery to recover.
 *
 * Removal adds one more: leaving clears your selected organization server-side,
 * so a session that stays open afterwards resolves no organization at all and
 * every screen 400s. Signing out is part of the action, not a nicety.
 */

const listMembers = vi.fn();
const updateRole = vi.fn();
const removeMember = vi.fn();
const useAuth = vi.fn();
const logout = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    listMembersApiV1OrganizationsMembersGet: (...a: unknown[]) => listMembers(...a),
    updateMemberRoleApiV1OrganizationsMembersUserIdPatch: (...a: unknown[]) => updateRole(...a),
    removeMemberApiV1OrganizationsMembersUserIdDelete: (...a: unknown[]) => removeMember(...a),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) } }));

import { OrganizationMembersSection } from './OrganizationMembersSection';

const ADMIN = { user_id: 1, email: 'a@x.com', name: 'Ada', role: 'admin', is_superuser: false, is_self: true };
const OTHER_ADMIN = { user_id: 2, email: 'b@x.com', name: 'Ben', role: 'admin', is_superuser: false, is_self: false };
const MEMBER = { user_id: 3, email: 'c@x.com', name: 'Cleo', role: 'member', is_superuser: false, is_self: false };

function mount(data: unknown[], error?: unknown) {
    listMembers.mockResolvedValue(error ? { error } : { data });
    return render(<OrganizationMembersSection />);
}

async function confirm(label: RegExp) {
    fireEvent.click(await screen.findByLabelText(label));
    fireEvent.click(await screen.findByRole('button', { name: /^Yes,/ }));
}

beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1 }, loading: false, logout });
    updateRole.mockResolvedValue({ data: {} });
    removeMember.mockResolvedValue({ data: null });
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

    // ── removal ─────────────────────────────────────────────────────────────

    it('lets an admin remove someone, and drops the row', async () => {
        mount([ADMIN, OTHER_ADMIN, MEMBER]);
        await confirm(/Remove Cleo/i);
        await waitFor(() => expect(removeMember).toHaveBeenCalled());
        expect(removeMember.mock.calls[0][0].path.user_id).toBe(MEMBER.user_id);
        await waitFor(() => expect(screen.queryByText('Cleo')).toBeNull());
    });

    it('asks before removing rather than acting on the first click', async () => {
        // Removal is not undoable from this screen -- the person has to be
        // invited back -- so a mis-click must not be enough.
        mount([ADMIN, OTHER_ADMIN, MEMBER]);
        fireEvent.click(await screen.findByLabelText(/Remove Cleo/i));
        expect(removeMember).not.toHaveBeenCalled();
        expect(screen.getByText('Cleo')).toBeDefined();
    });

    it('lets a plain member leave but not remove anyone else', async () => {
        // The endpoint is deliberately not admin-gated for exactly this: a
        // member who cannot leave unaided is trapped in the organization.
        mount([{ ...ADMIN, is_self: false }, { ...MEMBER, is_self: true }]);
        await waitFor(() => expect(screen.getByText('Cleo')).toBeDefined());
        expect(screen.getByLabelText(/Leave this organization/i)).toBeDefined();
        expect(screen.queryByLabelText(/Remove Ada/i)).toBeNull();
    });

    it('signs you out after you leave, instead of leaving a session with no org', async () => {
        // The server clears selected_organization_id, so staying signed in
        // means every org-scoped screen 400s with no explanation.
        mount([{ ...ADMIN, is_self: false }, OTHER_ADMIN, { ...MEMBER, is_self: true }]);
        await confirm(/Leave this organization/i);
        await waitFor(() => expect(logout).toHaveBeenCalled());
    });

    it('does not sign you out when removing somebody else', async () => {
        mount([ADMIN, OTHER_ADMIN, MEMBER]);
        await confirm(/Remove Cleo/i);
        await waitFor(() => expect(screen.queryByText('Cleo')).toBeNull());
        expect(logout).not.toHaveBeenCalled();
    });

    it('keeps the row and surfaces the reason when the server refuses', async () => {
        // Dropping the row optimistically would show someone as removed while
        // they still have full access.
        removeMember.mockResolvedValue({
            error: { detail: "This is the organization's only admin." },
        });
        mount([ADMIN, OTHER_ADMIN, MEMBER]);
        await confirm(/Remove Cleo/i);
        await waitFor(() =>
            expect(toastError).toHaveBeenCalledWith("This is the organization's only admin."),
        );
        expect(screen.getByText('Cleo')).toBeDefined();
    });

    it('will not offer to remove the only admin', async () => {
        mount([ADMIN, MEMBER]);
        const own = await screen.findByLabelText(/Leave this organization/i);
        expect(own.hasAttribute('disabled')).toBe(true);
        fireEvent.click(own);
        expect(removeMember).not.toHaveBeenCalled();
    });

    it('warns that an API key outlives the person who knew it', async () => {
        // Keys belong to the organization, not to whoever minted one, so
        // removal alone does not revoke what they already copied.
        mount([ADMIN, OTHER_ADMIN, MEMBER]);
        fireEvent.click(await screen.findByLabelText(/Remove Cleo/i));
        expect(await screen.findByText(/until you rotate it/i)).toBeDefined();
    });
});
