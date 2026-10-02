import { describe, expect, it } from 'vitest';

import {
    type AgentRow,
    bulkSummary,
    DEFAULT_FILTER,
    filterAgents,
    isNarrowing,
    newestFirst,
    runBulk,
    versionLabel,
} from './agentsList';

const a = (id: number, name: string, over: Partial<AgentRow> = {}): AgentRow => ({
    id,
    name,
    status: 'active',
    created_at: `2026-09-${String(id).padStart(2, '0')}T00:00:00Z`,
    folder_id: null,
    ...over,
});

const AGENTS = [
    a(1, 'Support Bot'),
    a(10, 'Sales Outreach', { folder_id: 5 }),
    a(11, 'support escalation', { folder_id: 5 }),
    a(12, 'Old Survey', { status: 'archived', folder_id: 6 }),
];

const ids = (list: AgentRow[]) => list.map((x) => x.id);

describe('filterAgents', () => {
    it('shows active agents by default', () => {
        expect(ids(filterAgents(AGENTS, DEFAULT_FILTER))).toEqual([1, 10, 11]);
    });

    it('the status control can show archived or everything', () => {
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, status: 'archived' }))).toEqual([12]);
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, status: 'all' }))).toEqual([1, 10, 11, 12]);
    });

    it('finds by name anywhere in it, ignoring case', () => {
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, query: 'SUPPORT' }))).toEqual([1, 11]);
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, query: ' outreach ' }))).toEqual([10]);
    });

    it('finds an exact id, but never treats an id as a substring', () => {
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, query: '10' }))).toEqual([10]);
        // "1" is agent 1 only, not 10, 11 or 12
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, query: '1' }))).toEqual([1]);
    });

    it('narrows by folder, including "no folder"', () => {
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, folder: '5' }))).toEqual([10, 11]);
        expect(ids(filterAgents(AGENTS, { ...DEFAULT_FILTER, folder: 'none' }))).toEqual([1]);
    });

    it('a folder nobody is in returns nothing, not everything', () => {
        expect(filterAgents(AGENTS, { ...DEFAULT_FILTER, folder: '99' })).toEqual([]);
    });

    it('all the controls combine', () => {
        expect(ids(filterAgents(AGENTS, { query: 'support', status: 'all', folder: '5' }))).toEqual([11]);
    });
});

describe('isNarrowing', () => {
    it('grouping is kept only when nothing narrows the list', () => {
        expect(isNarrowing(DEFAULT_FILTER)).toBe(false);
        expect(isNarrowing({ ...DEFAULT_FILTER, status: 'archived' })).toBe(false);
        expect(isNarrowing({ ...DEFAULT_FILTER, query: '  ' })).toBe(false);
        expect(isNarrowing({ ...DEFAULT_FILTER, query: 'x' })).toBe(true);
        expect(isNarrowing({ ...DEFAULT_FILTER, folder: 'none' })).toBe(true);
    });
});

describe('newestFirst', () => {
    it('sorts without mutating the input', () => {
        const input = [a(1, 'a'), a(3, 'c'), a(2, 'b')];
        expect(ids(newestFirst(input))).toEqual([3, 2, 1]);
        expect(ids(input)).toEqual([1, 3, 2]);
    });
});

describe('versionLabel', () => {
    it('says what is live, and flags unpublished work', () => {
        expect(versionLabel({ released_version_number: 3, has_unpublished_draft: false })).toEqual({ text: 'Live v3', tone: 'live' });
        expect(versionLabel({ released_version_number: 3, has_unpublished_draft: true })).toEqual({ text: 'Live v3 · Draft', tone: 'pending' });
    });

    it('an agent that was never published is just a draft', () => {
        expect(versionLabel({ released_version_number: null, has_unpublished_draft: true })).toEqual({ text: 'Draft', tone: 'draft' });
        expect(versionLabel({})).toEqual({ text: 'Draft', tone: 'draft' });
    });
});

describe('runBulk and bulkSummary', () => {
    it('counts each outcome, and one failure never stops the rest', async () => {
        const seen: number[] = [];
        const result = await runBulk([1, 2, 3, 4], async (id) => {
            seen.push(id);
            if (id === 2) throw new Error('boom');
            return id !== 3;
        });
        expect(seen.sort()).toEqual([1, 2, 3, 4]);
        expect(result).toEqual({ ok: 2, failed: 2 });
    });

    it('words the result plainly', () => {
        expect(bulkSummary('archived', { ok: 7, failed: 1 })).toBe('7 archived, 1 failed');
        expect(bulkSummary('moved', { ok: 3, failed: 0 })).toBe('3 moved');
        expect(bulkSummary('archived', { ok: 0, failed: 2 })).toBe('2 failed, none archived');
        expect(bulkSummary('archived', { ok: 0, failed: 0 })).toBe('Nothing was archived');
    });
});
