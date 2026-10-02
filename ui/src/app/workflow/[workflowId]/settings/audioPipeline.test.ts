import { describe, expect, it } from 'vitest';

import { resolveWorkflowConfigurations } from '@/types/workflow-configurations';

import { applyForm, type AudioPipelineForm, formFromConfig, isFormDirty, validateAudioForm } from './audioPipeline';

const base = () => resolveWorkflowConfigurations({});

describe('formFromConfig', () => {
    it('defaults to what runs today', () => {
        expect(formFromConfig(base())).toEqual({
            denoising: 'none',
            dtmfEnabled: true,
            dtmfTimeout: '2',
            ivrEnabled: false,
            fallbackEnabled: false,
            fallbackProvider: 'elevenlabs',
            fallbackApiKey: '',
            fallbackVoice: '',
        });
    });

    it('reads what was saved', () => {
        const form = formFromConfig({
            ...base(),
            denoising_mode: 'rnnoise',
            dtmf_input_enabled: false,
            dtmf_input_timeout_secs: 4,
            ivr_detection: { enabled: true },
            tts_fallback: { provider: 'deepgram', api_key: 'sk-****1234', voice: 'aura' },
        } as never);
        expect(form).toMatchObject({
            denoising: 'rnnoise', dtmfEnabled: false, dtmfTimeout: '4', ivrEnabled: true,
            fallbackEnabled: true, fallbackProvider: 'deepgram', fallbackApiKey: 'sk-****1234', fallbackVoice: 'aura',
        });
    });
});

describe('validateAudioForm', () => {
    const form = (over: Partial<AudioPipelineForm> = {}): AudioPipelineForm => ({ ...formFromConfig(base()), ...over });

    it('accepts the defaults', () => {
        expect(validateAudioForm(form())).toBeNull();
    });

    it('bounds the keypad wait only while the keypad is on', () => {
        expect(validateAudioForm(form({ dtmfTimeout: '0.1' }))).toMatch(/0.5 and 10/);
        expect(validateAudioForm(form({ dtmfTimeout: '' }))).not.toBeNull();
        expect(validateAudioForm(form({ dtmfTimeout: '99' }))).not.toBeNull();
        expect(validateAudioForm(form({ dtmfEnabled: false, dtmfTimeout: '99' }))).toBeNull();
    });
});

describe('applyForm', () => {
    const form = (over: Partial<AudioPipelineForm> = {}): AudioPipelineForm => ({ ...formFromConfig(base()), ...over });

    it('leaves every other setting alone', () => {
        const config = { ...base(), max_call_duration: 600, dictionary: 'acme' };
        const out = applyForm(config, form({ denoising: 'rnnoise' }));
        expect(out.max_call_duration).toBe(600);
        expect(out.dictionary).toBe('acme');
        expect(out.denoising_mode).toBe('rnnoise');
    });

    it('turns the phone-menu hang-up on without losing its other keys', () => {
        const out = applyForm({ ...base(), ivr_detection: { enabled: false, note: 'x' } } as never, form({ ivrEnabled: true }));
        expect(out.ivr_detection).toEqual({ enabled: true, note: 'x' });
    });

    it('stores a backup voice only with the fields that were filled in', () => {
        const out = applyForm(base(), form({ fallbackEnabled: true, fallbackProvider: 'cartesia', fallbackApiKey: 'k', fallbackVoice: '  ' }));
        expect(out.tts_fallback).toEqual({ provider: 'cartesia', api_key: 'k' });
    });

    it('clears the backup voice explicitly so the server removes it', () => {
        const out = applyForm({ ...base(), tts_fallback: { provider: 'deepgram' } } as never, form({ fallbackEnabled: false }));
        expect(out.tts_fallback).toBeNull();
    });

    it('never stores a nonsense timeout', () => {
        expect(applyForm(base(), form({ dtmfTimeout: 'soon' })).dtmf_input_timeout_secs).toBe(2);
    });
});

describe('isFormDirty', () => {
    it('is false for an untouched form and true after any change', () => {
        const a = formFromConfig(base());
        expect(isFormDirty(a, { ...a })).toBe(false);
        expect(isFormDirty(a, { ...a, ivrEnabled: true })).toBe(true);
        expect(isFormDirty(a, { ...a, fallbackApiKey: 'x' })).toBe(true);
    });
});
