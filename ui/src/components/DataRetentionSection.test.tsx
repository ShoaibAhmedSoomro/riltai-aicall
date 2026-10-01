import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getPrefs = vi.fn();
const useAuth = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    getPreferencesApiV1OrganizationsPreferencesGet: (...a: unknown[]) => getPrefs(...a),
    savePreferencesApiV1OrganizationsPreferencesPut: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { DataRetentionSection } from './DataRetentionSection';

beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1 }, loading: false });
});

describe('DataRetentionSection', () => {
    it('defaults to keeping everything forever, and says nothing is deleted unless a period is set', async () => {
        getPrefs.mockResolvedValue({ data: {} });
        render(<DataRetentionSection />);
        await waitFor(() => expect(screen.getByText(/Keep forever \(default\)/)).toBeDefined());
        expect(screen.getByText(/Nothing is deleted unless a period is set/i)).toBeDefined();
        expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
    });

    it('shows the saved window and mode', async () => {
        getPrefs.mockResolvedValue({ data: { data_retention_days: 90, default_storage_mode: 'except_pii' } });
        render(<DataRetentionSection />);
        await waitFor(() => expect(screen.getByText('90 days')).toBeDefined());
        expect(screen.getByText(/except personal details/i)).toBeDefined();
    });

    it('a failed load is an error, not an empty "keep forever"', async () => {
        getPrefs.mockResolvedValue({ error: { detail: 'boom' } });
        render(<DataRetentionSection />);
        await waitFor(() => expect(screen.getByText(/boom|Failed to load/i)).toBeDefined());
        expect(screen.queryByText(/Keep forever/)).toBeNull();
    });
});
