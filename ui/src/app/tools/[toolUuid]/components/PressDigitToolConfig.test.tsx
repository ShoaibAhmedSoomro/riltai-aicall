import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PressDigitToolConfig } from './PressDigitToolConfig';

function setup(digits: string) {
    const onDigitsChange = vi.fn();
    const onUrgentChange = vi.fn();
    render(
        <PressDigitToolConfig
            name="Press 1"
            onNameChange={vi.fn()}
            description="d"
            onDescriptionChange={vi.fn()}
            digits={digits}
            onDigitsChange={onDigitsChange}
            urgent={false}
            onUrgentChange={onUrgentChange}
        />,
    );
    return { onDigitsChange, onUrgentChange };
}

describe('PressDigitToolConfig', () => {
    it('shows no complaint for valid keys', () => {
        setup('123#');
        expect(screen.queryByRole('alert')).toBeNull();
        expect(screen.getByLabelText('Keys to press').getAttribute('aria-invalid')).toBe('false');
    });

    it('says what is wrong with an invalid entry, and marks the field invalid', () => {
        setup('12x');
        expect(screen.getByRole('alert').textContent).toMatch(/"x" is not a phone key/);
        expect(screen.getByLabelText('Keys to press').getAttribute('aria-invalid')).toBe('true');
    });

    it('does not scold an empty field before the person has typed', () => {
        setup('');
        expect(screen.queryByRole('alert')).toBeNull();
    });

    it('reports typing and the immediate switch', () => {
        const { onDigitsChange, onUrgentChange } = setup('1');
        fireEvent.change(screen.getByLabelText('Keys to press'), { target: { value: '12' } });
        expect(onDigitsChange).toHaveBeenCalledWith('12');
        fireEvent.click(screen.getByRole('switch'));
        expect(onUrgentChange).toHaveBeenCalledWith(true);
    });
});
