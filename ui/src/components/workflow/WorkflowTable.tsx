'use client';

import {
    Archive,
    Check,
    Copy,
    Folder as FolderIcon,
    FolderInput,
    Inbox,
    MoreHorizontal,
    Pencil,
    RotateCcw,
    Share2,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';
import { toast } from 'sonner';

import {
    moveWorkflowToFolderApiV1WorkflowWorkflowIdFolderPut,
    updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut,
} from '@/client/sdk.gen';
import type { FolderResponse } from '@/client/types.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuSub,
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { useOrganizationTimezone } from '@/hooks/useOrganizationTimezone';
import { copyTextToClipboard } from '@/lib/clipboard';
import { formatDate } from '@/lib/dateTime';
import { cn } from '@/lib/utils';

import { type AgentRow, versionLabel } from './agentsList';

/** Selection state lives in the list view, so it survives regrouping. */
export interface AgentSelection {
    selected: ReadonlySet<number>;
    onToggle: (id: number, on: boolean) => void;
    /** Select or clear exactly these rows (the ones this table is showing). */
    onToggleMany: (ids: number[], on: boolean) => void;
}

interface WorkflowTableProps {
    workflows: AgentRow[];
    showArchived: boolean;
    /**
     * When provided, each row gets a "Move to folder" action listing these
     * folders. Omit it (e.g. for the archived list) to hide the control.
     */
    folders?: FolderResponse[];
    /** The folder this table is rendered under; null means "Uncategorized". */
    currentFolderId?: number | null;
    /** Omit for a table with no checkboxes. */
    selection?: AgentSelection;
}

const TONE_CLASS = {
    live: 'border-primary/30 bg-primary/10 text-primary',
    pending: 'border-warning/40 bg-warning/10 text-foreground',
    draft: 'border-border bg-muted text-muted-foreground',
} as const;

export function WorkflowTable({
    workflows,
    showArchived,
    folders,
    currentFolderId = null,
    selection,
}: WorkflowTableProps) {
    const router = useRouter();
    const organizationTimezone = useOrganizationTimezone();
    const [isPending, startTransition] = useTransition();
    const [busyId, setBusyId] = useState<number | null>(null);

    const refresh = () => startTransition(() => router.refresh());

    const handleArchiveToggle = async (id: number, currentStatus: string) => {
        const archiving = currentStatus === 'active';
        setBusyId(id);
        try {
            const response = await updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut({
                path: { workflow_id: id },
                body: { status: archiving ? 'archived' : 'active' },
            });
            if (response.error) throw new Error('status update failed');
            toast.success(archiving ? 'Agent archived' : 'Agent restored');
            refresh();
        } catch (error) {
            console.error('Error changing agent status:', error);
            toast.error(archiving ? 'Failed to archive agent' : 'Failed to restore agent');
        } finally {
            setBusyId(null);
        }
    };

    const handleMove = async (id: number, folderId: number | null) => {
        setBusyId(id);
        try {
            const response = await moveWorkflowToFolderApiV1WorkflowWorkflowIdFolderPut({
                path: { workflow_id: id },
                body: { folder_id: folderId },
            });
            if (response.error) throw new Error('Failed to move agent');
            toast.success(folderId === null ? 'Moved to Uncategorized' : 'Agent moved');
            refresh();
        } catch (error) {
            console.error('Error moving workflow:', error);
            toast.error('Failed to move agent');
        } finally {
            setBusyId(null);
        }
    };

    const handleCopyLink = async (id: number) => {
        try {
            await copyTextToClipboard(`${window.location.origin}/workflow/${id}`);
            toast.success('Link copied');
        } catch {
            toast.error('Could not copy the link');
        }
    };

    const rowIds = workflows.map((w) => w.id);
    const selectedHere = selection ? rowIds.filter((id) => selection.selected.has(id)).length : 0;
    const allSelected = rowIds.length > 0 && selectedHere === rowIds.length;

    return (
        <Card className="overflow-hidden">
            <CardContent className="p-0">
                <Table>
                    <TableHeader>
                        <TableRow>
                            {selection && (
                                <TableHead className="w-10">
                                    <Checkbox
                                        checked={allSelected ? true : selectedHere > 0 ? 'indeterminate' : false}
                                        onCheckedChange={(v) => selection.onToggleMany(rowIds, v === true)}
                                        aria-label="Select all agents shown"
                                    />
                                </TableHead>
                            )}
                            <TableHead className="font-semibold">ID</TableHead>
                            <TableHead className="font-semibold">Agent Name</TableHead>
                            <TableHead className="font-semibold">Version</TableHead>
                            <TableHead className="font-semibold">Created At</TableHead>
                            <TableHead className="font-semibold text-center">Total Runs</TableHead>
                            <TableHead className="font-semibold text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {workflows.map((workflow) => {
                            const archived = showArchived || workflow.status === 'archived';
                            const version = versionLabel(workflow);
                            const busy = busyId === workflow.id || isPending;
                            return (
                                <TableRow
                                    key={workflow.id}
                                    data-state={selection?.selected.has(workflow.id) ? 'selected' : undefined}
                                    className={cn('hover:bg-accent transition-colors', archived && 'opacity-60')}
                                >
                                    {selection && (
                                        <TableCell>
                                            <Checkbox
                                                checked={selection.selected.has(workflow.id)}
                                                onCheckedChange={(v) => selection.onToggle(workflow.id, v === true)}
                                                aria-label={`Select ${workflow.name}`}
                                            />
                                        </TableCell>
                                    )}
                                    <TableCell className="text-muted-foreground">{workflow.id}</TableCell>
                                    <TableCell className="font-medium">{workflow.name}</TableCell>
                                    <TableCell>
                                        <Badge
                                            variant="outline"
                                            className={cn('whitespace-nowrap', TONE_CLASS[version.tone])}
                                            title={
                                                version.tone === 'pending'
                                                    ? 'Calls run the live version. The editor opens your unpublished draft.'
                                                    : version.tone === 'draft'
                                                      ? 'Never published, so it cannot take calls yet.'
                                                      : 'Calls run this version.'
                                            }
                                        >
                                            {version.text}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>{formatDate(workflow.created_at, organizationTimezone)}</TableCell>
                                    <TableCell className="text-center">
                                        <span className="inline-flex items-center justify-center min-w-[2rem] px-2 py-1 text-sm font-semibold bg-muted rounded-full">
                                            {workflow.total_runs || 0}
                                        </span>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex justify-end gap-2">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => router.push(`/workflow/${workflow.id}`)}
                                            >
                                                <Pencil size={16} />
                                                Edit
                                            </Button>
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        size="icon"
                                                        disabled={busy}
                                                        aria-label={`More actions for ${workflow.name}`}
                                                    >
                                                        {busyId === workflow.id ? (
                                                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                                                        ) : (
                                                            <MoreHorizontal />
                                                        )}
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end" className="w-52">
                                                    <DropdownMenuItem onClick={() => router.push(`/workflow/${workflow.id}/settings?embed=1`)}>
                                                        <Share2 size={14} className="mr-2" />
                                                        Share
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem onClick={() => handleCopyLink(workflow.id)}>
                                                        <Copy size={14} className="mr-2" />
                                                        Copy link
                                                    </DropdownMenuItem>
                                                    {folders && !archived && (
                                                        <DropdownMenuSub>
                                                            <DropdownMenuSubTrigger>
                                                                <FolderInput size={14} className="mr-2" />
                                                                Move to folder
                                                            </DropdownMenuSubTrigger>
                                                            <DropdownMenuSubContent className="w-52">
                                                                <DropdownMenuItem
                                                                    disabled={workflow.folder_id == null && currentFolderId === null}
                                                                    onClick={() => handleMove(workflow.id, null)}
                                                                >
                                                                    <Inbox size={14} className="mr-2" />
                                                                    Uncategorized
                                                                    {workflow.folder_id == null && <Check size={14} className="ml-auto" />}
                                                                </DropdownMenuItem>
                                                                {folders.map((folder) => (
                                                                    <DropdownMenuItem
                                                                        key={folder.id}
                                                                        disabled={folder.id === workflow.folder_id}
                                                                        onClick={() => handleMove(workflow.id, folder.id)}
                                                                    >
                                                                        <FolderIcon size={14} className="mr-2" />
                                                                        <span className="truncate">{folder.name}</span>
                                                                        {folder.id === workflow.folder_id && (
                                                                            <Check size={14} className="ml-auto shrink-0" />
                                                                        )}
                                                                    </DropdownMenuItem>
                                                                ))}
                                                            </DropdownMenuSubContent>
                                                        </DropdownMenuSub>
                                                    )}
                                                    <DropdownMenuSeparator />
                                                    <DropdownMenuItem onClick={() => handleArchiveToggle(workflow.id, workflow.status)}>
                                                        {archived ? (
                                                            <>
                                                                <RotateCcw size={14} className="mr-2" />
                                                                Restore
                                                            </>
                                                        ) : (
                                                            <>
                                                                <Archive size={14} className="mr-2" />
                                                                Archive
                                                            </>
                                                        )}
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </div>
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            </CardContent>
        </Card>
    );
}
