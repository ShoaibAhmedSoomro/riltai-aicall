/**
 * Every documentation link in the product, resolved through one function.
 *
 * `docs.rilt.ai` is NOT published — it is NXDOMAIN, and nothing in this repo
 * deploys it. All 11 linked pages exist as Mintlify `.mdx` sources under
 * `docs/`, so the content is real; only the hosting is missing. Until it is
 * published, every "Learn more" in the app was a browser error page.
 *
 * So links point at the `.mdx` source on GitHub, which resolves and shows the
 * real content. It is not pretty — frontmatter is visible and Mintlify
 * components render as raw JSX — but a working link to the right words beats a
 * dead one.
 *
 * TO SWITCH TO THE REAL DOCS SITE: set DOCS_SITE below to "https://docs.rilt.ai"
 * and add the DNS record. That is the entire change; every link follows.
 */

// Set to the published docs origin (e.g. "https://docs.rilt.ai") once it exists.
// null means "fall back to the source on GitHub".
const DOCS_SITE: string | null = null;

const DOCS_SOURCE_BASE =
    "https://github.com/ShoaibAhmedSoomro/riltai-aicall/blob/main/docs";

/**
 * Build a documentation URL from a site-relative path.
 *
 * `path` is the Mintlify route without a leading slash or extension, and may
 * carry an anchor: "voice-agent/agent", "voice-agent/add-to-website#headless-mode".
 */
export function docsUrl(path: string): string {
    const normalized = path.replace(/^\/+/, "");
    if (DOCS_SITE) {
        return normalized ? `${DOCS_SITE}/${normalized}` : DOCS_SITE;
    }
    if (!normalized) {
        return DOCS_SOURCE_BASE;
    }
    // GitHub needs the file extension, and its heading anchors are generated
    // differently from Mintlify's — so an anchor may land on the page rather
    // than the section. Acceptable: the alternative is no page at all.
    const [route, anchor] = normalized.split("#");
    return `${DOCS_SOURCE_BASE}/${route}.mdx${anchor ? `#${anchor}` : ""}`;
}

/** The documentation root, for a bare "Docs" link. */
export const DOCS_BASE = docsUrl("");

export const NODE_DOCUMENTATION_URLS: Record<string, string> = {
    startCall: docsUrl("voice-agent/start-call"),
    endCall: docsUrl("voice-agent/end-call"),
    agent: docsUrl("voice-agent/agent"),
    global: docsUrl("voice-agent/global"),
    apiTrigger: docsUrl("voice-agent/api-trigger"),
    webhook: docsUrl("voice-agent/webhook"),
    qaAnalysis: docsUrl("getting-started/index"),
};

export const CONTEXT_VARIABLES_DOC_URL = docsUrl(
    "core-concepts/context-and-variables",
);

export const TOOLS_INTRODUCTION_DOC_URL = docsUrl("voice-agent/tools/introduction");

export const KNOWLEDGE_BASE_DOC_URL = docsUrl("voice-agent/knowledge-base");

export const PRE_CALL_DATA_FETCH_DOC_URL = docsUrl(
    "voice-agent/pre-call-data-fetch",
);

export const SETTINGS_DOCUMENTATION_URLS: Record<string, string> = {
    general: docsUrl("voice-agent/editing-a-workflow"),
    modelOverrides: docsUrl("configurations/inference-providers"),
    templateVariables: docsUrl("voice-agent/template-variables"),

    recordings: docsUrl("voice-agent/pre-recorded-audio"),
    deployment: docsUrl("voice-agent/add-to-website"),
};

export const WIDGET_CONTEXT_DOC_URL = docsUrl(
    "voice-agent/add-to-website#pass-context-to-the-agent",
);

export const WIDGET_MODE_DOCUMENTATION_URLS: Record<
    "floating" | "inline" | "headless",
    string
> = {
    floating: docsUrl("voice-agent/add-to-website#floating-widget"),
    inline: docsUrl("voice-agent/add-to-website#inline-component"),
    headless: docsUrl("voice-agent/add-to-website#headless-mode"),
};

export const TOOL_DOCUMENTATION_URLS: Record<string, string> = {
    http_api: docsUrl("voice-agent/tools/http-api"),
    end_call: docsUrl("voice-agent/tools/end-call"),
    transfer_call: docsUrl("voice-agent/tools/call-transfer"),
};

// The twelve links that were hardcoded as literals in feature files rather than
// going through this module — which is why they all had to be found by grep.
export const MCP_DOC_URL = docsUrl("integrations/mcp");
export const TRACING_DOC_URL = docsUrl("configurations/tracing");
export const API_KEYS_DOC_URL = docsUrl("configurations/api-keys");
export const INTERRUPTION_DOC_URL = docsUrl("configurations/interruption");
export const TELEPHONY_OVERVIEW_DOC_URL = docsUrl("integrations/telephony/overview");
export const TELEPHONY_INBOUND_DOC_URL = docsUrl("integrations/telephony/inbound");
export const PRE_RECORDED_AUDIO_DOC_URL = docsUrl("voice-agent/pre-recorded-audio");
export const VOICE_AGENT_INTRO_DOC_URL = docsUrl("voice-agent/introduction");
export const DEPLOYMENT_UPDATE_DOC_URL = docsUrl("deployment/update");
