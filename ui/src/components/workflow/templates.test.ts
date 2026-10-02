import { describe, expect, it } from 'vitest';

import { categoriesOf, categoryLabel, defaultAgentName, filterByCategory, previewSteps } from './templates';

const t = (slug: string, category: string) => ({ slug, category });

describe('categories', () => {
    it('lists only categories that have a template, in a fixed order', () => {
        const templates = [t('a', 'outbound-sales'), t('b', 'receptionist'), t('c', 'outbound-sales')];
        expect(categoriesOf(templates)).toEqual(['receptionist', 'outbound-sales']);
    });

    it('still shows a category the server added later, after the known ones', () => {
        expect(categoriesOf([t('a', 'zeta'), t('b', 'receptionist'), t('c', 'alpha')])).toEqual([
            'receptionist', 'alpha', 'zeta',
        ]);
    });

    it('labels known slugs and falls back to a readable name', () => {
        expect(categoryLabel('appointment-booking')).toBe('Appointment booking');
        expect(categoryLabel('real_estate')).toBe('Real estate');
        expect(categoryLabel('')).toBe('General');
    });

    it('filters, and null means everything', () => {
        const templates = [t('a', 'receptionist'), t('b', 'outbound-sales')];
        expect(filterByCategory(templates, null)).toHaveLength(2);
        expect(filterByCategory(templates, 'receptionist').map((x) => x.slug)).toEqual(['a']);
        expect(filterByCategory(templates, 'nope')).toEqual([]);
    });
});

describe('defaultAgentName', () => {
    it('uses the template name as it is', () => {
        expect(defaultAgentName('  Front Desk Receptionist ')).toBe('Front Desk Receptionist');
    });
    it('never returns an empty name', () => {
        expect(defaultAgentName('   ')).toBe('New agent');
    });
});

describe('previewSteps', () => {
    it('lists the call steps and leaves out the global persona', () => {
        const def = {
            nodes: [
                { type: 'globalNode', data: { name: 'Global' } },
                { type: 'startCall', data: { name: 'Greeting' } },
                { type: 'agentNode', data: { name: 'Take A Message' } },
                { type: 'endCall', data: { name: '' } },
            ],
        };
        expect(previewSteps(def)).toEqual(['Greeting', 'Take A Message']);
    });
    it('copes with a missing definition', () => {
        expect(previewSteps(null)).toEqual([]);
        expect(previewSteps({})).toEqual([]);
    });
});
