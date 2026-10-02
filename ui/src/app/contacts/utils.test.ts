import { describe, expect, it } from 'vitest';

import {
    contactName,
    fieldNameFromHeader,
    guessColumns,
    importSummary,
    parsePhoneList,
    validateFieldName,
} from './utils';

describe('guessColumns', () => {
    it('finds the obvious columns', () => {
        expect(guessColumns(['First Name', 'Last Name', 'Mobile', 'E-mail', 'Employer'])).toEqual({
            phone_number: 'Mobile',
            first_name: 'First Name',
            last_name: 'Last Name',
            email: 'E-mail',
        });
    });

    it('does not read an email column as the phone, or use one column twice', () => {
        const g = guessColumns(['Email', 'Phone Number']);
        expect(g.email).toBe('Email');
        expect(g.phone_number).toBe('Phone Number');
    });

    it('guesses nothing it is unsure of', () => {
        expect(guessColumns(['Company', 'City'])).toEqual({
            phone_number: null,
            first_name: null,
            last_name: null,
            email: null,
        });
    });
});

describe('fieldNameFromHeader', () => {
    it('makes a header into a usable variable name', () => {
        expect(fieldNameFromHeader('Employer Name')).toBe('employer_name');
        expect(fieldNameFromHeader('  Plan / Tier! ')).toBe('plan_tier');
    });

    it('never produces a name the API would refuse', () => {
        for (const header of ['123 abc', '###', '', 'phone_number', 'Email', 'a'.repeat(100)]) {
            const name = fieldNameFromHeader(header);
            expect(validateFieldName(name)).toBeNull();
        }
    });

    it('keeps two columns apart when they would collide', () => {
        const first = fieldNameFromHeader('Company');
        const second = fieldNameFromHeader('company', [first]);
        expect(first).toBe('company');
        expect(second).toBe('company_2');
    });
});

describe('validateFieldName', () => {
    it('explains each refusal', () => {
        expect(validateFieldName('9lives')).toMatch(/letters/);
        expect(validateFieldName('email')).toMatch(/standard/);
        expect(validateFieldName('plan', ['plan'])).toMatch(/already/);
        expect(validateFieldName('plan')).toBeNull();
    });
});

describe('parsePhoneList', () => {
    it('splits on lines, commas and semicolons and drops blanks', () => {
        expect(parsePhoneList('+971501111111\n\n+971502222222, +971503333333;  ,+971504444444\r\n')).toEqual([
            '+971501111111',
            '+971502222222',
            '+971503333333',
            '+971504444444',
        ]);
    });
});

describe('contactName', () => {
    it('joins what exists and is null when nothing does', () => {
        expect(contactName({ first_name: 'Ana', last_name: 'Lee' })).toBe('Ana Lee');
        expect(contactName({ first_name: 'Ana', last_name: null })).toBe('Ana');
        expect(contactName({ first_name: null, last_name: null })).toBeNull();
    });
});

describe('importSummary', () => {
    it('reports only what happened', () => {
        expect(importSummary({ created_count: 1200, updated_count: 0, skipped_count: 0, invalid_count: 0 })).toBe('1,200 new');
        expect(importSummary({ created_count: 5, updated_count: 2, skipped_count: 3, invalid_count: 1 })).toBe(
            '5 new · 2 updated · 3 already existed · 1 rejected',
        );
    });

    it('speaks about the do-not-call list when that is what was imported', () => {
        expect(importSummary({ created_count: 9, updated_count: 0, skipped_count: 1, invalid_count: 0, mode: 'suppression' })).toBe(
            '9 added to the do-not-call list · 1 already on the list',
        );
    });
});
