"use client";

import { Search, Settings2, Star } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { listOrganizationPhoneNumbersApiV1OrganizationsPhoneNumbersGet } from "@/client/sdk.gen";
import type { OrgPhoneNumberResponse } from "@/client/types.gen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { matchesPhoneNumber } from "./utils";

/**
 * Every phone number in the organization on one page: which provider account
 * owns it, and which agent answers it.
 *
 * Read-only on purpose. Adding, assigning and removing numbers stay on each
 * provider account's page, which validates the number with the provider and
 * checks that two numbers do not route the same inbound call. Repeating that here
 * would be a second place for it to disagree.
 */
export default function PhoneNumbersPage() {
    const { user, redirectToLogin, loading: authLoading } = useAuth();
    const [numbers, setNumbers] = useState<OrgPhoneNumberResponse[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [query, setQuery] = useState("");

    useEffect(() => {
        if (!authLoading && !user) redirectToLogin();
    }, [authLoading, user, redirectToLogin]);

    useEffect(() => {
        if (authLoading || !user) return;
        let cancelled = false;
        void (async () => {
            try {
                const res = await listOrganizationPhoneNumbersApiV1OrganizationsPhoneNumbersGet();
                if (cancelled) return;
                if (res.error || !res.data) {
                    setError(detailFromError(res.error, "Could not load phone numbers"));
                    return;
                }
                setNumbers(res.data.phone_numbers);
            } catch (e) {
                if (!cancelled) setError(detailFromError(e, "Could not load phone numbers"));
            }
        })();
        return () => { cancelled = true; };
    }, [authLoading, user]);

    const shown = useMemo(() => (numbers ?? []).filter((n) => matchesPhoneNumber(n, query)), [numbers, query]);
    const answering = (numbers ?? []).filter((n) => n.is_active && n.inbound_workflow_id != null).length;

    if (authLoading || !user) {
        return <div className="container mx-auto px-4 py-8"><Skeleton className="h-64 w-full" /></div>;
    }

    return (
        <div className="container mx-auto space-y-6 px-4 py-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold">Phone numbers</h1>
                    <p className="text-muted-foreground">
                        Every number across all your providers, and the agent that answers it.
                    </p>
                </div>
                <Button variant="outline" asChild>
                    <Link href="/telephony-configurations"><Settings2 /> Manage providers and numbers</Link>
                </Button>
            </div>

            {error ? (
                <p className="text-sm text-destructive">{error}</p>
            ) : (
                <Card>
                    <CardContent className="space-y-4 pt-6">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="relative min-w-[240px] max-w-sm flex-1">
                                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    placeholder="Search number, label, agent or provider"
                                    aria-label="Search phone numbers"
                                    className="pl-8"
                                />
                            </div>
                            {numbers && numbers.length > 0 && (
                                <p className="text-sm text-muted-foreground">
                                    {numbers.length} number{numbers.length === 1 ? "" : "s"} · {answering} answering calls
                                </p>
                            )}
                        </div>

                        <div className="overflow-x-auto rounded-md border">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Number</TableHead>
                                        <TableHead>Provider</TableHead>
                                        <TableHead>Answered by</TableHead>
                                        <TableHead>Trunk</TableHead>
                                        <TableHead>Status</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {numbers === null ? (
                                        <TableRow><TableCell colSpan={5}><Skeleton className="h-6 w-full" /></TableCell></TableRow>
                                    ) : numbers.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                                                No phone numbers yet.{" "}
                                                <Link href="/telephony-configurations" className="underline">Connect a provider</Link> to add one.
                                            </TableCell>
                                        </TableRow>
                                    ) : shown.length === 0 ? (
                                        <TableRow><TableCell colSpan={5} className="py-10 text-center text-muted-foreground">No numbers match.</TableCell></TableRow>
                                    ) : shown.map((n) => (
                                        <TableRow key={n.id}>
                                            <TableCell>
                                                <div className="font-medium tabular-nums">{n.address}</div>
                                                {n.label && <div className="text-xs text-muted-foreground">{n.label}</div>}
                                            </TableCell>
                                            <TableCell>
                                                <Link
                                                    href={`/telephony-configurations/${n.telephony_configuration_id}`}
                                                    className="hover:underline"
                                                >
                                                    {n.telephony_configuration_name}
                                                </Link>
                                                <div className="text-xs capitalize text-muted-foreground">{n.telephony_provider}</div>
                                            </TableCell>
                                            <TableCell>
                                                {n.inbound_workflow_id ? (
                                                    <Link
                                                        href={`/workflow/${n.inbound_workflow_id}`}
                                                        className="inline-flex items-center gap-1 hover:underline"
                                                    >
                                                        <span className="text-muted-foreground">#{n.inbound_workflow_id}</span>
                                                        <span className="max-w-[200px] truncate" title={n.inbound_workflow_name ?? undefined}>
                                                            {n.inbound_workflow_name ?? "Agent"}
                                                        </span>
                                                    </Link>
                                                ) : (
                                                    <span className="text-muted-foreground">Unassigned</span>
                                                )}
                                            </TableCell>
                                            <TableCell className="text-muted-foreground">{n.telephony_trunk_name ?? "—"}</TableCell>
                                            <TableCell>
                                                <div className="flex flex-wrap items-center gap-1.5">
                                                    {n.telephony_configuration_inactive ? (
                                                        <Badge variant="outline">Provider inactive</Badge>
                                                    ) : n.is_active ? (
                                                        <Badge variant="success">Active</Badge>
                                                    ) : (
                                                        <Badge variant="outline">Inactive</Badge>
                                                    )}
                                                    {n.is_default_caller_id && (
                                                        <Badge className="gap-1"><Star className="h-3 w-3 fill-current" /> Default caller</Badge>
                                                    )}
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
