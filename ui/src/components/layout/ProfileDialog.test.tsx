import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const updateProfile = vi.fn();
const useAuth = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    updateProfileApiV1AuthProfilePatch: (...a: unknown[]) => updateProfile(...a),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('sonner', () => ({ toast: { error: (m: string) => toastError(m), success: (m: string) => toastSuccess(m) } }));

import { ProfileDialog } from './ProfileDialog';

const OK = {
    data: { token: 'new.jwt.token', user: { id: 1, email: 'a@b.c', name: 'New Name' } },
    error: undefined,
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
    useAuth.mockReturnValue({
        user: {
            id: '1',
            name: 'Old Name',
            email: 'a@b.c',
            profile: { job_title: 'Ops Lead', avatar_color: 'teal', timezone: null, phone: null },
        },
        loading: false,
    });
    updateProfile.mockReset().mockResolvedValue(OK);
    toastError.mockReset();
    toastSuccess.mockReset();
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    // save() reloads on success; jsdom would otherwise warn about navigation
    Object.defineProperty(window, 'location', {
        configurable: true,
        value: { ...window.location, reload: vi.fn() },
    });
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
});

async function open() {
    render(<ProfileDialog open onOpenChange={() => undefined} />);
    // fields seed from the current user on open
    await screen.findByDisplayValue('Old Name');
}

/** fireEvent is the house pattern here; user-event is not a dependency. */
function type(label: string, value: string) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function save() {
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
}

/** Radix unmounts inactive tab panels, so credential fields need this first.
 *  Radix activates a tab on mousedown, not click (same note as
 *  WorkflowTesterPanel.test.tsx). jest-dom matchers are not installed here,
 *  hence the raw attribute read. */
async function tab(name: RegExp) {
    fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0 });
    await waitFor(() =>
        expect(screen.getByRole('tab', { name }).getAttribute('data-state')).toBe('active'),
    );
}

describe('ProfileDialog', () => {
    it('sends only the fields that changed', async () => {
        // The server distinguishes "clear the name" (empty string) from "leave it
        // alone" (absent), so sending every field on every save would overwrite
        // values the user never touched.
        await open();
        type('Display name', 'Fresh Name');
        save();

        await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(1));
        expect(updateProfile.mock.calls[0][0].body).toEqual({ name: 'Fresh Name' });
    });

    it('refreshes the session cookie after a successful save', async () => {
        // The OSS session is a write-once httpOnly cookie and the auth context
        // exposes no update path, so skipping this leaves the header showing the
        // old name until the next sign-in.
        await open();
        type('Display name', 'Fresh Name');
        save();

        await waitFor(() =>
            expect(fetchMock.mock.calls.some(([u]) => String(u) === '/api/auth/session')).toBe(true),
        );
        const session = fetchMock.mock.calls.find(([url]) => String(url) === '/api/auth/session');
        expect(session).toBeDefined();
        const body = JSON.parse(session![1].body as string);
        // the FRESH token must be stored: the JWT embeds the email, so an email
        // change invalidates the old one
        expect(body.token).toBe('new.jwt.token');
        expect(body.user.name).toBe('New Name');
    });

    it('refuses a password change when the confirmation does not match', async () => {
        await open();
        await tab(/security/i);
        type('New password', 'longenough1');
        type('Confirm new password', 'different11');
        type('Current password', 'oldpassword');
        save();

        await waitFor(() =>
            expect(toastError).toHaveBeenCalledWith(expect.stringContaining('do not match')),
        );
        expect(updateProfile).not.toHaveBeenCalled();
    });

    it('requires the current password before setting a new one', async () => {
        await open();
        await tab(/security/i);
        type('New password', 'longenough1');
        type('Confirm new password', 'longenough1');
        save();

        await waitFor(() =>
            expect(toastError).toHaveBeenCalledWith(expect.stringContaining('current password')),
        );
        expect(updateProfile).not.toHaveBeenCalled();
    });

    it('surfaces a rejected save and does not touch the session', async () => {
        // The generated client resolves on 4xx, so an unchecked `error` would
        // look like success and then store a token that does not exist.
        updateProfile.mockResolvedValue({ data: undefined, error: { detail: 'Email already registered' } });
        await open();
        await tab(/security/i);
        type('Email', 'taken@example.com');
        save();

        await waitFor(() =>
            expect(toastError).toHaveBeenCalledWith(
                expect.stringContaining('Email already registered'),
            ),
        );
        expect(fetchMock.mock.calls.some(([u]) => String(u) === '/api/auth/session')).toBe(false);
        expect(toastSuccess).not.toHaveBeenCalled();
    });

    it('sends the whole profile blob when one preference changes', async () => {
        // The blob is replaced rather than merged, so every field it holds has
        // to be present or an untouched preference would be silently cleared.
        await open();
        type('Job title', 'Head of Operations');
        save();

        await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(1));
        expect(updateProfile.mock.calls[0][0].body).toEqual({
            profile: {
                job_title: 'Head of Operations',
                phone: null,
                timezone: null,
                avatar_color: 'teal',
            },
        });
    });

    it('keeps the name and the profile blob separate in one save', async () => {
        await open();
        type('Display name', 'Fresh Name');
        type('Job title', 'Head of Operations');
        save();

        await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(1));
        const body = updateProfile.mock.calls[0][0].body;
        expect(body.name).toBe('Fresh Name');
        expect(body.profile.job_title).toBe('Head of Operations');
        // email untouched, so it must not appear at all
        expect(body).not.toHaveProperty('email');
    });

    it('keeps Save disabled until something actually changes', async () => {
        await open();
        expect(
            (screen.getByRole('button', { name: /save changes/i }) as HTMLButtonElement).disabled,
        ).toBe(true);
    });
});
