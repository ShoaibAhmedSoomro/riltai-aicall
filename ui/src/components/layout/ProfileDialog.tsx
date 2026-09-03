'use client';

import { Check, Copy, Loader2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { updateProfileApiV1AuthProfilePatch } from '@/client/sdk.gen';
import type { UserProfileFields } from '@/client/types.gen';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';
import { AVATAR_COLOR_CLASS, AVATAR_COLORS, avatarInitials } from '@/lib/avatar';
import { getLocalTimezone } from '@/lib/dateTime';
import { cn } from '@/lib/utils';

/**
 * Edit the signed-in user's own details.
 *
 * Only rendered for the local auth provider. The hosted provider owns its
 * users' identities and ships a far more complete account UI at
 * /handler/account-settings, so the profile menu links there instead of
 * reimplementing a worse version.
 *
 * Three tabs rather than one long form, because the fields have different
 * consequences: Profile is cosmetic and safe, Security changes credentials, and
 * Account is read-only facts you sometimes need to quote in a support thread.
 *
 * Two behaviours that are easy to get wrong and are covered by tests:
 *
 * 1. Only changed fields are sent, so the server can tell "clear the job title"
 *    apart from "leave it alone".
 * 2. The OSS session is a write-once httpOnly cookie read at login and the auth
 *    context exposes no refresh, so a successful save re-POSTs
 *    /api/auth/session with the FRESH token. The JWT embeds the email, so after
 *    an email change the old token describes an address that no longer resolves.
 */

/** A curated shortlist plus the browser's own zone, rather than all ~600. */
const TIMEZONE_CHOICES = [
    'UTC',
    'Asia/Dubai',
    'Asia/Karachi',
    'Asia/Kolkata',
    'Asia/Singapore',
    'Europe/London',
    'Europe/Berlin',
    'America/New_York',
    'America/Chicago',
    'America/Los_Angeles',
    'Australia/Sydney',
];

export function ProfileDialog({
    open,
    onOpenChange,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}) {
    const { user } = useAuth();
    const current = user as
        | { id?: string; name?: string; email?: string; profile?: UserProfileFields; created_at?: string; is_superuser?: boolean }
        | null;
    const storedProfile = current?.profile ?? {};

    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [jobTitle, setJobTitle] = useState('');
    const [phone, setPhone] = useState('');
    const [timezone, setTimezone] = useState('');
    const [avatarColor, setAvatarColor] = useState('');
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [saving, setSaving] = useState(false);
    const [copied, setCopied] = useState(false);

    // Re-seed on every open so a cancelled edit does not leak into the next one.
    useEffect(() => {
        if (!open) return;
        setName(current?.name ?? '');
        setEmail(current?.email ?? '');
        setJobTitle(storedProfile.job_title ?? '');
        setPhone(storedProfile.phone ?? '');
        setTimezone(storedProfile.timezone ?? '');
        setAvatarColor(storedProfile.avatar_color ?? 'slate');
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
        setCopied(false);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const zoneChoices = useMemo(() => {
        const local = getLocalTimezone();
        const stored = storedProfile.timezone;
        return [...new Set([...(stored ? [stored] : []), local, ...TIMEZONE_CHOICES])];
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const changingPassword = newPassword.length > 0;
    const profileChanged =
        (storedProfile.job_title ?? '') !== jobTitle ||
        (storedProfile.phone ?? '') !== phone ||
        (storedProfile.timezone ?? '') !== timezone ||
        (storedProfile.avatar_color ?? 'slate') !== avatarColor;
    const nameChanged = (current?.name ?? '') !== name;
    const emailChanged = (current?.email ?? '') !== email;
    const hasChanges = nameChanged || emailChanged || profileChanged || changingPassword;

    async function copyId() {
        try {
            await navigator.clipboard.writeText(String(current?.id ?? ''));
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            toast.error('Could not copy to the clipboard');
        }
    }

    async function save() {
        if (changingPassword && newPassword !== confirmPassword) {
            toast.error('The new passwords do not match');
            return;
        }
        if (changingPassword && !currentPassword) {
            toast.error('Enter your current password to set a new one');
            return;
        }

        setSaving(true);
        try {
            const response = await updateProfileApiV1AuthProfilePatch({
                body: {
                    ...(nameChanged ? { name } : {}),
                    ...(emailChanged ? { email } : {}),
                    ...(changingPassword
                        ? { current_password: currentPassword, new_password: newPassword }
                        : {}),
                    // The blob is sent whole when any part of it changes: it is
                    // small, and replacing it avoids a merge protocol for
                    // something this form always holds in full.
                    ...(profileChanged
                        ? {
                              profile: {
                                  job_title: jobTitle || null,
                                  phone: phone || null,
                                  timezone: timezone || null,
                                  avatar_color: avatarColor || null,
                              },
                          }
                        : {}),
                },
            });

            // The generated client resolves rather than throwing on 4xx/5xx.
            if (response.error || !response.data) {
                toast.error(detailFromError(response.error, 'Could not save your profile'));
                return;
            }

            const stored = await fetch('/api/auth/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: response.data.token, user: response.data.user }),
            });
            if (!stored.ok) {
                toast.error('Saved, but the session could not be refreshed. Please sign in again.');
                return;
            }

            toast.success('Profile updated');
            onOpenChange(false);
            // Blunt, but the auth context has no update path and this happens
            // once per edit.
            window.location.reload();
        } catch {
            toast.error('Could not reach the server');
        } finally {
            setSaving(false);
        }
    }

    const initials = avatarInitials(name, email);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>Profile settings</DialogTitle>
                    <DialogDescription>
                        Your details, the credentials you sign in with, and how reports are dated.
                    </DialogDescription>
                </DialogHeader>

                <Tabs defaultValue="profile">
                    <TabsList className="grid w-full grid-cols-3">
                        <TabsTrigger value="profile">Profile</TabsTrigger>
                        <TabsTrigger value="security">Security</TabsTrigger>
                        <TabsTrigger value="account">Account</TabsTrigger>
                    </TabsList>

                    {/* ── Profile: cosmetic and safe */}
                    <TabsContent value="profile" className="space-y-4 pt-4">
                        <div className="flex items-center gap-4">
                            <span
                                aria-hidden
                                className={cn(
                                    'flex size-14 shrink-0 items-center justify-center rounded-full text-lg font-semibold',
                                    AVATAR_COLOR_CLASS[avatarColor] ?? AVATAR_COLOR_CLASS.slate,
                                )}
                            >
                                {initials}
                            </span>
                            <div className="min-w-0">
                                <p className="text-sm font-medium">Avatar colour</p>
                                <p className="mb-2 text-xs text-muted-foreground">
                                    Initials are used; no image is stored.
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                    {AVATAR_COLORS.map((colour) => (
                                        <button
                                            key={colour}
                                            type="button"
                                            aria-label={`Use the ${colour} avatar`}
                                            aria-pressed={avatarColor === colour}
                                            onClick={() => setAvatarColor(colour)}
                                            className={cn(
                                                'size-6 rounded-full ring-offset-2 ring-offset-background transition-all',
                                                AVATAR_COLOR_CLASS[colour],
                                                avatarColor === colour && 'ring-2 ring-ring',
                                            )}
                                        />
                                    ))}
                                </div>
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <Label htmlFor="profile-name">Display name</Label>
                            <Input
                                id="profile-name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder="Your name"
                                autoComplete="name"
                            />
                        </div>

                        <div className="grid gap-4 sm:grid-cols-2">
                            <div className="space-y-1.5">
                                <Label htmlFor="profile-title">Job title</Label>
                                <Input
                                    id="profile-title"
                                    value={jobTitle}
                                    onChange={(e) => setJobTitle(e.target.value)}
                                    placeholder="Operations Manager"
                                    autoComplete="organization-title"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="profile-phone">Phone</Label>
                                <Input
                                    id="profile-phone"
                                    value={phone}
                                    onChange={(e) => setPhone(e.target.value)}
                                    placeholder="+971 50 000 0000"
                                    autoComplete="tel"
                                />
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <Label htmlFor="profile-timezone">Reporting timezone</Label>
                            <Select value={timezone || 'inherit'} onValueChange={(v) => setTimezone(v === 'inherit' ? '' : v)}>
                                <SelectTrigger id="profile-timezone">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="inherit">
                                        Use the organization default
                                    </SelectItem>
                                    {zoneChoices.map((zone) => (
                                        <SelectItem key={zone} value={zone}>
                                            {zone}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground">
                                Dated dashboard and report figures are computed in this zone.
                            </p>
                        </div>
                    </TabsContent>

                    {/* ── Security: changes credentials */}
                    <TabsContent value="security" className="space-y-4 pt-4">
                        <div className="space-y-1.5">
                            <Label htmlFor="profile-email">Email</Label>
                            <Input
                                id="profile-email"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="you@example.com"
                                autoComplete="email"
                            />
                            <p className="text-xs text-muted-foreground">You sign in with this address.</p>
                        </div>

                        <Separator />

                        <div className="space-y-3">
                            <div>
                                <p className="text-sm font-medium">Change password</p>
                                <p className="text-xs text-muted-foreground">
                                    Leave blank to keep your current password.
                                </p>
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="profile-new-password">New password</Label>
                                <Input
                                    id="profile-new-password"
                                    type="password"
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    autoComplete="new-password"
                                    placeholder="At least 8 characters"
                                />
                            </div>
                            {changingPassword && (
                                <>
                                    <div className="space-y-1.5">
                                        <Label htmlFor="profile-confirm-password">Confirm new password</Label>
                                        <Input
                                            id="profile-confirm-password"
                                            type="password"
                                            value={confirmPassword}
                                            onChange={(e) => setConfirmPassword(e.target.value)}
                                            autoComplete="new-password"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label htmlFor="profile-current-password">Current password</Label>
                                        <Input
                                            id="profile-current-password"
                                            type="password"
                                            value={currentPassword}
                                            onChange={(e) => setCurrentPassword(e.target.value)}
                                            autoComplete="current-password"
                                        />
                                        <p className="text-xs text-muted-foreground">
                                            Required so a stolen session cannot change your password.
                                        </p>
                                    </div>
                                </>
                            )}
                        </div>
                    </TabsContent>

                    {/* ── Account: read-only facts */}
                    <TabsContent value="account" className="space-y-3 pt-4">
                        <dl className="divide-y divide-border/60 rounded-lg border border-border/60">
                            <div className="flex items-center justify-between gap-3 px-3 py-2.5">
                                <dt className="text-sm text-muted-foreground">User ID</dt>
                                <dd className="flex items-center gap-2">
                                    <span className="font-mono text-sm tabular-nums">{current?.id ?? '—'}</span>
                                    <Button variant="ghost" size="icon" className="size-7" onClick={() => void copyId()} aria-label="Copy user ID">
                                        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                                    </Button>
                                </dd>
                            </div>
                            <div className="flex items-center justify-between gap-3 px-3 py-2.5">
                                <dt className="text-sm text-muted-foreground">Member since</dt>
                                <dd className="text-sm">
                                    {current?.created_at
                                        ? new Date(current.created_at).toLocaleDateString(undefined, {
                                              year: 'numeric',
                                              month: 'long',
                                              day: 'numeric',
                                          })
                                        : '—'}
                                </dd>
                            </div>
                            <div className="flex items-center justify-between gap-3 px-3 py-2.5">
                                <dt className="text-sm text-muted-foreground">Role</dt>
                                <dd className="text-sm">{current?.is_superuser ? 'Superuser' : 'Member'}</dd>
                            </div>
                        </dl>
                        <p className="text-xs text-muted-foreground">
                            API keys, organization settings and integrations live in{' '}
                            <a href="/settings" className="underline hover:no-underline">
                                platform settings
                            </a>
                            .
                        </p>
                    </TabsContent>
                </Tabs>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
                        Cancel
                    </Button>
                    <Button onClick={() => void save()} disabled={saving || !hasChanges}>
                        {saving && <Loader2 className="animate-spin" />}
                        Save changes
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
