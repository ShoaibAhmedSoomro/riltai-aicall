import { describe, expect, it } from 'vitest';

import type { AlertMetricResponse, AlertRuleResponse } from '@/client/types.gen';

import { EMPTY_RULE_FORM, formToRequest, parseRecipients, ruleSummary, ruleToForm, validateRuleForm } from './alertForm';

const metric = (over: Partial<AlertMetricResponse>): AlertMetricResponse => ({
    key: 'm', label: 'Thing', description: '', trigger: 'run_completed', value_type: 'flag', ...over,
});
const form = (over = {}) => ({ ...EMPTY_RULE_FORM, name: 'Rule', metric: 'm', ...over });

describe('validateRuleForm', () => {
    it('needs a name and a metric', () => {
        expect(validateRuleForm(form({ name: ' ' }), metric({}))).toMatch(/name/i);
        expect(validateRuleForm(form(), undefined)).toMatch(/what to watch/i);
    });

    it('a flag metric needs nothing else', () => {
        expect(validateRuleForm(form(), metric({ value_type: 'flag' }))).toBeNull();
    });

    it('a number metric needs a number; a text metric needs a value', () => {
        const num = metric({ value_type: 'number', label: 'Call duration' });
        expect(validateRuleForm(form({ threshold: '' }), num)).toMatch(/call duration/i);
        expect(validateRuleForm(form({ threshold: 'abc' }), num)).not.toBeNull();
        expect(validateRuleForm(form({ threshold: '0' }), num)).toBeNull();
        expect(validateRuleForm(form({ matchValue: ' ' }), metric({ value_type: 'text' }))).not.toBeNull();
    });

    it('a window metric needs a sensible period', () => {
        const win = metric({ trigger: 'window', value_type: 'number' });
        expect(validateRuleForm(form({ threshold: '1', windowMinutes: '2' }), win)).toMatch(/5 and 1440/);
        expect(validateRuleForm(form({ threshold: '1', windowMinutes: '60' }), win)).toBeNull();
    });

    it('bounds the wait between alerts', () => {
        expect(validateRuleForm(form({ cooldownMinutes: '0' }), metric({}))).not.toBeNull();
        expect(validateRuleForm(form({ cooldownMinutes: '99999' }), metric({}))).not.toBeNull();
    });
});

describe('formToRequest', () => {
    it('sends only the fields the metric uses', () => {
        const req = formToRequest(form({ threshold: '5', matchValue: 'x', windowMinutes: '30' }), metric({ value_type: 'number' }));
        expect(req).toMatchObject({ threshold: 5, match_value: null, window_minutes: null });
        const win = formToRequest(form({ threshold: '5', windowMinutes: '30' }), metric({ trigger: 'window', value_type: 'number' }));
        expect(win.window_minutes).toBe(30);
    });

    it('empty scope means every agent', () => {
        expect(formToRequest(form({ scopeWorkflowId: '' }), metric({})).scope_workflow_id).toBeNull();
        expect(formToRequest(form({ scopeWorkflowId: '7' }), metric({})).scope_workflow_id).toBe(7);
    });
});

const rule = (over = {}): AlertRuleResponse => ({
    rule_uuid: 'r', name: 'R', is_active: true, trigger: 'window', metric: 'm', comparator: 'gt',
    threshold: 20, window_minutes: 30, severity: 'high', cooldown_minutes: 60, channel_uuids: ['c1'], ...over,
}) as AlertRuleResponse;

describe('rules as text and as a form', () => {
    it('reads as a sentence', () => {
        const m = metric({ label: 'Failure rate', value_type: 'number', unit: '%', trigger: 'window' });
        expect(ruleSummary(rule(), m)).toBe('Failure rate is above 20 % over 30 min');
        expect(ruleSummary(rule(), metric({ label: 'A call failed' }))).toBe('A call failed');
        expect(ruleSummary(rule({ match_value: 'busy' }), metric({ label: 'Outcome is', value_type: 'text' }))).toBe('Outcome is: busy');
    });

    it('survives a metric the page does not know', () => {
        expect(ruleSummary(rule({ metric: 'gone' }), undefined)).toBe('gone');
    });

    it('round-trips through the form', () => {
        const f = ruleToForm(rule({ scope_workflow_id: 9 }));
        expect(f).toMatchObject({ threshold: '20', windowMinutes: '30', scopeWorkflowId: '9', channelUuids: ['c1'] });
    });
});

describe('parseRecipients', () => {
    it('splits on commas, spaces and lines, and drops duplicates', () => {
        expect(parseRecipients('a@x.co, b@x.co\nA@x.co;c@x.co  ')).toEqual(['a@x.co', 'b@x.co', 'c@x.co']);
        expect(parseRecipients('  ')).toEqual([]);
    });
});
