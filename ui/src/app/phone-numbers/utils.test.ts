import { describe, expect, it } from 'vitest';

import { matchesPhoneNumber } from './utils';

const number = {
    address: '+971 50 123 4567',
    address_normalized: '+971501234567',
    label: 'Support line',
    inbound_workflow_name: 'Support Agent',
    telephony_configuration_name: 'Dubai Twilio',
    telephony_provider: 'twilio',
};

describe('matchesPhoneNumber', () => {
    it('everything matches an empty search', () => {
        expect(matchesPhoneNumber(number, '')).toBe(true);
        expect(matchesPhoneNumber(number, '   ')).toBe(true);
    });

    it('finds a number however the digits are written', () => {
        expect(matchesPhoneNumber(number, '501234567')).toBe(true);
        expect(matchesPhoneNumber(number, '+971 50')).toBe(true);
        expect(matchesPhoneNumber(number, '050-123')).toBe(false); // a leading 0 is not part of the stored number
        expect(matchesPhoneNumber(number, '5012')).toBe(true);
    });

    it('finds by label, agent or provider, ignoring case', () => {
        expect(matchesPhoneNumber(number, 'SUPPORT')).toBe(true);
        expect(matchesPhoneNumber(number, 'dubai')).toBe(true);
        expect(matchesPhoneNumber(number, 'twilio')).toBe(true);
    });

    it('does not match something that is not there', () => {
        expect(matchesPhoneNumber(number, 'sales')).toBe(false);
        expect(matchesPhoneNumber(number, '999')).toBe(false);
    });

    it('copes with a number that has no label or agent', () => {
        expect(matchesPhoneNumber({ ...number, label: null, inbound_workflow_name: null }, 'agent')).toBe(false);
    });
});
