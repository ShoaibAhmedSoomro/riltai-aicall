import { describe, expect, it } from 'vitest';

import { isSinglePromptShape } from './agentShape';

const start = { id: 's', type: 'startCall' };
const end = { id: 'e', type: 'endCall' };
const agent = { id: 'a', type: 'agentNode' };

describe('isSinglePromptShape', () => {
    it('is true for start -> end', () => {
        expect(isSinglePromptShape([start, end], [{ source: 's', target: 'e' }])).toBe(true);
    });

    it('stops matching the moment a node is added', () => {
        expect(isSinglePromptShape([start, agent, end], [{ source: 's', target: 'e' }])).toBe(false);
    });

    it('is false with a global persona, because it changes what the model is told', () => {
        const g = { id: 'g', type: 'globalNode' };
        expect(isSinglePromptShape([start, end, g], [{ source: 's', target: 'e' }])).toBe(false);
    });

    it('is false when the edge does not run start -> end', () => {
        expect(isSinglePromptShape([start, end], [{ source: 'e', target: 's' }])).toBe(false);
        expect(isSinglePromptShape([start, end], [])).toBe(false);
        expect(isSinglePromptShape([start, end], [{ source: 's', target: 'e' }, { source: 's', target: 'e' }])).toBe(false);
    });

    it('is false for a lone start (the old blank canvas) and for missing data', () => {
        expect(isSinglePromptShape([start], [])).toBe(false);
        expect(isSinglePromptShape(null, null)).toBe(false);
    });
});
