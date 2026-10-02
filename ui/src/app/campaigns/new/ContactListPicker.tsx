'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { listContactListsApiV1ContactsListsGet } from '@/client/sdk.gen';
import type { ContactListResponse } from '@/client/types.gen';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

/**
 * Choose a saved contact list as a campaign's data source. The value is the
 * list's uuid, which is what the campaign stores as its source.
 */
export function ContactListPicker({ value, onChange }: { value: string; onChange: (listUuid: string) => void }) {
    const [lists, setLists] = useState<ContactListResponse[] | null>(null);

    useEffect(() => {
        let cancelled = false;
        void listContactListsApiV1ContactsListsGet().then((res) => {
            if (!cancelled) setLists(res.data ?? []);
        });
        return () => { cancelled = true; };
    }, []);

    return (
        <div className="space-y-2">
            <Label htmlFor="contact-list">Contact list</Label>
            {lists === null ? (
                <p className="text-sm text-muted-foreground">Loading lists…</p>
            ) : lists.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                    You have no contact lists yet.{' '}
                    <Link href="/contacts" className="underline">Import contacts</Link> and choose a list, then come back.
                </p>
            ) : (
                <>
                    <Select value={value || undefined} onValueChange={onChange}>
                        <SelectTrigger id="contact-list">
                            <SelectValue placeholder="Choose a list" />
                        </SelectTrigger>
                        <SelectContent>
                            {lists.map((l) => (
                                <SelectItem key={l.list_uuid} value={l.list_uuid} disabled={!l.contact_count}>
                                    {l.name} ({(l.contact_count ?? 0).toLocaleString()} contact{l.contact_count === 1 ? '' : 's'})
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <p className="text-sm text-muted-foreground">
                        Everyone in the list is called once, except numbers on your do-not-call list.
                    </p>
                </>
            )}
        </div>
    );
}
