import { describe, expect, it } from 'vitest';

import { formatElapsed } from './format';

const T0 = Date.parse('2026-10-02T10:00:00Z');

describe('formatElapsed', () => {
    it('minutes and seconds', () => {
        expect(formatElapsed('2026-10-02T10:00:00Z', T0 + 247_000)).toBe('4:07');
        expect(formatElapsed('2026-10-02T10:00:00Z', T0 + 5_000)).toBe('0:05');
    });
    it('hours when a call runs long', () => {
        expect(formatElapsed('2026-10-02T10:00:00Z', T0 + 3_729_000)).toBe('1:02:09');
    });
    it('never goes negative when this clock is behind the server', () => {
        expect(formatElapsed('2026-10-02T10:00:00Z', T0 - 60_000)).toBe('0:00');
    });
    it('copes with a bad date', () => {
        expect(formatElapsed('not a date')).toBe('–');
    });
});
