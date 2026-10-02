import { describe, expect, it } from 'vitest';

import { MAX_PRESS_DIGITS, validatePressDigits } from './pressDigit';

describe('validatePressDigits', () => {
    it.each(['1', '0', '123#', '*9#', '  5  '])('accepts %j', (digits) => {
        expect(validatePressDigits(digits)).toBeNull();
    });

    it('asks for keys when there are none', () => {
        expect(validatePressDigits('')).toMatch(/enter the keys/i);
        expect(validatePressDigits('   ')).toMatch(/enter the keys/i);
    });

    it('names the character that is not a key', () => {
        expect(validatePressDigits('12x')).toMatch(/"x" is not a phone key/);
        expect(validatePressDigits('one')).toMatch(/not a phone key/);
    });

    it('explains a space instead of calling it a key', () => {
        expect(validatePressDigits('1 2')).toMatch(/remove the spaces/i);
    });

    it('stops at the server limit', () => {
        expect(validatePressDigits('1'.repeat(MAX_PRESS_DIGITS))).toBeNull();
        expect(validatePressDigits('1'.repeat(MAX_PRESS_DIGITS + 1))).toMatch(/at most/i);
    });
});
