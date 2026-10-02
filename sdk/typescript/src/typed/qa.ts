// GENERATED — do not edit by hand.
//
// Regenerate with `npm run codegen` against the target AICall backend.
// Source of truth: the backend's model-backed node-spec catalog served
// from `/api/v1/node-types`.

/**
 * Named values to pull out of the finished call. They land in `gathered_context.extracted_variables` and get one column each in the CSV export. A field the model does not return is left out rather than defaulted.
 */
export interface QaQa_extraction_fieldsRow {
    /**
     * snake_case identifier used downstream.
     */
    name: string;
    /**
     * Data type of the extracted value.
     */
    type: "string" | "number" | "boolean";
    /**
     * Per-variable hint describing what to look for.
     */
    prompt?: string;
}
/**
 * Pass/fail questions asked of the call. A failure tags the call `check_failed:<name>`, which is filterable.
 */
export interface QaQa_checksRow {
    /**
     * snake_case identifier. A failure tags the call `check_failed:<name>`.
     */
    name: string;
    /**
     * What must be true for this check to pass.
     */
    criterion: string;
    /**
     * Ask for a 0-100 score alongside the verdict.
     */
    scored?: boolean;
}

/**
 * Run LLM quality analysis on the call transcript.
 *
 * LLM hint: Runs an LLM quality review on the call transcript after completion. Per-node analysis splits the conversation by node and evaluates each segment against the configured system prompt. Sampling, minimum duration, and voicemail filters are supported.
 */
export interface Qa {
    type: "qa";
    /**
     * Short identifier for this QA configuration.
     */
    name?: string;
    /**
     * When false, the QA run is skipped.
     */
    qa_enabled?: boolean;
    /**
     * Instructions to the QA reviewer LLM. Supports placeholders: `{node_summary}`, `{previous_conversation_summary}`, `{transcript}`, `{metrics}`.
     */
    qa_system_prompt?: string;
    /**
     * Named values to pull out of the finished call. They land in `gathered_context.extracted_variables` and get one column each in the CSV export. A field the model does not return is left out rather than defaulted.
     */
    qa_extraction_fields?: Array<QaQa_extraction_fieldsRow>;
    /**
     * Pass/fail questions asked of the call. A failure tags the call `check_failed:<name>`, which is filterable.
     */
    qa_checks?: Array<QaQa_checksRow>;
    /**
     * Calls shorter than this are skipped.
     */
    qa_min_call_duration?: number;
    /**
     * When false, calls flagged as voicemail are skipped.
     */
    qa_voicemail_calls?: boolean;
    /**
     * Percent of eligible calls QA'd. 100 means every call; lower values use random sampling.
     */
    qa_sample_rate?: number;
    /**
     * When true, the QA pass uses the same LLM the workflow runs with. Set false to specify a separate provider/model.
     */
    qa_use_workflow_llm?: boolean;
    /**
     * LLM provider used for the QA pass.
     */
    qa_provider?: "openai" | "azure" | "openrouter" | "anthropic";
    /**
     * Model identifier (e.g., 'gpt-4o', 'claude-sonnet-4-6'). Provider-specific.
     */
    qa_model?: string;
    /**
     * API key for the chosen provider.
     */
    qa_api_key?: string;
    /**
     * Required for the Azure provider.
     */
    qa_endpoint?: string;
}

/** Factory — sets `type` for you so you don't repeat the discriminator. */
export function qa(input: Omit<Qa, "type">): Qa {
    return { type: "qa", ...input };
}
