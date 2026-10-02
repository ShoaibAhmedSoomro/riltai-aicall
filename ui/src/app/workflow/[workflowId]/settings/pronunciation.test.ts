import { describe, expect, it } from 'vitest';

import { resolveWorkflowConfigurations } from '@/types/workflow-configurations';

import {
    agentUsesRealtime,
    applyForm,
    formFromConfig,
    isDirty,
    MAX_FROM,
    MAX_OVERRIDES,
    NEW_OVERRIDE,
    usableOverrides,
    validateForm,
} from './pronunciation';

const base = () => resolveWorkflowConfigurations({});
const row = (from_text: string, to_text = 'x', over = {}) => ({ ...NEW_OVERRIDE, from_text, to_text, ...over });

describe('the form from a configuration', () => {
    it('starts empty and off', () => {
        const form = formFromConfig(base());
        expect(form.overrides).toEqual([]);
        expect(form.normalization.enabled).toBe(false);
    });

    it('reads what was saved, filling flags an older row lacks', () => {
        const form = formFromConfig({ ...base(), pronunciation_overrides: [{ from_text: 'AED', to_text: 'dirhams' }] } as never);
        expect(form.overrides[0]).toEqual({ from_text: 'AED', to_text: 'dirhams', whole_word: true, match_case: false });
    });
});

describe('usableOverrides', () => {
    it('drops blank rows and trims the rest', () => {
        expect(usableOverrides([row('  '), row(' AED ', ' dirhams ')])).toEqual([row('AED', 'dirhams')]);
    });
});

describe('validateForm', () => {
    const form = (overrides: ReturnType<typeof row>[]) => ({ ...formFromConfig(base()), overrides });

    it('accepts none, and accepts blank scaffolding', () => {
        expect(validateForm(form([]))).toBeNull();
        expect(validateForm(form([row('')]))).toBeNull();
    });

    it('stops a duplicate, which would silently never apply', () => {
        expect(validateForm(form([row('AED'), row('aed')]))).toMatch(/appears twice/);
        expect(validateForm(form([row('AED', 'x', { match_case: true }), row('aed', 'y', { match_case: true })]))).toBeNull();
    });

    it('stops text the server would refuse', () => {
        expect(validateForm(form([row('x'.repeat(MAX_FROM + 1))]))).toMatch(/too long/);
        expect(validateForm(form([row('a', 'y'.repeat(201))]))).toMatch(/too long/);
        expect(validateForm(form(Array.from({ length: MAX_OVERRIDES + 1 }, (_, i) => row(`w${i}`))))).toMatch(/At most/);
    });

    it('checks the number cut-off', () => {
        const f = formFromConfig(base());
        expect(validateForm({ ...f, normalization: { ...f.normalization, number_digit_cutoff: -1 } })).toMatch(/whole number/);
        expect(validateForm({ ...f, normalization: { ...f.normalization, number_digit_cutoff: null } })).toBeNull();
    });
});

describe('saving', () => {
    it('writes only usable rows and leaves other settings alone', () => {
        const config = { ...base(), max_call_duration: 600 };
        const out = applyForm(config, { ...formFromConfig(config), overrides: [row(''), row('AED', 'dirhams')] });
        expect(out.pronunciation_overrides).toEqual([row('AED', 'dirhams')]);
        expect(out.max_call_duration).toBe(600);
    });

    it('is not dirty for an untouched form or a blank added row', () => {
        const form = formFromConfig(base());
        expect(isDirty(form, { ...form })).toBe(false);
        expect(isDirty(form, { ...form, overrides: [row('')] })).toBe(false);
        expect(isDirty(form, { ...form, overrides: [row('AED')] })).toBe(true);
        expect(isDirty(form, { ...form, normalization: { ...form.normalization, enabled: true } })).toBe(true);
    });
});

describe('agentUsesRealtime', () => {
    it('follows an agent-level override when there is one', () => {
        const realtime = { ...base(), model_configuration_v2_override: { mode: 'byok', byok: { mode: 'realtime' } } } as never;
        const pipeline = { ...base(), model_configuration_v2_override: { mode: 'byok', byok: { mode: 'pipeline' } } } as never;
        expect(agentUsesRealtime(realtime, { is_realtime: false })).toBe(true);
        expect(agentUsesRealtime(pipeline, { is_realtime: true })).toBe(false);
    });

    it('otherwise follows the organization', () => {
        expect(agentUsesRealtime(base(), { is_realtime: true })).toBe(true);
        expect(agentUsesRealtime(base(), { is_realtime: false })).toBe(false);
        expect(agentUsesRealtime(base(), null)).toBe(false);
    });
});
