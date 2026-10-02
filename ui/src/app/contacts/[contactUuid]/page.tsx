"use client";

import { ArrowLeft, Ban, PhoneCall, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
    addListMembersApiV1ContactsListsListUuidMembersPost,
    addSuppressionsApiV1ContactsSuppressionsPost,
    bulkDeleteContactsApiV1ContactsBulkDeletePost,
    getContactApiV1ContactsContactUuidGet,
    getContactRunsApiV1ContactsContactUuidRunsGet,
    listContactListsApiV1ContactsListsGet,
    removeListMembersApiV1ContactsListsListUuidMembersDelete,
    removeSuppressionApiV1ContactsSuppressionsDelete,
    updateContactApiV1ContactsContactUuidPatch,
} from "@/client/sdk.gen";
import type { ContactListResponse, ContactResponse, ContactRunResponse } from "@/client/types.gen";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { Money } from "@/lib/currency";
import { formatDateTime } from "@/lib/dateTime";

import { contactName, validateFieldName } from "../utils";

type Row = { key: string; value: string };

const toRows = (attrs: Record<string, unknown>): Row[] =>
    Object.entries(attrs).map(([key, value]) => ({ key, value: value == null ? "" : String(value) }));

export default function ContactDetailPage() {
    const { contactUuid } = useParams<{ contactUuid: string }>();
    const router = useRouter();
    const { user, redirectToLogin, loading: authLoading } = useAuth();

    const [contact, setContact] = useState<ContactResponse | null>(null);
    const [notFound, setNotFound] = useState(false);
    const [first, setFirst] = useState("");
    const [last, setLast] = useState("");
    const [email, setEmail] = useState("");
    const [rows, setRows] = useState<Row[]>([]);
    const [saving, setSaving] = useState(false);

    const [allLists, setAllLists] = useState<ContactListResponse[]>([]);
    const [runs, setRuns] = useState<ContactRunResponse[]>([]);
    const [runsTotal, setRunsTotal] = useState(0);
    const [runsPage, setRunsPage] = useState(1);
    const [runsPages, setRunsPages] = useState(1);
    const [confirmDelete, setConfirmDelete] = useState(false);

    useEffect(() => {
        if (!authLoading && !user) redirectToLogin();
    }, [authLoading, user, redirectToLogin]);

    const load = useCallback(async () => {
        const res = await getContactApiV1ContactsContactUuidGet({ path: { contact_uuid: contactUuid } });
        if (res.error || !res.data) {
            if (res.response?.status === 404) setNotFound(true);
            else toast.error(detailFromError(res.error, "Could not load the contact"));
            return;
        }
        const c = res.data;
        setContact(c);
        setFirst(c.first_name ?? "");
        setLast(c.last_name ?? "");
        setEmail(c.email ?? "");
        setRows(toRows(c.attributes ?? {}));
    }, [contactUuid]);

    const loadRuns = useCallback(async (page: number) => {
        const res = await getContactRunsApiV1ContactsContactUuidRunsGet({
            path: { contact_uuid: contactUuid },
            query: { page, limit: 25 },
        });
        if (res.data) {
            setRuns(res.data.runs);
            setRunsTotal(res.data.total_count);
            setRunsPages(Math.max(1, res.data.total_pages));
        }
    }, [contactUuid]);

    useEffect(() => {
        if (!user) return;
        void load();
        void loadRuns(1);
        void listContactListsApiV1ContactsListsGet().then((r) => r.data && setAllLists(r.data));
    }, [user, load, loadRuns]);

    if (authLoading || !user) {
        return <div className="container mx-auto px-4 py-8"><Skeleton className="h-64 w-full" /></div>;
    }
    if (notFound) {
        return (
            <div className="container mx-auto px-4 py-8">
                <p className="mb-4">That contact does not exist.</p>
                <Button variant="outline" asChild><Link href="/contacts"><ArrowLeft /> Back to contacts</Link></Button>
            </div>
        );
    }
    if (!contact) {
        return <div className="container mx-auto px-4 py-8"><Skeleton className="h-64 w-full" /></div>;
    }

    const keys = rows.map((r) => r.key);
    const rowProblem = (r: Row, i: number): string | null => {
        if (!r.key) return null;
        return validateFieldName(r.key, keys.filter((_, j) => j !== i));
    };
    const attrsValid = rows.every((r, i) => !r.key.trim() ? !r.value.trim() : rowProblem(r, i) === null);

    const dirty =
        first !== (contact.first_name ?? "") ||
        last !== (contact.last_name ?? "") ||
        email !== (contact.email ?? "") ||
        JSON.stringify(rows.filter((r) => r.key)) !== JSON.stringify(toRows(contact.attributes ?? {}));

    async function save() {
        setSaving(true);
        try {
            const res = await updateContactApiV1ContactsContactUuidPatch({
                path: { contact_uuid: contactUuid },
                body: {
                    first_name: first.trim() || null,
                    last_name: last.trim() || null,
                    email: email.trim() || null,
                    attributes: Object.fromEntries(rows.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value])),
                },
            });
            if (res.error || !res.data) return toast.error(detailFromError(res.error, "Could not save"));
            toast.success("Saved");
            await load();
        } finally {
            setSaving(false);
        }
    }

    async function setSuppressed(on: boolean) {
        const res = on
            ? await addSuppressionsApiV1ContactsSuppressionsPost({ body: { phone_numbers: [contact!.phone_e164], reason: "Added from the contact page" } })
            : await removeSuppressionApiV1ContactsSuppressionsDelete({ query: { phone_e164: contact!.phone_e164 } });
        if (res.error) return toast.error(detailFromError(res.error, "Could not update the do-not-call list"));
        toast.success(on ? "Added to the do-not-call list" : "Removed from the do-not-call list");
        await load();
    }

    async function addToList(listUuid: string) {
        const res = await addListMembersApiV1ContactsListsListUuidMembersPost({
            path: { list_uuid: listUuid },
            body: { contact_uuids: [contactUuid] },
        });
        if (res.error) return toast.error(detailFromError(res.error, "Could not add to the list"));
        await load();
    }

    async function removeFromList(listUuid: string) {
        const res = await removeListMembersApiV1ContactsListsListUuidMembersDelete({
            path: { list_uuid: listUuid },
            body: { contact_uuids: [contactUuid] },
        });
        if (res.error) return toast.error(detailFromError(res.error, "Could not remove from the list"));
        await load();
    }

    async function remove() {
        const res = await bulkDeleteContactsApiV1ContactsBulkDeletePost({ body: { contact_uuids: [contactUuid] } });
        if (res.error) return toast.error(detailFromError(res.error, "Could not delete"));
        toast.success("Contact deleted");
        router.push("/contacts");
    }

    const memberOf = new Set((contact.lists ?? []).map((l) => l.list_uuid));
    const joinable = allLists.filter((l) => !memberOf.has(l.list_uuid));

    return (
        <div className="container mx-auto max-w-5xl space-y-6 px-4 py-8">
            <Button variant="ghost" size="sm" asChild><Link href="/contacts"><ArrowLeft /> Contacts</Link></Button>

            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold">{contactName(contact) ?? contact.phone_number}</h1>
                    <p className="mt-1 flex items-center gap-2 text-muted-foreground">
                        <span className="tabular-nums">{contact.phone_number}</span>
                        {contact.phone_number !== contact.phone_e164 && <span className="text-xs">({contact.phone_e164})</span>}
                        {contact.suppressed && <Badge variant="destructive">Do not call</Badge>}
                    </p>
                </div>
                <div className="flex gap-2">
                    {contact.suppressed ? (
                        <Button variant="outline" onClick={() => setSuppressed(false)}><PhoneCall /> Allow calls again</Button>
                    ) : (
                        <Button variant="outline" onClick={() => setSuppressed(true)}><Ban /> Do not call</Button>
                    )}
                    <Button variant="outline" onClick={() => setConfirmDelete(true)}><Trash2 /> Delete</Button>
                </div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Details</CardTitle>
                    <CardDescription>
                        The phone number is this contact&apos;s identity and cannot be edited. To use a different number, add a new contact.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="grid gap-4 sm:grid-cols-3">
                        <div className="space-y-1.5">
                            <Label htmlFor="d-first" className="text-xs">First name</Label>
                            <Input id="d-first" value={first} onChange={(e) => setFirst(e.target.value)} />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="d-last" className="text-xs">Last name</Label>
                            <Input id="d-last" value={last} onChange={(e) => setLast(e.target.value)} />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="d-email" className="text-xs">Email</Label>
                            <Input id="d-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label className="text-xs">Custom fields</Label>
                        <p className="text-xs text-muted-foreground">
                            Available to an agent in its prompts, for example {"{{company}}"}.
                        </p>
                        {rows.map((r, i) => {
                            const problem = rowProblem(r, i);
                            return (
                                <div key={i} className="flex items-start gap-2">
                                    <div className="w-48 shrink-0">
                                        <Input value={r.key} placeholder="field_name" aria-label={`Custom field ${i + 1} name`}
                                            onChange={(e) => setRows((p) => p.map((x, j) => j === i ? { ...x, key: e.target.value } : x))} />
                                        {problem && <p className="mt-1 text-xs text-destructive">{problem}</p>}
                                    </div>
                                    <Input className="flex-1" value={r.value} placeholder="value" aria-label={`Custom field ${i + 1} value`}
                                        onChange={(e) => setRows((p) => p.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} />
                                    <Button variant="ghost" size="icon" aria-label={`Remove custom field ${i + 1}`}
                                        onClick={() => setRows((p) => p.filter((_, j) => j !== i))}><X /></Button>
                                </div>
                            );
                        })}
                        <Button variant="outline" size="sm" onClick={() => setRows((p) => [...p, { key: "", value: "" }])}><Plus /> Add a field</Button>
                    </div>
                </CardContent>
                <CardFooter className="justify-end gap-3 border-t pt-6">
                    {dirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
                    <Button onClick={save} disabled={!dirty || saving || !attrsValid}>{saving ? "Saving…" : "Save"}</Button>
                </CardFooter>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Lists</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="flex flex-wrap gap-2">
                        {(contact.lists ?? []).length === 0 && <span className="text-sm text-muted-foreground">Not in any list.</span>}
                        {(contact.lists ?? []).map((l) => (
                            <Badge key={l.list_uuid} variant="secondary" className="gap-1 pr-1">
                                {l.name}
                                <button aria-label={`Remove from ${l.name}`} className="rounded p-0.5 hover:bg-muted" onClick={() => removeFromList(l.list_uuid)}>
                                    <X className="h-3 w-3" />
                                </button>
                            </Badge>
                        ))}
                    </div>
                    {joinable.length > 0 && (
                        <Select value={undefined} onValueChange={addToList}>
                            <SelectTrigger className="w-56" aria-label="Add to a list"><SelectValue placeholder="Add to a list…" /></SelectTrigger>
                            <SelectContent>
                                {joinable.map((l) => <SelectItem key={l.list_uuid} value={l.list_uuid}>{l.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Call history</CardTitle>
                    <CardDescription>
                        Calls placed to this number across all your agents. {(contact.call_count ?? 0) > 0 && `${contact.call_count} recorded on this contact.`}
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="overflow-x-auto rounded-md border">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>When</TableHead>
                                    <TableHead>Agent</TableHead>
                                    <TableHead>Outcome</TableHead>
                                    <TableHead className="text-right">Duration</TableHead>
                                    <TableHead className="text-right">Cost</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {runs.length === 0 ? (
                                    <TableRow><TableCell colSpan={5} className="py-8 text-center text-muted-foreground">No calls to this number yet.</TableCell></TableRow>
                                ) : runs.map((r) => (
                                    <TableRow key={r.id}>
                                        <TableCell className="whitespace-nowrap">
                                            <Link className="underline-offset-4 hover:underline" href={`/workflow/${r.workflow_id}/run/${r.id}`}>
                                                {formatDateTime(r.created_at)}
                                            </Link>
                                        </TableCell>
                                        <TableCell>{r.workflow_name ?? `Agent ${r.workflow_id}`}</TableCell>
                                        <TableCell className="text-muted-foreground">{r.disposition ?? "—"}</TableCell>
                                        <TableCell className="text-right tabular-nums">{r.call_duration_seconds}s</TableCell>
                                        <TableCell className="text-right">{r.charge_usd != null ? <Money value={r.charge_usd} maxDecimals={4} /> : "—"}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                    {runsPages > 1 && (
                        <div className="flex items-center justify-between text-sm text-muted-foreground">
                            <span>{runsTotal.toLocaleString()} calls</span>
                            <div className="flex items-center gap-2">
                                <Button size="sm" variant="outline" disabled={runsPage <= 1} onClick={() => { setRunsPage(runsPage - 1); void loadRuns(runsPage - 1); }}>Previous</Button>
                                <span className="tabular-nums">Page {runsPage} of {runsPages}</span>
                                <Button size="sm" variant="outline" disabled={runsPage >= runsPages} onClick={() => { setRunsPage(runsPage + 1); void loadRuns(runsPage + 1); }}>Next</Button>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete this contact?</AlertDialogTitle>
                        <AlertDialogDescription>
                            They are removed from every list. Call history is kept. If they are on the do-not-call list, they stay on it.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={remove}>Delete</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
