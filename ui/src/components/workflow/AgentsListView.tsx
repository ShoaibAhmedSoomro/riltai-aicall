'use client';

import { Archive, FolderInput, RotateCcw, Search, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import {
    moveWorkflowToFolderApiV1WorkflowWorkflowIdFolderPut,
    updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut,
} from '@/client/sdk.gen';
import type { FolderResponse, WorkflowListResponse } from '@/client/types.gen';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

import {
    type AgentFilter,
    bulkSummary,
    DEFAULT_FILTER,
    filterAgents,
    isNarrowing,
    newestFirst,
    runBulk,
    type StatusFilter,
} from './agentsList';
import { AgentFolderView } from './folders/AgentFolderView';
import { FolderSection } from './folders/FolderSection';
import { type AgentSelection, WorkflowTable } from './WorkflowTable';

interface AgentsListViewProps {
    /** Every agent, active and archived. Filtering happens here, in the browser. */
    workflows: WorkflowListResponse[];
    folders: FolderResponse[];
}

/**
 * The agents page body: find an agent, narrow the list, act on several at once.
 *
 * The server hands over the whole list (one request), so search and filters need
 * no endpoint. With nothing narrowing the list, agents stay grouped in their
 * folders as before. The moment a query or folder filter is active the result is
 * one flat table, because a search must never hide a match inside a collapsed
 * folder.
 */
export function AgentsListView({ workflows, folders }: AgentsListViewProps) {
    const router = useRouter();
    const [filter, setFilter] = useState<AgentFilter>(DEFAULT_FILTER);
    const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
    const [busy, setBusy] = useState(false);

    // A select-all must never act on rows the person can no longer see.
    useEffect(() => {
        setSelected(new Set());
    }, [filter.query, filter.status, filter.folder]);

    const visible = useMemo(() => newestFirst(filterAgents(workflows, filter)), [workflows, filter]);
    const narrowing = isNarrowing(filter);

    const selection: AgentSelection = useMemo(
        () => ({
            selected,
            onToggle: (id, on) =>
                setSelected((prev) => {
                    const next = new Set(prev);
                    if (on) next.add(id); else next.delete(id);
                    return next;
                }),
            onToggleMany: (ids, on) =>
                setSelected((prev) => {
                    const next = new Set(prev);
                    for (const id of ids) {
                        if (on) next.add(id); else next.delete(id);
                    }
                    return next;
                }),
        }),
        [selected],
    );

    const chosen = workflows.filter((w) => selected.has(w.id));
    const archivable = chosen.filter((w) => w.status === 'active');
    const restorable = chosen.filter((w) => w.status === 'archived');

    async function applyStatus(rows: WorkflowListResponse[], status: 'active' | 'archived') {
        setBusy(true);
        try {
            const result = await runBulk(
                rows.map((w) => w.id),
                async (id) => {
                    const res = await updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut({
                        path: { workflow_id: id },
                        body: { status },
                    });
                    return !res.error;
                },
            );
            const message = bulkSummary(status === 'archived' ? 'archived' : 'restored', result);
            if (result.failed > 0) toast.error(message); else toast.success(message);
            setSelected(new Set());
            router.refresh();
        } finally {
            setBusy(false);
        }
    }

    async function applyMove(rows: WorkflowListResponse[], folderId: number | null) {
        setBusy(true);
        try {
            const result = await runBulk(
                rows.map((w) => w.id),
                async (id) => {
                    const res = await moveWorkflowToFolderApiV1WorkflowWorkflowIdFolderPut({
                        path: { workflow_id: id },
                        body: { folder_id: folderId },
                    });
                    return !res.error;
                },
            );
            const message = bulkSummary('moved', result);
            if (result.failed > 0) toast.error(message); else toast.success(message);
            setSelected(new Set());
            router.refresh();
        } finally {
            setBusy(false);
        }
    }

    if (workflows.length === 0) {
        return (
            <Card>
                <CardContent className="p-8 text-center text-muted-foreground">
                    No agents yet. Create your first agent to get started.
                </CardContent>
            </Card>
        );
    }

    const active = visible.filter((w) => w.status === 'active');
    const archived = visible.filter((w) => w.status === 'archived');

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
                <div className="relative min-w-[220px] flex-1">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                        value={filter.query}
                        onChange={(e) => setFilter((f) => ({ ...f, query: e.target.value }))}
                        placeholder="Search by name or ID"
                        aria-label="Search agents"
                        className="pl-8"
                    />
                </div>
                <Select value={filter.status} onValueChange={(v) => setFilter((f) => ({ ...f, status: v as StatusFilter }))}>
                    <SelectTrigger className="w-36" aria-label="Filter by status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="active">Active</SelectItem>
                        <SelectItem value="archived">Archived</SelectItem>
                        <SelectItem value="all">All</SelectItem>
                    </SelectContent>
                </Select>
                {folders.length > 0 && (
                    <Select value={filter.folder} onValueChange={(v) => setFilter((f) => ({ ...f, folder: v }))}>
                        <SelectTrigger className="w-44" aria-label="Filter by folder"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All folders</SelectItem>
                            <SelectItem value="none">Uncategorized</SelectItem>
                            {folders.map((f) => <SelectItem key={f.id} value={String(f.id)}>{f.name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                )}
            </div>

            {selected.size > 0 && (
                <div
                    role="toolbar"
                    aria-label="Actions for the selected agents"
                    className="sticky top-14 z-20 flex flex-wrap items-center gap-2 rounded-md border bg-background px-3 py-2 shadow-sm"
                >
                    <span className="text-sm font-medium">{selected.size} selected</span>
                    {archivable.length > 0 && (
                        <Button size="sm" variant="outline" disabled={busy} onClick={() => applyStatus(archivable, 'archived')}>
                            <Archive /> Archive{archivable.length !== chosen.length ? ` (${archivable.length})` : ''}
                        </Button>
                    )}
                    {restorable.length > 0 && (
                        <Button size="sm" variant="outline" disabled={busy} onClick={() => applyStatus(restorable, 'active')}>
                            <RotateCcw /> Restore{restorable.length !== chosen.length ? ` (${restorable.length})` : ''}
                        </Button>
                    )}
                    {archivable.length > 0 && folders.length > 0 && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button size="sm" variant="outline" disabled={busy}><FolderInput /> Move to folder</Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="start" className="w-52">
                                <DropdownMenuLabel>Move {archivable.length} to</DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => applyMove(archivable, null)}>Uncategorized</DropdownMenuItem>
                                {folders.map((f) => (
                                    <DropdownMenuItem key={f.id} onClick={() => applyMove(archivable, f.id)}>
                                        <span className="truncate">{f.name}</span>
                                    </DropdownMenuItem>
                                ))}
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}
                    <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setSelected(new Set())}>
                        <X /> Clear
                    </Button>
                </div>
            )}

            {visible.length === 0 ? (
                <Card>
                    <CardContent className="p-8 text-center text-muted-foreground">
                        No agents match.{' '}
                        <button className="underline" onClick={() => setFilter(DEFAULT_FILTER)}>Clear the filters</button>
                    </CardContent>
                </Card>
            ) : narrowing ? (
                <WorkflowTable
                    workflows={visible}
                    showArchived={false}
                    folders={filter.status === 'archived' ? undefined : folders}
                    selection={selection}
                />
            ) : filter.status === 'archived' ? (
                <WorkflowTable workflows={archived} showArchived selection={selection} />
            ) : (
                <>
                    <AgentFolderView workflows={active} folders={folders} selection={selection} />
                    {filter.status === 'all' && archived.length > 0 && (
                        <div className="mt-6">
                            <FolderSection kind="archived" workflows={archived} selection={selection} />
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
