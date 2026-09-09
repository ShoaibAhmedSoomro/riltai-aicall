import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Call pricing, where the wrong empty state is a false financial claim.
 *
 * Self-hosted deployments never reach the pricing service, so without a local
 * rate every cost figure in the product is null. The fix is a price per minute
 * — and the trap is what to show before one is set. "$0.00" says the calls were
 * free. Only "not set" says nobody has priced them.
 *
 * The other two: on the hosted plan this value is ignored entirely, so an
 * editable box there is a control that does nothing; and a failed load must not
 * render as "no price set", because that is a statement rather than a failure.
 */

const getRateCard = vi.fn();
const saveRateCard = vi.fn();
const useAuth = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('@/client/sdk.gen', () => ({
    getUsageRateCardApiV1OrganizationsUsageRateCardGet: (...a: unknown[]) => getRateCard(...a),
    saveUsageRateCardApiV1OrganizationsUsageRateCardPut: (...a: unknown[]) => saveRateCard(...a),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => useAuth() }));
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) } }));

import { UsageRateCardSection } from './UsageRateCardSection';

const UNSET = { configured: false, applies_to_this_deployment: true };
const SET = {
    configured: true,
    price_per_minute_usd: 0.05,
    currency: 'USD',
    applies_to_this_deployment: true,
};

beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1 }, loading: false });
    getRateCard.mockResolvedValue({ data: UNSET });
    saveRateCard.mockResolvedValue({ data: SET });
});

describe('UsageRateCardSection', () => {
    it('says no price is set rather than showing a zero', async () => {
        render(<UsageRateCardSection />);
        await waitFor(() => expect(screen.getByText(/No price set/i)).toBeDefined());
        // The distinction the whole feature rests on.
        expect(screen.getByText(/zero would say your calls were free/i)).toBeDefined();
        // And the input is genuinely blank rather than prefilled with 0,
        // which would turn one stray click on Save into "calls are free".
        const input = screen.getByLabelText(/Price per minute/i) as HTMLInputElement;
        expect(input.value).toBe("");
    });

    it('shows the configured rate', async () => {
        getRateCard.mockResolvedValue({ data: SET });
        render(<UsageRateCardSection />);
        await waitFor(() => expect(screen.getByText(/\$0\.05\/min/)).toBeDefined());
    });

    it('prefills the input so saving is an edit, not a re-entry', async () => {
        getRateCard.mockResolvedValue({ data: SET });
        render(<UsageRateCardSection />);
        const input = (await screen.findByLabelText(/Price per minute/i)) as HTMLInputElement;
        expect(input.value).toBe('0.05');
    });

    it('sends the entered rate', async () => {
        render(<UsageRateCardSection />);
        const input = await screen.findByLabelText(/Price per minute/i);
        fireEvent.change(input, { target: { value: '0.12' } });
        fireEvent.click(screen.getByRole('button', { name: /Save rate/i }));
        await waitFor(() => expect(saveRateCard).toHaveBeenCalled());
        expect(saveRateCard.mock.calls[0][0].body.price_per_minute_usd).toBe(0.12);
    });

    it('refuses a zero or negative rate before calling the server', async () => {
        // 0 would price every call at nothing, which is exactly the false claim
        // the unset state exists to avoid.
        render(<UsageRateCardSection />);
        const input = await screen.findByLabelText(/Price per minute/i);
        for (const bad of ['0', '-1']) {
            fireEvent.change(input, { target: { value: bad } });
            fireEvent.click(screen.getByRole('button', { name: /Save rate/i }));
        }
        await waitFor(() => expect(toastError).toHaveBeenCalled());
        expect(saveRateCard).not.toHaveBeenCalled();
    });

    it('offers no editable rate on the hosted plan', async () => {
        // There, calls are priced upstream and this value is ignored — a box
        // that saves a number nothing reads is worse than no box.
        getRateCard.mockResolvedValue({
            data: { configured: false, applies_to_this_deployment: false },
        });
        render(<UsageRateCardSection />);
        await waitFor(() =>
            expect(screen.getByText(/priced by AICall/i)).toBeDefined(),
        );
        expect(screen.queryByLabelText(/Price per minute/i)).toBeNull();
    });

    it('shows a failed load as a failure, not as "no price set"', async () => {
        getRateCard.mockResolvedValue({ error: { detail: 'Boom' } });
        render(<UsageRateCardSection />);
        await waitFor(() => expect(screen.getByText('Boom')).toBeDefined());
        expect(screen.queryByText(/No price set/i)).toBeNull();
    });

    it('tells a member it is admin-only instead of failing generically', async () => {
        saveRateCard.mockResolvedValue({
            error: { detail: 'Access denied.' },
            response: { status: 403 },
        });
        render(<UsageRateCardSection />);
        const input = await screen.findByLabelText(/Price per minute/i);
        fireEvent.change(input, { target: { value: '0.12' } });
        fireEvent.click(screen.getByRole('button', { name: /Save rate/i }));
        await waitFor(() =>
            expect(toastError).toHaveBeenCalledWith('Only an admin can change the rate.'),
        );
        await waitFor(() =>
            expect(screen.getByText(/Only an admin can change the rate/i)).toBeDefined(),
        );
    });

    it('says a change is not retroactive', async () => {
        // Re-pricing completed calls would rewrite reports that were already
        // read, so the copy has to set that expectation up front.
        getRateCard.mockResolvedValue({ data: SET });
        render(<UsageRateCardSection />);
        await waitFor(() =>
            expect(screen.getByText(/does not change retroactively/i)).toBeDefined(),
        );
    });
});
