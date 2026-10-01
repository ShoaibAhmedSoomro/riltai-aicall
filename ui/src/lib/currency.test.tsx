import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BILLING_CURRENCY, formatAmount, formatMoney, Money } from './currency';

describe('currency', () => {
    it('is dirham', () => {
        expect(BILLING_CURRENCY).toBe('AED');
        expect(formatMoney(12.5)).toBe('AED 12.50');
    });

    it('keeps small per-call figures visible instead of rounding them to 0.00', () => {
        expect(formatAmount(0.0123, { maxDecimals: 4 })).toBe('0.0123');
        expect(formatAmount(0.5, { maxDecimals: 4 })).toBe('0.50');
        expect(formatAmount(1234.5)).toBe('1,234.50');
    });

    it('draws the dirham sign before the amount', () => {
        render(<Money value={3.6725} maxDecimals={4} />);
        expect(screen.getByRole('img', { name: 'AED' })).toBeDefined();
        expect(screen.getByText(/3\.6725/)).toBeDefined();
    });
});
