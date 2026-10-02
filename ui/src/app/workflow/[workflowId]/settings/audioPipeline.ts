import type { WorkflowConfigurations } from '@/types/workflow-configurations';

/**
 * The "Audio & Calls" settings as typed in the form, and the rules for turning them
 * into the stored configuration. Pure, so the rules are tested without the page.
 *
 * Every default equals today's behaviour: no denoising, keypad on with a 2 second
 * idle flush, no phone-menu hang-up, no backup voice.
 */
export type DenoisingMode = 'none' | 'rnnoise';

export interface AudioPipelineForm {
    denoising: DenoisingMode;
    dtmfEnabled: boolean;
    dtmfTimeout: string;
    ivrEnabled: boolean;
    fallbackEnabled: boolean;
    fallbackProvider: string;
    fallbackApiKey: string;
    fallbackVoice: string;
}

/** Providers whose voice needs only a key (and optionally a voice) to work as a backup. */
export const BACKUP_VOICE_PROVIDERS = [
    { value: 'elevenlabs', label: 'ElevenLabs' },
    { value: 'deepgram', label: 'Deepgram' },
    { value: 'openai', label: 'OpenAI' },
    { value: 'cartesia', label: 'Cartesia' },
] as const;

export const DEFAULT_DTMF_TIMEOUT_SECS = 2;
const DTMF_MIN = 0.5;
const DTMF_MAX = 10;

type Fallback = { provider?: string; api_key?: string; voice?: string } | null | undefined;

export function formFromConfig(config: WorkflowConfigurations): AudioPipelineForm {
    const fb = config.tts_fallback as Fallback;
    return {
        denoising: config.denoising_mode === 'rnnoise' ? 'rnnoise' : 'none',
        dtmfEnabled: config.dtmf_input_enabled !== false,
        dtmfTimeout: String(Number(config.dtmf_input_timeout_secs) || DEFAULT_DTMF_TIMEOUT_SECS),
        ivrEnabled: Boolean((config.ivr_detection as { enabled?: boolean } | undefined)?.enabled),
        fallbackEnabled: Boolean(fb && fb.provider),
        fallbackProvider: fb?.provider || BACKUP_VOICE_PROVIDERS[0].value,
        fallbackApiKey: fb?.api_key || '',
        fallbackVoice: fb?.voice || '',
    };
}

/** What is wrong with the form, in words the person can act on, or null. */
export function validateAudioForm(form: AudioPipelineForm): string | null {
    const timeout = Number(form.dtmfTimeout);
    if (form.dtmfEnabled && (form.dtmfTimeout.trim() === '' || Number.isNaN(timeout) || timeout < DTMF_MIN || timeout > DTMF_MAX)) {
        return `Wait for more keys between ${DTMF_MIN} and ${DTMF_MAX} seconds`;
    }
    if (form.fallbackEnabled && !form.fallbackProvider) return 'Choose a provider for the backup voice';
    return null;
}

export function applyForm(config: WorkflowConfigurations, form: AudioPipelineForm): WorkflowConfigurations {
    const timeout = Number(form.dtmfTimeout);
    return {
        ...config,
        denoising_mode: form.denoising,
        dtmf_input_enabled: form.dtmfEnabled,
        // Keep the stored value when the keypad is off and the box is not meaningful.
        dtmf_input_timeout_secs: Number.isNaN(timeout) ? DEFAULT_DTMF_TIMEOUT_SECS : timeout,
        ivr_detection: { ...(config.ivr_detection as object | undefined), enabled: form.ivrEnabled },
        // null clears it on the server; an omitted key would leave the stored one.
        tts_fallback: (form.fallbackEnabled
            ? {
                  provider: form.fallbackProvider,
                  ...(form.fallbackApiKey ? { api_key: form.fallbackApiKey } : {}),
                  ...(form.fallbackVoice.trim() ? { voice: form.fallbackVoice.trim() } : {}),
              }
            : null) as WorkflowConfigurations['tts_fallback'],
    };
}

export function isFormDirty(a: AudioPipelineForm, b: AudioPipelineForm): boolean {
    const keys = Object.keys(a) as (keyof AudioPipelineForm)[];
    return keys.some((k) => a[k] !== b[k]);
}
