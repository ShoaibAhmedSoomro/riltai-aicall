import {
    DEFAULT_SPEECH_NORMALIZATION,
    type PronunciationOverride,
    type SpeechNormalization,
    type WorkflowConfigurations,
} from '@/types/workflow-configurations';

/** Server limits (api/schemas/workflow_configurations.py). */
export const MAX_OVERRIDES = 200;
export const MAX_FROM = 100;
export const MAX_TO = 200;

export interface PronunciationForm {
    overrides: PronunciationOverride[];
    normalization: SpeechNormalization;
}

export const NEW_OVERRIDE: PronunciationOverride = {
    from_text: '',
    to_text: '',
    whole_word: true,
    match_case: false,
};

export function formFromConfig(config: WorkflowConfigurations): PronunciationForm {
    return {
        overrides: (config.pronunciation_overrides ?? []).map((o) => ({ ...NEW_OVERRIDE, ...o })),
        normalization: { ...DEFAULT_SPEECH_NORMALIZATION, ...config.speech_normalization },
    };
}

/** Rows with nothing in "Say this" are blank scaffolding, not rules. */
export function usableOverrides(overrides: PronunciationOverride[]): PronunciationOverride[] {
    return overrides
        .map((o) => ({ ...o, from_text: o.from_text.trim(), to_text: o.to_text.trim() }))
        .filter((o) => o.from_text !== '');
}

export function validateForm(form: PronunciationForm): string | null {
    const rows = usableOverrides(form.overrides);
    if (rows.length > MAX_OVERRIDES) return `At most ${MAX_OVERRIDES} pronunciations`;
    for (const row of rows) {
        if (row.from_text.length > MAX_FROM) return `"${row.from_text.slice(0, 20)}…" is too long (at most ${MAX_FROM} characters)`;
        if (row.to_text.length > MAX_TO) return `The replacement for "${row.from_text}" is too long (at most ${MAX_TO} characters)`;
    }
    const seen = new Set<string>();
    for (const row of rows) {
        const key = row.match_case ? row.from_text : row.from_text.toLowerCase();
        if (seen.has(key)) return `"${row.from_text}" appears twice. Only the first would apply`;
        seen.add(key);
    }
    const cutoff = form.normalization.number_digit_cutoff;
    if (cutoff !== null && (!Number.isInteger(cutoff) || cutoff < 0)) return 'The number cut-off must be a whole number, or empty';
    return null;
}

export function isDirty(a: PronunciationForm, b: PronunciationForm): boolean {
    return JSON.stringify(normalised(a)) !== JSON.stringify(normalised(b));
}

function normalised(form: PronunciationForm) {
    return { o: usableOverrides(form.overrides), n: form.normalization };
}

export function applyForm(config: WorkflowConfigurations, form: PronunciationForm): WorkflowConfigurations {
    return {
        ...config,
        pronunciation_overrides: usableOverrides(form.overrides),
        speech_normalization: form.normalization,
    };
}

type V2Override = { mode?: string; byok?: { mode?: string } } | undefined;

/**
 * Does this agent run on a speech-to-speech model? Then there is no text-to-speech
 * stage for these settings to act on, and the card must say so rather than let them
 * silently do nothing. A saved agent-level override decides; otherwise the
 * organization's configuration does.
 */
export function agentUsesRealtime(
    config: WorkflowConfigurations,
    organizationEffective: { is_realtime?: boolean } | null | undefined,
): boolean {
    const override = config.model_configuration_v2_override as V2Override;
    if (override) return override.mode === 'byok' && override.byok?.mode === 'realtime';
    return Boolean(organizationEffective?.is_realtime);
}
