import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const widgetSource = readFileSync(
    resolve(process.cwd(), 'public/embed/rilt-widget.js'),
    'utf8',
);

// The real embed-config response always carries the COMPLETE text set:
// `EmbedConfigResponse.texts` is a required `WidgetTexts`
// (api/routes/public_embed.py) and `WidgetTexts.resolve()` fills every field
// from its own defaults (api/schemas/widget_texts.py), so a partial or absent
// map is not something a client can receive. That is why the widget holds no
// copy of its own: `widgetText()` warning and returning '' is its guard against
// talking to an older API, not a fallback.
//
// A fixture without `texts` therefore misrepresents the server. It rendered the
// panel with blank labels and left an assertion on the end-of-chat banner
// comparing against an empty string.
//
// The values are read out of the committed OpenAPI spec instead of being
// retyped here, so they cannot drift from the Python schema — CI already fails
// if the spec and the app disagree, and widget_texts.py is documented as the
// single source of truth that nothing else may hardcode.
const widgetTextDefaults: Record<string, string> = Object.fromEntries(
    Object.entries(
        (
            JSON.parse(
                readFileSync(
                    resolve(process.cwd(), '../docs/api-reference/openapi.json'),
                    'utf8',
                ),
            ) as {
                components: {
                    schemas: {
                        WidgetTexts: { properties: Record<string, { default: string }> };
                    };
                };
            }
        ).components.schemas.WidgetTexts.properties,
    ).map(([key, prop]) => [key, prop.default]),
);

type WidgetWindow = Window & {
    RiltWidget?: {
        init: () => Promise<void>;
        start: () => Promise<void>;
        startChat: () => Promise<void>;
        endChat: () => Promise<unknown[] | null>;
        getState: () => { chat: { status: string } };
    };
};

async function flushMicrotasks() {
    for (let i = 0; i < 5; i += 1) {
        await Promise.resolve();
    }
}

function createFetchMock(autoStart: boolean) {
    return vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/api/v1/public/embed/config/')) {
            return {
                ok: true,
                status: 200,
                json: async () => ({
                    workflow_id: 7,
                    settings: {
                        widgetType: 'chat',
                        embedMode: 'inline',
                        containerId: 'rilt-inline-container',
                    },
                    texts: widgetTextDefaults,
                    auto_start: autoStart,
                }),
            } as Response;
        }

        if (url.includes('/api/v1/public/embed/chat/') && url.endsWith('/end')) {
            return {
                ok: true,
                status: 200,
                json: async () => ({
                    revision: 3,
                    state: 'completed',
                    is_completed: true,
                    turns: [],
                }),
            } as Response;
        }

        return {
            ok: true,
            status: 200,
            json: async () => ({
                session_token: 'emb_session_TEST',
                workflow_run_id: 101,
                chat_session: {
                    revision: 2,
                    state: 'running',
                    is_completed: false,
                    turns: [],
                },
            }),
        } as Response;
    });
}

function countInitCalls(fetchMock: ReturnType<typeof createFetchMock>) {
    return fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith('/api/v1/public/embed/init'),
    ).length;
}

async function loadWidget(fetchMock: ReturnType<typeof createFetchMock>) {
    vi.stubGlobal('fetch', fetchMock);
    window.eval(widgetSource);
    await flushMicrotasks();

    const widget = (window as WidgetWindow).RiltWidget;
    expect(widget).toBeDefined();
    if (fetchMock.mock.calls.length === 0) {
        await widget?.init();
    }
    await flushMicrotasks();
    return widget as NonNullable<WidgetWindow['RiltWidget']>;
}

describe('public embed widget copy contract', () => {
    // The widget renders whatever the server sends and has no defaults, so any
    // key it asks for that WidgetTexts does not define renders as an empty
    // string with only a console warning. That is how a blank end-of-chat
    // banner survived here unnoticed. A typo in the widget, or a field dropped
    // from the schema, fails this instead of silently blanking a label.
    it('asks only for labels the server schema defines', () => {
        const requested = [
            ...new Set(
                [...widgetSource.matchAll(/widgetText\('([A-Za-z0-9_]+)'\)/g)].map(
                    (match) => match[1],
                ),
            ),
        ].sort();

        expect(requested.length).toBeGreaterThan(0);
        expect(Object.keys(widgetTextDefaults).length).toBeGreaterThan(0);
        expect(
            requested.filter((key) => !(key in widgetTextDefaults)),
        ).toEqual([]);
    });

    it('supplies non-empty copy for every one of them', () => {
        const blank = Object.entries(widgetTextDefaults)
            .filter(([, value]) => typeof value !== 'string' || value.length === 0)
            .map(([key]) => key);

        expect(blank).toEqual([]);
    });
});

describe('public embed widget chat lifecycle', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        document.head.innerHTML = '';
        document.body.innerHTML = `
            <script src="http://widget.test/embed/rilt-widget.js?token=emb_TEST"></script>
            <div id="rilt-inline-container"></div>
        `;
    });

    afterEach(() => {
        delete (window as WidgetWindow).RiltWidget;
        vi.useRealTimers();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
        document.head.innerHTML = '';
        document.body.innerHTML = '';
    });

    it('auto-start replaces the inline CTA with the started conversation', async () => {
        const fetchMock = createFetchMock(true);
        await loadWidget(fetchMock);
        await vi.advanceTimersByTimeAsync(1000);
        await flushMicrotasks();

        expect(countInitCalls(fetchMock)).toBe(1);
        expect(document.querySelector('.rilt-chat-inline-cta')).toBeNull();
        expect(document.querySelector('.rilt-chat-panel--inline')).not.toBeNull();
    });

    it('public startChat opens the inline panel and reuses its session', async () => {
        const fetchMock = createFetchMock(false);
        const widget = await loadWidget(fetchMock);

        expect(document.querySelector('.rilt-chat-inline-cta')).not.toBeNull();
        expect(countInitCalls(fetchMock)).toBe(0);

        await widget.startChat();
        await flushMicrotasks();

        expect(countInitCalls(fetchMock)).toBe(1);
        expect(document.querySelector('.rilt-chat-inline-cta')).toBeNull();
        expect(document.querySelector('.rilt-chat-panel--inline')).not.toBeNull();

        await widget.startChat();
        await flushMicrotasks();
        expect(countInitCalls(fetchMock)).toBe(1);
    });

    it('shows an end-chat action that completes the server session', async () => {
        const fetchMock = createFetchMock(false);
        const widget = await loadWidget(fetchMock);

        await widget.startChat();
        await flushMicrotasks();

        const endButton = document.querySelector<HTMLButtonElement>('.rilt-chat-end');
        expect(endButton).not.toBeNull();
        expect(endButton?.disabled).toBe(false);

        endButton?.click();
        await flushMicrotasks();

        expect(fetchMock.mock.calls.some(([url]) =>
            String(url).endsWith('/api/v1/public/embed/chat/emb_session_TEST/end'),
        )).toBe(false);

        const confirmEndButton = document.querySelector<HTMLButtonElement>(
            '.rilt-chat-end-confirm-submit',
        );
        expect(confirmEndButton).not.toBeNull();
        confirmEndButton?.click();
        await flushMicrotasks();

        const endCalls = fetchMock.mock.calls.filter(([url]) =>
            String(url).endsWith('/api/v1/public/embed/chat/emb_session_TEST/end'),
        );
        expect(endCalls).toHaveLength(1);
        expect(widget.getState().chat.status).toBe('ended');
        // Asserted against the schema default rather than a retyped literal:
        // the question is whether the banner renders the conversation-ended
        // copy at all (it used to render nothing), not whether that copy still
        // reads exactly as it did when this test was written.
        expect(document.querySelector('.rilt-chat-banner')?.textContent).toContain(
            widgetTextDefaults.conversationEndedText,
        );
        expect(widgetTextDefaults.conversationEndedText).toBeTruthy();
        expect(document.querySelector<HTMLButtonElement>('.rilt-chat-send')?.disabled).toBe(true);
    });

    it('generic start waits for chat configuration before choosing a flow', async () => {
        let resolveConfig: (response: Response) => void = () => undefined;
        const configResponse = new Promise<Response>((resolve) => {
            resolveConfig = resolve;
        });
        const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('/api/v1/public/embed/config/')) {
                return configResponse;
            }
            if (url.endsWith('/api/v1/public/embed/init')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        session_token: 'emb_session_TEST',
                        workflow_run_id: 101,
                        config: { workflow_id: 7 },
                        chat_session: {
                            revision: 2,
                            state: 'running',
                            is_completed: false,
                            turns: [],
                        },
                    }),
                } as Response;
            }
            if (url.includes('/turn-credentials/')) {
                return { ok: false, status: 503 } as Response;
            }
            throw new Error(`Unexpected request: ${url}`);
        });
        const getUserMedia = vi.fn().mockRejectedValue(
            Object.assign(new Error('permission denied'), { name: 'NotAllowedError' }),
        );
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });

        window.eval(widgetSource);
        await flushMicrotasks();
        const widget = (window as WidgetWindow).RiltWidget;
        expect(widget).toBeDefined();

        const startPromise = widget?.start();
        await flushMicrotasks();

        expect(countInitCalls(fetchMock)).toBe(0);
        expect(getUserMedia).not.toHaveBeenCalled();

        resolveConfig({
            ok: true,
            status: 200,
            json: async () => ({
                workflow_id: 7,
                settings: {
                    widgetType: 'chat',
                    embedMode: 'inline',
                    containerId: 'rilt-inline-container',
                },
                texts: widgetTextDefaults,
                auto_start: false,
            }),
        } as Response);
        await startPromise;
        await flushMicrotasks();

        const configCalls = fetchMock.mock.calls.filter(([url]) =>
            String(url).includes('/api/v1/public/embed/config/'),
        );
        expect(configCalls).toHaveLength(1);
        expect(countInitCalls(fetchMock)).toBe(1);
        expect(getUserMedia).not.toHaveBeenCalled();
        expect(document.querySelector('.rilt-chat-panel--inline')).not.toBeNull();
    });
});
