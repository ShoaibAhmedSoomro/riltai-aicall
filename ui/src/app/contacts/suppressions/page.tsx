"use client";

import { ArrowLeft, Search, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
    addSuppressionsApiV1ContactsSuppressionsPost,
    getPreferencesApiV1OrganizationsPreferencesGet,
    listSuppressionsApiV1ContactsSuppressionsGet,
    removeSuppressionApiV1ContactsSuppressionsDelete,
    savePreferencesApiV1OrganizationsPreferencesPut,
} from "@/client/sdk.gen";
import type { SuppressionCreateResponse, SuppressionResponse } from "@/client/types.gen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dateTime";

import { ContactImportDialog } from "../ContactImportDialog";
import { parsePhoneList } from "../utils";

const SOURCE_LABEL: Record<string, string> = {
    manual: "Added by hand",
    csv: "Imported",
    call_disposition: "Call outcome",
    api: "API",
};
const PAGE_SIZE = 50;

export default function SuppressionsPage() {
    const { user, redirectToLogin, loading: authLoading } = useAuth();
    const [rows, setRows] = useState<SuppressionResponse[] | null>(null);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(1);
    const [page, setPage] = useState(1);
    const [search, setSearch] = useState("");
    const [q, setQ] = useState("");
    const [importOpen, setImportOpen] = useState(false);

    useEffect(() => {
        if (!authLoading && !user) redirectToLogin();
    }, [authLoading, user, redirectToLogin]);

    useEffect(() => {
        const t = setTimeout(() => { setQ(search.trim()); setPage(1); }, 300);
        return () => clearTimeout(t);
    }, [search]);

    const load = useCallback(async () => {
        const res = await listSuppressionsApiV1ContactsSuppressionsGet({ query: { q: q || undefined, page, limit: PAGE_SIZE } });
        if (res.error || !res.data) return toast.error(detailFromError(res.error, "Could not load the list"));
        setRows(res.data.suppressions);
        setTotal(res.data.total_count);
        setPages(Math.max(1, res.data.total_pages));
    }, [q, page]);

    useEffect(() => { if (user) void load(); }, [user, load]);

    async function remove(number: string) {
        const res = await removeSuppressionApiV1ContactsSuppressionsDelete({ query: { phone_e164: number } });
        if (res.error) return toast.error(detailFromError(res.error, "Could not remove it"));
        toast.success("Removed. This number can be called again.");
        void load();
    }

    if (authLoading || !user) return <div className="container mx-auto px-4 py-8"><Skeleton className="h-64 w-full" /></div>;

    return (
        <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
            <Button variant="ghost" size="sm" asChild><Link href="/contacts"><ArrowLeft /> Contacts</Link></Button>
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold">Do not call</h1>
                    <p className="text-muted-foreground">
                        Numbers your agents will never dial. Enforced on campaigns, the API trigger and test calls.
                    </p>
                </div>
                <Button variant="outline" onClick={() => setImportOpen(true)}><Upload /> Import a file</Button>
            </div>

            <AddNumbers onAdded={() => void load()} />
            <AutoOptOut />

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">The list</CardTitle>
                    <CardDescription>
                        A number stays here even if its contact is deleted, and applies even if it was never a contact.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="relative max-w-sm">
                        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search numbers" aria-label="Search numbers" className="pl-8" />
                    </div>
                    <div className="overflow-x-auto rounded-md border">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Number</TableHead>
                                    <TableHead>How it was added</TableHead>
                                    <TableHead>Reason</TableHead>
                                    <TableHead>Added</TableHead>
                                    <TableHead className="w-12" />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rows === null ? (
                                    <TableRow><TableCell colSpan={5}><Skeleton className="h-6 w-full" /></TableCell></TableRow>
                                ) : rows.length === 0 ? (
                                    <TableRow><TableCell colSpan={5} className="py-10 text-center text-muted-foreground">{q ? "No numbers match." : "Nothing on the list yet."}</TableCell></TableRow>
                                ) : rows.map((r) => (
                                    <TableRow key={r.phone_e164}>
                                        <TableCell className="tabular-nums">{r.phone_e164}</TableCell>
                                        <TableCell><Badge variant="secondary">{SOURCE_LABEL[r.source] ?? r.source}</Badge></TableCell>
                                        <TableCell className="text-muted-foreground">{r.reason ?? "—"}</TableCell>
                                        <TableCell className="whitespace-nowrap text-muted-foreground">{r.created_at ? formatDateTime(r.created_at) : "—"}</TableCell>
                                        <TableCell>
                                            <Button variant="ghost" size="icon" aria-label={`Remove ${r.phone_e164}`} onClick={() => remove(r.phone_e164)}><Trash2 /></Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                    <div className="flex items-center justify-between text-sm text-muted-foreground">
                        <span>{total.toLocaleString()} number{total === 1 ? "" : "s"}</span>
                        <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                            <span className="tabular-nums">Page {page} of {pages}</span>
                            <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <ContactImportDialog open={importOpen} onOpenChange={setImportOpen} onDone={() => void load()} mode="suppression" />
        </div>
    );
}

function AddNumbers({ onAdded }: { onAdded: () => void }) {
    const [text, setText] = useState("");
    const [country, setCountry] = useState("");
    const [reason, setReason] = useState("");
    const [saving, setSaving] = useState(false);
    const [result, setResult] = useState<SuppressionCreateResponse | null>(null);

    async function add() {
        setSaving(true);
        setResult(null);
        try {
            const res = await addSuppressionsApiV1ContactsSuppressionsPost({
                body: { phone_numbers: parsePhoneList(text), country_hint: country.trim() || null, reason: reason.trim() || null },
            });
            if (res.error || !res.data) return toast.error(detailFromError(res.error, "Could not add the numbers"));
            setResult(res.data);
            // Keep only what was refused, so it can be fixed and sent again.
            setText((res.data.invalid ?? []).join("\n"));
            onAdded();
        } finally {
            setSaving(false);
        }
    }

    const count = parsePhoneList(text).length;
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-base">Add numbers</CardTitle>
                <CardDescription>One per line, or separated by commas. Up to 1,000 at a time; use Import a file for more.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"+971501234567\n+14155551234"} aria-label="Numbers to add" />
                <div className="flex flex-wrap items-end gap-3">
                    <div className="space-y-1.5">
                        <Label htmlFor="s-country" className="text-xs">Country (for local numbers)</Label>
                        <Input id="s-country" value={country} maxLength={2} placeholder="AE" className="w-20 uppercase" onChange={(e) => setCountry(e.target.value.toUpperCase())} />
                    </div>
                    <div className="min-w-[200px] flex-1 space-y-1.5">
                        <Label htmlFor="s-reason" className="text-xs">Reason (optional)</Label>
                        <Input id="s-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Asked not to be called" />
                    </div>
                    <Button onClick={add} disabled={saving || count === 0}>{saving ? "Adding…" : `Add ${count || ""} number${count === 1 ? "" : "s"}`}</Button>
                </div>
                {result && (
                    <p className="text-sm text-muted-foreground" role="status">
                        {result.added} added
                        {result.already_suppressed > 0 && ` · ${result.already_suppressed} already on the list`}
                        {(result.invalid ?? []).length > 0 && ` · ${(result.invalid ?? []).length} not valid phone numbers (left in the box so you can fix them)`}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

/** Which call outcomes mean "do not call this person again". */
function AutoOptOut() {
    const [codes, setCodes] = useState("");
    const [saved, setSaved] = useState("");
    const [loaded, setLoaded] = useState(false);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        void getPreferencesApiV1OrganizationsPreferencesGet().then((res) => {
            const value = (res.data?.do_not_call_dispositions ?? []).join(", ");
            setCodes(value);
            setSaved(value);
            setLoaded(true);
        });
    }, []);

    async function save() {
        setSaving(true);
        try {
            const list = codes.split(",").map((c) => c.trim()).filter(Boolean);
            const res = await savePreferencesApiV1OrganizationsPreferencesPut({ body: { do_not_call_dispositions: list } });
            if (res.error) return toast.error(detailFromError(res.error, "Could not save"));
            const value = list.join(", ");
            setCodes(value);
            setSaved(value);
            toast.success("Saved. It applies to calls that finish from now on.");
        } finally {
            setSaving(false);
        }
    }

    if (!loaded) return null;
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-base">Automatic opt-outs</CardTitle>
                <CardDescription>
                    When a call ends with one of these outcomes, its number is added to the list for you. Use the outcome
                    codes your agents already produce, separated by commas.
                </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-end gap-3">
                <div className="min-w-[240px] flex-1 space-y-1.5">
                    <Label htmlFor="o-codes" className="text-xs">Outcome codes</Label>
                    <Input id="o-codes" value={codes} onChange={(e) => setCodes(e.target.value)} placeholder="e.g. do_not_call, opted_out" />
                </div>
                <Button onClick={save} disabled={saving || codes === saved}>{saving ? "Saving…" : "Save"}</Button>
            </CardContent>
        </Card>
    );
}
