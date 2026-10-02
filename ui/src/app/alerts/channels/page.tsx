'use client';

import { Loader2, Mail, Plus, Webhook } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import {
    createChannelApiV1AlertsChannelsPost,
    deleteChannelApiV1AlertsChannelsChannelUuidDelete,
    listChannelsApiV1AlertsChannelsGet,
    testChannelApiV1AlertsChannelsChannelUuidTestPost,
} from '@/client/sdk.gen';
import type { AlertChannelResponse, AlertChannelTestResponse } from '@/client/types.gen';
import { CredentialSelector } from '@/components/http';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';

import { parseRecipients } from '../alertForm';
import { AlertsTabs } from '../AlertsTabs';

function describe(channel: AlertChannelResponse): string {
    const config = channel.config as { recipients?: string[]; endpoint_url?: string };
    if (channel.type === 'email') return (config.recipients ?? []).join(', ');
    return config.endpoint_url ?? '';
}

const TEST_RESULT: Record<string, string> = {
    succeeded: 'Delivered. Check the destination.',
    dead_letter: 'Failed',
    pending: 'Sent to the queue, still being tried',
};

export default function AlertChannelsPage() {
    const { loading: authLoading, isAuthenticated } = useAuth();
    const [channels, setChannels] = useState<AlertChannelResponse[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [adding, setAdding] = useState(false);
    const [testing, setTesting] = useState<string | null>(null);
    const [results, setResults] = useState<Record<string, AlertChannelTestResponse>>({});

    // add form
    const [name, setName] = useState('');
    const [type, setType] = useState<'email' | 'webhook'>('webhook');
    const [recipients, setRecipients] = useState('');
    const [url, setUrl] = useState('');
    const [method, setMethod] = useState('POST');
    const [credential, setCredential] = useState('');
    const [formError, setFormError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        const res = await listChannelsApiV1AlertsChannelsGet();
        if (res.error) {
            setError(detailFromError(res.error, 'Could not load channels'));
            return;
        }
        setError(null);
        setChannels(res.data ?? []);
    }, []);

    useEffect(() => {
        if (authLoading || !isAuthenticated) return;
        void load();
    }, [authLoading, isAuthenticated, load]);

    const create = async () => {
        setSaving(true);
        setFormError(null);
        const config =
            type === 'email'
                ? { recipients: parseRecipients(recipients) }
                : { endpoint_url: url.trim(), http_method: method, ...(credential ? { credential_uuid: credential } : {}) };
        const res = await createChannelApiV1AlertsChannelsPost({ body: { name: name.trim(), type, config } });
        setSaving(false);
        if (res.error) {
            setFormError(detailFromError(res.error, 'Could not create the channel'));
            return;
        }
        setAdding(false);
        setName('');
        setRecipients('');
        setUrl('');
        setCredential('');
        await load();
    };

    const test = async (channel: AlertChannelResponse) => {
        setTesting(channel.channel_uuid);
        const res = await testChannelApiV1AlertsChannelsChannelUuidTestPost({ path: { channel_uuid: channel.channel_uuid } });
        setTesting(null);
        if (res.error || !res.data) {
            toast.error(detailFromError(res.error, 'The test could not be sent'));
            return;
        }
        setResults((prev) => ({ ...prev, [channel.channel_uuid]: res.data! }));
    };

    const remove = async (channel: AlertChannelResponse) => {
        if (!window.confirm(`Delete the channel “${channel.name}”? Rules that use it stop notifying here.`)) return;
        const res = await deleteChannelApiV1AlertsChannelsChannelUuidDelete({ path: { channel_uuid: channel.channel_uuid } });
        if (res.error) {
            toast.error(detailFromError(res.error, 'Could not delete the channel'));
            return;
        }
        await load();
    };

    return (
        <div className="container mx-auto px-4 py-8">
            <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold">Alert channels</h1>
                    <p className="mt-1 text-sm text-muted-foreground">Where alerts are sent besides this page.</p>
                </div>
                <Button onClick={() => setAdding(true)}>
                    <Plus className="mr-1 h-4 w-4" aria-hidden /> Add channel
                </Button>
            </div>
            <AlertsTabs />
            {error && (
                <p role="alert" className="mb-4 text-sm text-destructive">
                    {error}
                </p>
            )}

            <Card>
                <CardContent className="p-0">
                    {channels === null ? (
                        <p className="p-8 text-center text-sm text-muted-foreground">Loading…</p>
                    ) : channels.length === 0 ? (
                        <div className="p-10 text-center">
                            <p className="font-medium">No channels yet</p>
                            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                                Add an email list or a webhook, then choose it in a rule. Alerts always appear on the
                                Alerts page too.
                            </p>
                        </div>
                    ) : (
                        <ul className="divide-y">
                            {channels.map((c) => {
                                const result = results[c.channel_uuid];
                                return (
                                    <li key={c.channel_uuid} className="flex flex-wrap items-center gap-3 px-4 py-3">
                                        {c.type === 'email' ? (
                                            <Mail className="h-4 w-4 text-muted-foreground" aria-hidden />
                                        ) : (
                                            <Webhook className="h-4 w-4 text-muted-foreground" aria-hidden />
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium">{c.name}</p>
                                            <p className="truncate text-xs text-muted-foreground">{describe(c)}</p>
                                            {result && (
                                                <p
                                                    className={`mt-1 text-xs ${result.status === 'dead_letter' ? 'text-destructive' : 'text-muted-foreground'}`}
                                                    role="status"
                                                >
                                                    {TEST_RESULT[result.status] ?? result.status}
                                                    {result.error ? `: ${result.error}` : ''}
                                                </p>
                                            )}
                                        </div>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            disabled={testing === c.channel_uuid}
                                            onClick={() => test(c)}
                                        >
                                            {testing === c.channel_uuid && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                                            Send test
                                        </Button>
                                        <Button size="sm" variant="ghost" className="text-destructive" onClick={() => remove(c)}>
                                            Delete
                                        </Button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </CardContent>
            </Card>

            <Dialog open={adding} onOpenChange={(o) => !saving && setAdding(o)}>
                <DialogContent className="sm:max-w-lg">
                    <DialogHeader>
                        <DialogTitle>Add a channel</DialogTitle>
                        <DialogDescription>Choose where alerts should be delivered.</DialogDescription>
                    </DialogHeader>
                    <div className="grid gap-4">
                        <div className="grid gap-2">
                            <Label htmlFor="channel-name">Name</Label>
                            <Input id="channel-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ops team" />
                        </div>
                        <div className="grid gap-2">
                            <Label htmlFor="channel-type">Type</Label>
                            <Select value={type} onValueChange={(v) => setType(v as 'email' | 'webhook')}>
                                <SelectTrigger id="channel-type">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="webhook">Webhook</SelectItem>
                                    <SelectItem value="email">Email</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {type === 'email' ? (
                            <div className="grid gap-2">
                                <Label htmlFor="channel-recipients">Recipients</Label>
                                <Textarea
                                    id="channel-recipients"
                                    value={recipients}
                                    onChange={(e) => setRecipients(e.target.value)}
                                    placeholder="one@company.com, two@company.com"
                                />
                            </div>
                        ) : (
                            <>
                                <div className="grid gap-2">
                                    <Label htmlFor="channel-url">Webhook URL</Label>
                                    <Input id="channel-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
                                </div>
                                <div className="grid gap-2">
                                    <Label htmlFor="channel-method">Method</Label>
                                    <Select value={method} onValueChange={setMethod}>
                                        <SelectTrigger id="channel-method">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="POST">POST</SelectItem>
                                            <SelectItem value="PUT">PUT</SelectItem>
                                            <SelectItem value="PATCH">PATCH</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <CredentialSelector value={credential} onChange={setCredential} />
                            </>
                        )}
                        {formError && (
                            <p role="alert" className="text-sm text-destructive">
                                {formError}
                            </p>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setAdding(false)} disabled={saving}>
                            Cancel
                        </Button>
                        <Button onClick={create} disabled={saving || !name.trim()}>
                            {saving ? 'Adding…' : 'Add channel'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
