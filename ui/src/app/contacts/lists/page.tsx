"use client";

import { ArrowLeft, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
    createContactListApiV1ContactsListsPost,
    deleteContactListApiV1ContactsListsListUuidDelete,
    listContactListsApiV1ContactsListsGet,
    updateContactListApiV1ContactsListsListUuidPatch,
} from "@/client/sdk.gen";
import type { ContactListResponse } from "@/client/types.gen";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dateTime";

export default function ContactListsPage() {
    const { user, redirectToLogin, loading: authLoading } = useAuth();
    const [lists, setLists] = useState<ContactListResponse[] | null>(null);
    const [editing, setEditing] = useState<ContactListResponse | "new" | null>(null);
    const [deleting, setDeleting] = useState<ContactListResponse | null>(null);

    useEffect(() => {
        if (!authLoading && !user) redirectToLogin();
    }, [authLoading, user, redirectToLogin]);

    const load = useCallback(async () => {
        const res = await listContactListsApiV1ContactsListsGet();
        if (res.error) return toast.error(detailFromError(res.error, "Could not load lists"));
        setLists(res.data ?? []);
    }, []);

    useEffect(() => { if (user) void load(); }, [user, load]);

    async function confirmDelete() {
        if (!deleting) return;
        const res = await deleteContactListApiV1ContactsListsListUuidDelete({ path: { list_uuid: deleting.list_uuid } });
        setDeleting(null);
        if (res.error) return toast.error(detailFromError(res.error, "Could not delete the list"));
        toast.success("List deleted");
        void load();
    }

    if (authLoading || !user) return <div className="container mx-auto px-4 py-8"><Skeleton className="h-64 w-full" /></div>;

    return (
        <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
            <Button variant="ghost" size="sm" asChild><Link href="/contacts"><ArrowLeft /> Contacts</Link></Button>
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold">Contact lists</h1>
                    <p className="text-muted-foreground">Reusable groups of contacts. Pick one as the source of a campaign.</p>
                </div>
                <Button onClick={() => setEditing("new")}><Plus /> New list</Button>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Your lists</CardTitle>
                    <CardDescription>Deleting a list never deletes the contacts in it.</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="overflow-x-auto rounded-md border">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Description</TableHead>
                                    <TableHead className="text-right">Contacts</TableHead>
                                    <TableHead>Created</TableHead>
                                    <TableHead className="w-24" />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {lists === null ? (
                                    <TableRow><TableCell colSpan={5}><Skeleton className="h-6 w-full" /></TableCell></TableRow>
                                ) : lists.length === 0 ? (
                                    <TableRow><TableCell colSpan={5} className="py-10 text-center text-muted-foreground">No lists yet. Create one, or choose a list when you import a CSV.</TableCell></TableRow>
                                ) : lists.map((l) => (
                                    <TableRow key={l.list_uuid}>
                                        <TableCell>
                                            <Link href={`/contacts?list=${l.list_uuid}`} className="font-medium underline-offset-4 hover:underline">{l.name}</Link>
                                        </TableCell>
                                        <TableCell className="max-w-xs truncate text-muted-foreground">{l.description ?? "—"}</TableCell>
                                        <TableCell className="text-right tabular-nums">{(l.contact_count ?? 0).toLocaleString()}</TableCell>
                                        <TableCell className="whitespace-nowrap text-muted-foreground">{l.created_at ? formatDateTime(l.created_at) : "—"}</TableCell>
                                        <TableCell>
                                            <div className="flex justify-end gap-1">
                                                <Button variant="ghost" size="icon" aria-label={`Edit ${l.name}`} onClick={() => setEditing(l)}><Pencil /></Button>
                                                <Button variant="ghost" size="icon" aria-label={`Delete ${l.name}`} onClick={() => setDeleting(l)}><Trash2 /></Button>
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </CardContent>
            </Card>

            <ListDialog editing={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} />

            <AlertDialog open={deleting !== null} onOpenChange={(o) => !o && setDeleting(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete &ldquo;{deleting?.name}&rdquo;?</AlertDialogTitle>
                        <AlertDialogDescription>
                            The list is removed. Its {(deleting?.contact_count ?? 0).toLocaleString()} contact(s) stay in Contacts. A campaign already created from this list keeps its own queue.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={confirmDelete}>Delete list</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

function ListDialog({ editing, onClose, onSaved }: {
    editing: ContactListResponse | "new" | null;
    onClose: () => void;
    onSaved: () => void;
}) {
    const existing = editing && editing !== "new" ? editing : null;
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setName(existing?.name ?? "");
        setDescription(existing?.description ?? "");
        setError(null);
    }, [editing, existing]);

    async function save() {
        setSaving(true);
        setError(null);
        try {
            const res = existing
                ? await updateContactListApiV1ContactsListsListUuidPatch({
                      path: { list_uuid: existing.list_uuid },
                      body: { name: name.trim(), description: description.trim() || null },
                  })
                : await createContactListApiV1ContactsListsPost({
                      body: { name: name.trim(), description: description.trim() || null },
                  });
            if (res.error) {
                setError(detailFromError(res.error, "Could not save the list"));
                return;
            }
            toast.success(existing ? "List updated" : "List created");
            onSaved();
        } finally {
            setSaving(false);
        }
    }

    return (
        <Dialog open={editing !== null} onOpenChange={(o) => !o && onClose()}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{existing ? "Edit list" : "New list"}</DialogTitle>
                    <DialogDescription>Add contacts to it from the Contacts page or when you import.</DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div className="space-y-1.5">
                        <Label htmlFor="l-name" className="text-xs">Name</Label>
                        <Input id="l-name" value={name} onChange={(e) => setName(e.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                        <Label htmlFor="l-desc" className="text-xs">Description (optional)</Label>
                        <Textarea id="l-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
                    </div>
                    {error && <p className="text-sm text-destructive">{error}</p>}
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button onClick={save} disabled={saving || !name.trim()}>{saving ? "Saving…" : "Save"}</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
