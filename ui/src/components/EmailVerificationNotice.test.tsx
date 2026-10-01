import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getMe = vi.fn();
const resend = vi.fn();
const useAuth = vi.fn();
const toastError = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    getCurrentUserApiV1AuthMeGet: (...a: unknown[]) => getMe(...a),
    resendVerificationApiV1AuthResendVerificationPost: (...a: unknown[]) => resend(...a),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a) } }));

import { EmailVerificationNotice } from './EmailVerificationNotice';

/**
 * The notice must say nothing unless the server said "unverified".
 *
 * A banner that flashes for verified users, or appears because a request
 * failed, claims something about the account that nobody checked. So the
 * only input that shows it is an explicit `email_verified: false`.
 */

beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1 }, loading: false });
});

describe('EmailVerificationNotice', () => {
    it('shows for an explicitly unverified user', async () => {
        getMe.mockResolvedValue({ data: { email_verified: false } });
        render(<EmailVerificationNotice />);
        await waitFor(() => expect(screen.getByText(/isn.t verified/i)).toBeDefined());
    });

    it('stays silent for a verified user', async () => {
        getMe.mockResolvedValue({ data: { email_verified: true } });
        const { container } = render(<EmailVerificationNotice />);
        await waitFor(() => expect(getMe).toHaveBeenCalled());
        expect(container.textContent).toBe('');
    });

    it('stays silent when the lookup fails -- unknown is not unverified', async () => {
        getMe.mockResolvedValue({ error: { detail: 'boom' } });
        const { container } = render(<EmailVerificationNotice />);
        await waitFor(() => expect(getMe).toHaveBeenCalled());
        expect(container.textContent).toBe('');
    });

    it('stays silent when the field is absent', async () => {
        // An older server that predates the field must not look "unverified".
        getMe.mockResolvedValue({ data: {} });
        const { container } = render(<EmailVerificationNotice />);
        await waitFor(() => expect(getMe).toHaveBeenCalled());
        expect(container.textContent).toBe('');
    });

    it('does not fetch before auth has settled', () => {
        useAuth.mockReturnValue({ user: null, loading: true });
        render(<EmailVerificationNotice />);
        expect(getMe).not.toHaveBeenCalled();
    });

    it('confirms a send, and reports a refusal instead of claiming success', async () => {
        getMe.mockResolvedValue({ data: { email_verified: false } });
        resend.mockResolvedValueOnce({ error: { detail: 'Email is not configured' } });
        render(<EmailVerificationNotice />);
        await waitFor(() => expect(screen.getByText(/isn.t verified/i)).toBeDefined());

        fireEvent.click(screen.getByRole('button', { name: /send verification/i }));
        await waitFor(() => expect(toastError).toHaveBeenCalled());
        // A refused send must not flip the notice to "Sent."
        expect(screen.queryByText(/^Sent\./)).toBeNull();

        resend.mockResolvedValueOnce({ data: { status: 'sent' } });
        fireEvent.click(screen.getByRole('button', { name: /send verification/i }));
        await waitFor(() => expect(screen.getByText(/check your inbox/i)).toBeDefined());
    });
});
