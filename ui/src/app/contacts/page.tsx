"use client";

import { Ban, CalendarPlus, ListPlus, PhoneOff, Plus, Search, Trash2, Upload, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { StatCard } from "@/app/overview/components/StatCard";
import {
    addListMembersApiV1ContactsListsListUuidMembersPost,
    addSuppressionsApiV1ContactsSuppressionsPost,
    bulkDeleteContactsApiV1ContactsBulkDeletePost,
    createContactApiV1ContactsPost,
    getContactsSummaryApiV1ContactsSummaryGet,
    listContactListsApiV1ContactsListsGet,
    listContactsApiV1ContactsGet,
} from "@/client/sdk.gen";
import type { ContactListResponse, ContactResponse, ContactSummaryResponse } from "@/client/types.gen";
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
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dateTime";

import { ContactImportDialog } from "./ContactImportDialog";
import { contactName } from "./utils";

const ALL = "all";
const PAGE_SIZE = 50;

type Sort = "created_at" | "name" | "last_called_at" | "call_count";

export default function ContactsPage() {
    const { user, redirectToLogin, loading: authLoading } = useAuth();
    // Arrive filtered to one list when linked from the Lists page.
    const initialList = useSearchParams().get("list");

    const [summary, setSummary] = useState<ContactSummaryResponse | null>(null);
    const [lists, setLists] = useState<ContactListResponse[]>([]);
    const [contacts, setContacts] = useState<ContactResponse[]>([]);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [search, setSearch] = useState("");
    const [q, setQ] = useState("");
    const [listFilter, setListFilter] = useState(initialList ?? ALL);
    const [suppressedFilter, setSuppressedFilter] = useState(ALL);
    const [sort, setSort] = useState<Sort>("created_at");
    const [page, setPage] = useState(1);
    const [selected, setSelected] = useState<Set<string>>(new Set());

    const [addOpen, setAddOpen] = useState(false);
    const [importOpen, setImportOpen] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);

    useEffect(() => {
        if (!authLoading && !user) redirectToLogin();
    }, [authLoading, user, redirectToLogin]);

    // Search waits for a pause in typing, so each keystroke is not a request.
    useEffect(() => {
        const t = setTimeout(() => { setQ(search.trim()); setPage(1); }, 300);
        return () => clearTimeout(t);
    }, [search]);

    const loadSide = useCallback(async () => {
        const [s, l] = await Promise.all([
            getContactsSummaryApiV1ContactsSummaryGet(),
            listContactListsApiV1ContactsListsGet(),
        ]);
        if (s.data) setSummary(s.data);
        if (l.data) setLists(l.data);
    }, []);

    const loadContacts = useCallback(async () => {
        setLoading(true);
        try {
            const res = await listContactsApiV1ContactsGet({
                query: {
                    q: q || undefined,
                    list_uuid: listFilter === ALL ? undefined : listFilter,
                    suppressed: suppressedFilter === ALL ? undefined : suppressedFilter === "yes",
                    sort,
                    page,
                    limit: PAGE_SIZE,
                },
            });
            if (res.error || !res.data) {
                setError(detailFromError(res.error, "Could not load contacts"));
                return;
            }
            setError(null);
            setContacts(res.data.contacts);
            setTotal(res.data.total_count);
            setTotalPages(Math.max(1, res.data.total_pages));
            setSelected(new Set());
        } catch (e) {
            setError(detailFromError(e, "Could not load contacts"));
        } finally {
            setLoading(false);
        }
    }, [q, listFilter, suppressedFilter, sort, page]);

    useEffect(() => { if (user) void loadSide(); }, [user, loadSide]);
    useEffect(() => { if (user) void loadContacts(); }, [user, loadContacts]);

    function refresh() {
        void loadSide();
        void loadContacts();
    }

    const chosen = contacts.filter((c) => selected.has(c.contact_uuid));
    const allOnPage = contacts.length > 0 && contacts.every((c) => selected.has(c.contact_uuid));

    async function bulkAddToList(listUuid: string) {
        const res = await addListMembersApiV1ContactsListsListUuidMembersPost({
            path: { list_uuid: listUuid },
            body: { contact_uuids: [...selected] },
        });
        if (res.error) return toast.error(detailFromError(res.error, "Could not add to the list"));
        toast.success(`Added ${res.data?.affected ?? 0} to the list`);
        refresh();
    }

    async function bulkSuppress() {
        const res = await addSuppressionsApiV1ContactsSuppressionsPost({
            body: { phone_numbers: chosen.map((c) => c.phone_e164), reason: "Added from Contacts" },
        });
        if (res.error) return toast.error(detailFromError(res.error, "Could not update the list"));
        toast.success(`${res.data?.added ?? 0} added to the do-not-call list`);
        refresh();
    }

    async function bulkDelete() {
        const res = await bulkDeleteContactsApiV1ContactsBulkDeletePost({ body: { contact_uuids: [...selected] } });
        setConfirmDelete(false);
        if (res.error) return toast.error(detailFromError(res.error, "Could not delete"));
        toast.success(`Deleted ${res.data?.affected ?? 0} contact(s)`);
        refresh();
    }

    if (authLoading || !user) {
        return (
            <div className="container mx-auto px-4 py-8 space-y-4">
                <Skeleton className="h-12 w-64" />
                <Skeleton className="h-64 w-full" />
            </div>
        );
    }

    return (
        <div className="container mx-auto space-y-6 px-4 py-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold">Contacts</h1>
                    <p className="text-muted-foreground">
                        The people your agents call. A number is one contact however it was written.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button variant="outline" asChild><Link href="/contacts/lists"><ListPlus /> Lists</Link></Button>
                    <Button variant="outline" asChild><Link href="/contacts/suppressions"><PhoneOff /> Do not call</Link></Button>
                    <Button variant="outline" onClick={() => setImportOpen(true)}><Upload /> Import CSV</Button>
                    <Button onClick={() => setAddOpen(true)}><Plus /> Add contact</Button>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatCard label="Contacts" icon={Users} value={(summary?.total ?? 0).toLocaleString()} loading={!summary} />
                <StatCard label="Do not call" icon={PhoneOff} value={(summary?.suppressed ?? 0).toLocaleString()} loading={!summary} href="/contacts/suppressions" />
                <StatCard label="Never called" icon={UserRound} value={(summary?.never_called ?? 0).toLocaleString()} loading={!summary} />
                <StatCard label="Added this month" icon={CalendarPlus} value={(summary?.added_this_month ?? 0).toLocaleString()} loading={!summary} />
            </div>

            <Card>
                <CardContent className="space-y-4 pt-6">
                    <div className="flex flex-wrap items-center gap-3">
                        <div className="relative min-w-[220px] flex-1">
                            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Search name, phone or email"
                                aria-label="Search contacts"
                                className="pl-8"
                            />
                        </div>
                        <Select value={listFilter} onValueChange={(v) => { setListFilter(v); setPage(1); }}>
                            <SelectTrigger className="w-44" aria-label="Filter by list"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value={ALL}>All lists</SelectItem>
                                {lists.map((l) => <SelectItem key={l.list_uuid} value={l.list_uuid}>{l.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={suppressedFilter} onValueChange={(v) => { setSuppressedFilter(v); setPage(1); }}>
                            <SelectTrigger className="w-40" aria-label="Filter by do-not-call"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value={ALL}>Everyone</SelectItem>
                                <SelectItem value="no">Can be called</SelectItem>
                                <SelectItem value="yes">Do not call</SelectItem>
                            </SelectContent>
                        </Select>
                        <Select value={sort} onValueChange={(v) => { setSort(v as Sort); setPage(1); }}>
                            <SelectTrigger className="w-44" aria-label="Sort"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="created_at">Newest first</SelectItem>
                                <SelectItem value="name">Name</SelectItem>
                                <SelectItem value="last_called_at">Last called</SelectItem>
                                <SelectItem value="call_count">Most called</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {selected.size > 0 && (
                        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
                            <span className="text-sm font-medium">{selected.size} selected</span>
                            <Select value={undefined} onValueChange={bulkAddToList}>
                                <SelectTrigger className="h-8 w-44" aria-label="Add selected to a list"><SelectValue placeholder="Add to list…" /></SelectTrigger>
                                <SelectContent>
                                    {lists.length === 0 && <SelectItem value="__none" disabled>No lists yet</SelectItem>}
                                    {lists.map((l) => <SelectItem key={l.list_uuid} value={l.list_uuid}>{l.name}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <Button size="sm" variant="outline" onClick={bulkSuppress}><Ban /> Do not call</Button>
                            <Button size="sm" variant="outline" onClick={() => setConfirmDelete(true)}><Trash2 /> Delete</Button>
                        </div>
                    )}

                    {error ? (
                        <p className="text-sm text-destructive">{error}</p>
                    ) : (
                        <div className="overflow-x-auto rounded-md border">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-10">
                                            <Checkbox
                                                checked={allOnPage}
                                                onCheckedChange={(v) => setSelected(v === true ? new Set(contacts.map((c) => c.contact_uuid)) : new Set())}
                                                aria-label="Select all on this page"
                                            />
                                        </TableHead>
                                        <TableHead>Name</TableHead>
                                        <TableHead>Phone</TableHead>
                                        <TableHead>Email</TableHead>
                                        <TableHead>Last called</TableHead>
                                        <TableHead>Last outcome</TableHead>
                                        <TableHead className="text-right">Calls</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {loading && contacts.length === 0 ? (
                                        <TableRow><TableCell colSpan={7}><Skeleton className="h-6 w-full" /></TableCell></TableRow>
                                    ) : contacts.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                                                {q || listFilter !== ALL || suppressedFilter !== ALL
                                                    ? "No contacts match those filters."
                                                    : "No contacts yet. Import a CSV or add one."}
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        contacts.map((c) => (
                                            <TableRow key={c.contact_uuid} data-state={selected.has(c.contact_uuid) ? "selected" : undefined}>
                                                <TableCell>
                                                    <Checkbox
                                                        checked={selected.has(c.contact_uuid)}
                                                        onCheckedChange={(v) => setSelected((prev) => {
                                                            const next = new Set(prev);
                                                            if (v === true) next.add(c.contact_uuid); else next.delete(c.contact_uuid);
                                                            return next;
                                                        })}
                                                        aria-label={`Select ${contactName(c) ?? c.phone_number}`}
                                                    />
                                                </TableCell>
                                                <TableCell>
                                                    <Link href={`/contacts/${c.contact_uuid}`} className="font-medium underline-offset-4 hover:underline">
                                                        {contactName(c) ?? <span className="text-muted-foreground">No name</span>}
                                                    </Link>
                                                    {c.suppressed && <Badge variant="destructive" className="ml-2">Do not call</Badge>}
                                                </TableCell>
                                                <TableCell className="tabular-nums">{c.phone_number}</TableCell>
                                                <TableCell className="text-muted-foreground">{c.email ?? "—"}</TableCell>
                                                <TableCell className="whitespace-nowrap text-muted-foreground">
                                                    {c.last_called_at ? formatDateTime(c.last_called_at) : "Never"}
                                                </TableCell>
                                                <TableCell className="text-muted-foreground">{c.last_disposition ?? "—"}</TableCell>
                                                <TableCell className="text-right tabular-nums">{c.call_count}</TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </div>
                    )}

                    <div className="flex items-center justify-between text-sm text-muted-foreground">
                        <span>{total.toLocaleString()} contact{total === 1 ? "" : "s"}</span>
                        <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                            <span className="tabular-nums">Page {page} of {totalPages}</span>
                            <Button size="sm" variant="outline" disabled={page >= totalPages || loading} onClick={() => setPage((p) => p + 1)}>Next</Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <AddContactDialog open={addOpen} onOpenChange={setAddOpen} onCreated={refresh} />
            <ContactImportDialog open={importOpen} onOpenChange={setImportOpen} onDone={refresh} lists={lists} />

            <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete {selected.size} contact{selected.size === 1 ? "" : "s"}?</AlertDialogTitle>
                        <AlertDialogDescription>
                            They are removed from every list. Call history is kept. Anyone on the do-not-call list stays on it.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={bulkDelete}>Delete</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

function AddContactDialog({ open, onOpenChange, onCreated }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onCreated: () => void;
}) {
    const [phone, setPhone] = useState("");
    const [country, setCountry] = useState("");
    const [first, setFirst] = useState("");
    const [last, setLast] = useState("");
    const [email, setEmail] = useState("");
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function save() {
        setSaving(true);
        setError(null);
        try {
            const res = await createContactApiV1ContactsPost({
                body: {
                    phone_number: phone,
                    country_hint: country.trim() || null,
                    first_name: first.trim() || null,
                    last_name: last.trim() || null,
                    email: email.trim() || null,
                },
            });
            if (res.error) {
                setError(detailFromError(res.error, "Could not add the contact"));
                return;
            }
            toast.success("Contact added");
            setPhone(""); setCountry(""); setFirst(""); setLast(""); setEmail("");
            onOpenChange(false);
            onCreated();
        } finally {
            setSaving(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Add a contact</DialogTitle>
                    <DialogDescription>Only the phone number is required.</DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div className="grid grid-cols-[1fr_5rem] gap-3">
                        <div className="space-y-1.5">
                            <Label htmlFor="ac-phone" className="text-xs">Phone number *</Label>
                            <Input id="ac-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+971 50 123 4567" />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="ac-country" className="text-xs">Country</Label>
                            <Input id="ac-country" value={country} maxLength={2} placeholder="AE" className="uppercase" onChange={(e) => setCountry(e.target.value.toUpperCase())} />
                        </div>
                    </div>
                    <p className="text-xs text-muted-foreground">Include the country code, or give the country for a number written locally.</p>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                            <Label htmlFor="ac-first" className="text-xs">First name</Label>
                            <Input id="ac-first" value={first} onChange={(e) => setFirst(e.target.value)} />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="ac-last" className="text-xs">Last name</Label>
                            <Input id="ac-last" value={last} onChange={(e) => setLast(e.target.value)} />
                        </div>
                    </div>
                    <div className="space-y-1.5">
                        <Label htmlFor="ac-email" className="text-xs">Email</Label>
                        <Input id="ac-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                    </div>
                    {error && <p className="text-sm text-destructive">{error}</p>}
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button onClick={save} disabled={saving || !phone.trim()}>{saving ? "Adding…" : "Add contact"}</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
