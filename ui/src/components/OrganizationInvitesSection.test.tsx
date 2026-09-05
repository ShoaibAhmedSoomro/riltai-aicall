import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Invitations, where the most important thing on screen is a caveat.
 *
 * Nothing delivers an invite yet — this deployment has no email — so an admin
 * who creates one and waits has been misled by the UI, not by the backend. The
 * notice saying so is therefore a tested behaviour, not decoration.
 *
 * The other two: a member must be told plainly that this is admin-only (the
 * list endpoint 403s, and an unexplained empty panel reads as "no invitations"),
 * and the server's refusals must reach the user, because they name the actual
 * problem — already a member, already invited.
 */

const listInvites = vi.fn();
const createInvite = vi.fn();
const revokeInvite = vi.fn();
const useAuth = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    listInvitesApiV1OrganizationsInvitesGet: (...a: unknown[]) => listInvites(...a),
    createInviteApiV1OrganizationsInvitesPost: (...a: unknown[]) => createInvite(...a),
    revokeInviteApiV1OrganizationsInvitesInviteIdDelete: (...a: unknown[]) => revokeInvite(...a),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) } }));

import { OrganizationInvitesSection } from './OrganizationInvitesSection';

const PENDING = {
    id: 1,
    email: 'new@x.com',
    role: 'member',
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 3 * 86400_000).toISOString(),
    invited_by_email: 'admin@x.com',
};

beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1 }, loading: false });
    listInvites.mockResolvedValue({ data: [] });
    createInvite.mockResolvedValue({ data: PENDING });
    revokeInvite.mockResolvedValue({ data: null });
});

describe('OrganizationInvitesSection', () => {
    it('says up front that invitations cannot be delivered yet', async () => {
        render(<OrganizationInvitesSection />);
        await waitFor(() =>
            expect(screen.getByText(/recorded but not yet delivered/i)).toBeDefined(),
        );
    });

    it('lists pending invitations with who invited them', async () => {
        listInvites.mockResolvedValue({ data: [PENDING] });
        render(<OrganizationInvitesSection />);
        await waitFor(() => expect(screen.getByText('new@x.com')).toBeDefined());
        expect(screen.getByText(/by admin@x.com/)).toBeDefined();
        expect(screen.getByText(/Expires in 3 days/)).toBeDefined();
    });

    it('tells a member this is admin-only instead of showing an empty panel', async () => {
        // The endpoint 403s for members. An unexplained empty list would read as
        // "there are no invitations", which is a different and wrong statement.
        listInvites.mockResolvedValue({ error: { detail: 'nope' }, response: { status: 403 } });
        render(<OrganizationInvitesSection />);
        await waitFor(() =>
            expect(screen.getByText(/Only an admin can invite/i)).toBeDefined(),
        );
        expect(screen.queryByLabelText(/Email address/i)).toBeNull();
    });

    it('defaults the role to member', async () => {
        render(<OrganizationInvitesSection />);
        await waitFor(() => expect(screen.getByLabelText(/Email address/i)).toBeDefined());
        fireEvent.change(screen.getByLabelText(/Email address/i), {
            target: { value: 'a@b.com' },
        });
        fireEvent.click(screen.getByRole('button', { name: /Create invitation/i }));
        await waitFor(() => expect(createInvite).toHaveBeenCalled());
        expect(createInvite.mock.calls[0][0].body.role).toBe('member');
    });

    it('surfaces the server refusal rather than a generic failure', async () => {
        // "That person is already in this organization" is the useful message;
        // swallowing it leaves the admin guessing.
        createInvite.mockResolvedValue({
            error: { detail: 'That person is already in this organization.' },
        });
        render(<OrganizationInvitesSection />);
        await waitFor(() => expect(screen.getByLabelText(/Email address/i)).toBeDefined());
        fireEvent.change(screen.getByLabelText(/Email address/i), {
            target: { value: 'dup@x.com' },
        });
        fireEvent.click(screen.getByRole('button', { name: /Create invitation/i }));
        await waitFor(() =>
            expect(toastError).toHaveBeenCalledWith(
                'That person is already in this organization.',
            ),
        );
    });

    it('removes a revoked invitation from the list', async () => {
        listInvites.mockResolvedValue({ data: [PENDING] });
        render(<OrganizationInvitesSection />);
        await waitFor(() => expect(screen.getByText('new@x.com')).toBeDefined());
        fireEvent.click(screen.getByLabelText(/Withdraw invitation to new@x.com/i));
        await waitFor(() => expect(screen.queryByText('new@x.com')).toBeNull());
    });

    it('does not drop a failed revoke from the list', async () => {
        // Removing it optimistically on failure would show the invite as gone
        // while it is still live and still acceptable.
        listInvites.mockResolvedValue({ data: [PENDING] });
        revokeInvite.mockResolvedValue({ error: { detail: 'nope' } });
        render(<OrganizationInvitesSection />);
        await waitFor(() => expect(screen.getByText('new@x.com')).toBeDefined());
        fireEvent.click(screen.getByLabelText(/Withdraw invitation to new@x.com/i));
        await waitFor(() => expect(toastError).toHaveBeenCalled());
        expect(screen.getByText('new@x.com')).toBeDefined();
    });
});
