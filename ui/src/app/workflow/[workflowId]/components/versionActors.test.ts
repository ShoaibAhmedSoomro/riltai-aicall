import { describe, expect, it } from 'vitest';

import type { WorkflowVersionResponse } from '@/client/types.gen';

import { versionActors } from './VersionHistoryPanel';

const v = (over: Partial<WorkflowVersionResponse>) =>
    ({ id: 1, version_number: 1, status: 'published', created_at: '', workflow_json: {}, ...over }) as WorkflowVersionResponse;

describe('versionActors', () => {
    it('says nothing for a version that predates the record', () => {
        expect(versionActors(v({}))).toBeNull();
        expect(versionActors(v({ status: 'draft' }))).toBeNull();
    });

    it('names the publisher of a published version', () => {
        expect(versionActors(v({ published_by_name: 'Sam' }))).toBe('By Sam');
    });

    it('names both when the author and the publisher differ', () => {
        expect(versionActors(v({ created_by_name: 'Ana', published_by_name: 'Sam' }))).toBe(
            'By Ana · published by Sam',
        );
    });

    it('does not repeat one person twice', () => {
        expect(versionActors(v({ created_by_name: 'Sam', published_by_name: 'Sam' }))).toBe('By Sam');
    });

    it('names who last edited a draft, and who started it if someone else', () => {
        expect(versionActors(v({ status: 'draft', updated_by_name: 'Sam' }))).toBe('Edited by Sam');
        expect(
            versionActors(v({ status: 'draft', created_by_name: 'Ana', updated_by_name: 'Sam' })),
        ).toBe('Started by Ana · edited by Sam');
    });
});
