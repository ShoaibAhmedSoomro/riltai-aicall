import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getStatus = vi.fn();
const requestPrune = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();
const useAuth = vi.fn();

vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('@/client/sdk.gen', () => ({
    getMaintenanceStatusApiV1SuperuserMaintenanceGet: (...a: unknown[]) => getStatus(...a),
    requestBuildCachePruneApiV1SuperuserMaintenancePruneBuildCachePost: (...a: unknown[]) =>
        requestPrune(...a),
}));
vi.mock('sonner', () => ({
    toast: {
        success: (...a: unknown[]) => toastSuccess(...a),
        error: (...a: unknown[]) => toastError(...a),
    },
}));

import { formatBytes, MaintenancePanel } from './MaintenancePanel';

/**
 * Three things must never be confused: a cache size the server has not
 * reported yet, a cache that is empty, and a clean-up that failed. Showing the
 * first as "0 B" would tell an operator sitting on 100 GB that there is nothing
 * to clear.
 */

const DISK = { total_bytes: 145e9, used_bytes: 17e9, free_bytes: 128e9, percent: 11.7 };

const status = (over: Record<string, unknown> = {}) => ({
    available: true,
    disk: DISK,
    build_cache_bytes: null,
    status_updated_at: null,
    last_prune: null,
    policy: { auto_keep_hours: 168, emergency_disk_percent: 85 },
    prune_requested: false,
    ...over,
});

beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1 }, loading: false });
    getStatus.mockResolvedValue({ data: status() });
});

describe('formatBytes', () => {
    it.each([
        [0, '0 B'],
        [999, '999 B'],
        [5_307_000_000, '5.3 GB'],
        [109_200_000_000, '109 GB'],
        [1_500, '1.5 kB'],
    ])('%s -> %s', (n, text) => expect(formatBytes(n)).toBe(text));
});

describe('MaintenancePanel states', () => {
    it('says "not reported yet" when the server has not reported a size', async () => {
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText('Not reported yet')).toBeDefined());
        expect(screen.queryByText('0 B')).toBeNull();
    });

    it('shows a genuinely empty cache as 0 B', async () => {
        getStatus.mockResolvedValue({ data: status({ build_cache_bytes: 0 }) });
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText('0 B')).toBeDefined());
        expect(screen.queryByText('Not reported yet')).toBeNull();
    });

    it('shows a failed clean-up with its reason, not as a success', async () => {
        getStatus.mockResolvedValue({
            data: status({
                build_cache_bytes: 5e9,
                last_prune: {
                    at: '2026-10-01T12:42:00+00:00',
                    source: 'manual',
                    ok: false,
                    freed_bytes: 0,
                    error: 'permission denied on buildx lock',
                },
            }),
        });
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText(/last clean-up failed/i)).toBeDefined());
        expect(screen.getByText(/permission denied on buildx lock/)).toBeDefined();
        // A failed run must not claim to have freed space.
        expect(screen.queryByText(/freed/i)).toBeNull();
    });

    it('reports how much a successful clean-up freed, and who triggered it', async () => {
        getStatus.mockResolvedValue({
            data: status({
                build_cache_bytes: 0,
                last_prune: {
                    at: '2026-10-01T12:45:00+00:00',
                    source: 'auto',
                    ok: true,
                    freed_bytes: 5_307_000_000,
                    error: null,
                },
            }),
        });
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText(/Weekly automatic clean-up/)).toBeDefined());
        expect(screen.getByText(/freed 5\.3 GB/)).toBeDefined();
    });

    it('does not claim freed space when the size could not be read', async () => {
        getStatus.mockResolvedValue({
            data: status({
                last_prune: {
                    at: '2026-10-01T12:45:00+00:00',
                    source: 'manual',
                    ok: true,
                    freed_bytes: null,
                    error: null,
                },
            }),
        });
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText(/Cleared from this page/)).toBeDefined());
        expect(screen.queryByText(/freed/i)).toBeNull();
    });

    it('flags a nearly full disk using the server-reported threshold', async () => {
        getStatus.mockResolvedValue({
            data: status({ disk: { ...DISK, used_bytes: 130e9, percent: 89.7 } }),
        });
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText('Nearly full')).toBeDefined());
    });

    it('does not flag a healthy disk', async () => {
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText(/of 145 GB used/)).toBeDefined());
        expect(screen.queryByText('Nearly full')).toBeNull();
    });
});

describe('MaintenancePanel auth timing', () => {
    it('does not fetch until auth has settled', () => {
        // Before the interceptor is registered the request goes out without a
        // token and fails as an authorization error for a real superuser.
        useAuth.mockReturnValue({ user: null, loading: true });
        render(<MaintenancePanel />);
        expect(getStatus).not.toHaveBeenCalled();
    });

    it('does not fetch when nobody is signed in', () => {
        useAuth.mockReturnValue({ user: null, loading: false });
        render(<MaintenancePanel />);
        expect(getStatus).not.toHaveBeenCalled();
    });
});

describe('MaintenancePanel availability and errors', () => {
    it('explains instead of offering a button that cannot work', async () => {
        getStatus.mockResolvedValue({ data: status({ available: false }) });
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText(/isn.t available on this deployment/i)).toBeDefined());
        expect(screen.queryByRole('button', { name: /clear build cache/i })).toBeNull();
    });

    it('shows the server error, e.g. a non-superuser, instead of an empty page', async () => {
        getStatus.mockResolvedValue({ error: { detail: 'Access denied. Superuser privileges required.' } });
        render(<MaintenancePanel />);
        await waitFor(() => expect(screen.getByText(/Superuser privileges required/)).toBeDefined());
        expect(screen.queryByRole('button', { name: /clear build cache/i })).toBeNull();
    });

    it('disables the button while a request is already pending', async () => {
        getStatus.mockResolvedValue({ data: status({ prune_requested: true }) });
        render(<MaintenancePanel />);
        const button = await screen.findByRole('button', { name: /waiting for the server/i });
        expect((button as HTMLButtonElement).disabled).toBe(true);
    });
});

describe('MaintenancePanel request flow', () => {
    it('asks for confirmation before filing anything', async () => {
        render(<MaintenancePanel />);
        fireEvent.click(await screen.findByRole('button', { name: /clear build cache now/i }));
        await screen.findByText(/clear the whole build cache/i);
        // Opening the dialog is not the request.
        expect(requestPrune).not.toHaveBeenCalled();
    });

    it('files the request on confirm, and does not claim success on the click', async () => {
        requestPrune.mockResolvedValue({ data: { status: 'requested' } });
        render(<MaintenancePanel />);
        fireEvent.click(await screen.findByRole('button', { name: /clear build cache now/i }));
        fireEvent.click(await screen.findByRole('button', { name: /^clear it$/i }));

        await waitFor(() => expect(requestPrune).toHaveBeenCalledTimes(1));
        await screen.findByRole('button', { name: /waiting for the server/i });
        // The server has not acted yet, so there is nothing to celebrate.
        expect(toastSuccess).not.toHaveBeenCalled();
    });

    it('reports a refused request', async () => {
        requestPrune.mockResolvedValue({ error: { detail: 'Server maintenance is not available here' } });
        render(<MaintenancePanel />);
        fireEvent.click(await screen.findByRole('button', { name: /clear build cache now/i }));
        fireEvent.click(await screen.findByRole('button', { name: /^clear it$/i }));

        await waitFor(() => expect(toastError).toHaveBeenCalled());
        // Not stuck in "waiting" for something that was never filed.
        expect(screen.queryByRole('button', { name: /waiting for the server/i })).toBeNull();
    });
});
