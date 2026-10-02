import { describe, expect, it } from 'vitest';

import { applyStarter, offersStarterHandbook } from './starterHandbook';

const STARTER = '#goal\nYou are the voice.\n\n## Rules\nBe brief.\n';

describe('offersStarterHandbook', () => {
    it('only on the prompt of a global or start node', () => {
        expect(offersStarterHandbook('globalNode', 'prompt')).toBe(true);
        expect(offersStarterHandbook('startCall', 'prompt')).toBe(true);
    });
    it('not on other nodes, or other fields', () => {
        expect(offersStarterHandbook('agentNode', 'prompt')).toBe(false);
        expect(offersStarterHandbook('endCall', 'prompt')).toBe(false);
        expect(offersStarterHandbook('startCall', 'extraction_prompt')).toBe(false);
        expect(offersStarterHandbook(undefined, 'prompt')).toBe(false);
    });
});

describe('applyStarter', () => {
    it('fills an empty prompt', () => {
        expect(applyStarter('', STARTER)).toBe(STARTER);
        expect(applyStarter('   \n', STARTER)).toBe(STARTER);
    });

    it('keeps what is written and adds the handbook after it', () => {
        const out = applyStarter('Our clinic opens at nine.  \n', STARTER);
        expect(out.startsWith('Our clinic opens at nine.\n\n#goal')).toBe(true);
        expect(out.endsWith(STARTER)).toBe(true);
    });

    it('does not stack a second copy', () => {
        const once = applyStarter('Notes', STARTER);
        expect(applyStarter(once, STARTER)).toBe(once);
    });
});
