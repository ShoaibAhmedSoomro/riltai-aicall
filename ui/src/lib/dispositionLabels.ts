/**
 * Human labels and outcome tone for call disposition codes.
 *
 * The API returns RAW codes, never display text: the daily report projects
 * `gathered_context->'mapped_call_disposition'` straight out of Postgres and
 * coalesces a missing key to the literal string "UNKNOWN"
 * (api/db/reports_client.py). So the UI is the only place these become readable.
 *
 * The known set is SYSTEM_DISPOSITION_CODES from
 * api/services/workflow/disposition_codes.py: the 14 EndTaskReason values plus 5
 * telephony values. An organization can also define its OWN codes, and the LLM
 * can emit free text, so the set is NOT closed — anything unmapped falls through
 * to a title-cased version of the code rather than being hidden or relabelled.
 *
 * Two sentinels look alike and are genuinely different values:
 *   "unknown"  the EndTaskReason enum member, i.e. the run ended for no known reason
 *   "UNKNOWN"  the SQL coalesce default, i.e. the run recorded no disposition at all
 * Both can appear as separate slices, so both are mapped, differently.
 */

/** Whether an outcome is a win, a neutral end, or a problem. Drives colour. */
export type DispositionTone = 'positive' | 'neutral' | 'negative';

interface DispositionMeta {
    label: string;
    tone: DispositionTone;
}

const DISPOSITIONS: Record<string, DispositionMeta> = {
    // ── EndTaskReason (pipecat/src/pipecat/utils/enums.py)
    user_qualified: { label: 'Qualified', tone: 'positive' },
    call_transferred: { label: 'Transferred', tone: 'positive' },
    transfer_call: { label: 'Transfer requested', tone: 'positive' },
    end_call_tool: { label: 'Ended by agent', tone: 'neutral' },
    user_hangup: { label: 'Caller hung up', tone: 'neutral' },
    user_disqualified: { label: 'Disqualified', tone: 'neutral' },
    call_duration_exceeded: { label: 'Max duration reached', tone: 'neutral' },
    user_idle_max_duration_exceeded: { label: 'Caller went silent', tone: 'neutral' },
    voicemail_detected: { label: 'Voicemail', tone: 'neutral' },
    system_cancelled: { label: 'Cancelled', tone: 'neutral' },
    unknown: { label: 'No reason recorded', tone: 'neutral' },
    system_connect_error: { label: 'Connection error', tone: 'negative' },
    pipeline_error: { label: 'Pipeline error', tone: 'negative' },
    unexpected_error: { label: 'Unexpected error', tone: 'negative' },

    // ── Telephony provider outcomes (api/enums.py)
    'no-answer': { label: 'No answer', tone: 'neutral' },
    busy: { label: 'Busy', tone: 'neutral' },
    canceled: { label: 'Canceled', tone: 'neutral' },
    failed: { label: 'Failed', tone: 'negative' },
    error: { label: 'Error', tone: 'negative' },

    // ── Sentinels that are not enum members
    // The SQL coalesce default: the run stored no disposition at all.
    UNKNOWN: { label: 'Not recorded', tone: 'neutral' },
    // The report's synthetic tail bucket: everything outside the top five.
    Other: { label: 'Other', tone: 'neutral' },
    // `->` on an explicit JSON null yields JSON null, not SQL NULL, so coalesce
    // does not fire and the string "null" arrives as a real label.
    null: { label: 'Not recorded', tone: 'neutral' },
};

/** Title-case an unmapped code: "some_custom_code" -> "Some custom code". */
function humanise(code: string): string {
    const words = code.replace(/[_-]+/g, ' ').trim();
    if (!words) return 'Not recorded';
    return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
}

export function dispositionLabel(code: string): string {
    return DISPOSITIONS[code]?.label ?? humanise(code);
}

export function dispositionTone(code: string): DispositionTone {
    return DISPOSITIONS[code]?.tone ?? 'neutral';
}

/**
 * Chart colour for a disposition, as a CSS custom property reference.
 *
 * Returns a var() string rather than a hex so the slice follows the app's
 * palette in both themes. --chart-* is the cool categorical ramp defined in
 * globals.css; --destructive carries the app's danger hue.
 */
export function dispositionColor(code: string): string {
    const tone = dispositionTone(code);
    if (tone === 'negative') return 'var(--destructive)';
    if (tone === 'positive') return 'var(--chart-2)';
    return 'var(--chart-1)';
}

/**
 * Distinct colours for a set of codes, keeping negatives red and positives
 * teal while spreading the neutral majority across the remaining ramp so
 * adjacent slices stay separable.
 */
export function dispositionPalette(codes: string[]): Record<string, string> {
    const NEUTRAL_RAMP = ['var(--chart-1)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)'];
    const out: Record<string, string> = {};
    let neutralIndex = 0;
    for (const code of codes) {
        const tone = dispositionTone(code);
        if (tone === 'negative') {
            out[code] = 'var(--destructive)';
        } else if (tone === 'positive') {
            out[code] = 'var(--chart-2)';
        } else {
            out[code] = NEUTRAL_RAMP[neutralIndex % NEUTRAL_RAMP.length];
            neutralIndex += 1;
        }
    }
    return out;
}
