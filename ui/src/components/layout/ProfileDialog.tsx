'use client';

import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { updateProfileApiV1AuthProfilePatch } from '@/client/sdk.gen';
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
import { Separator } from '@/components/ui/separator';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';

/**
 * Edit the signed-in user's own details.
 *
 * Only rendered for the local auth provider. The hosted provider owns its
 * users' identities and ships a far more complete account UI at
 * /handler/account-settings (email, password, MFA, passkeys, sessions), so the
 * profile menu links there instead of reimplementing a worse version.
 *
 * Two things this has to handle that a normal form does not:
 *
 * 1. The OSS session is a write-once httpOnly cookie read at login, and the
 *    auth context exposes no way to refresh it. A successful save therefore
 *    re-POSTs /api/auth/session with the fresh token and user, or the header
 *    would keep showing the old name until the next sign-in.
 * 2. The JWT embeds the email, so an email change invalidates the old token.
 *    The API returns a new one for exactly this reason and it must be stored.
 */
export function ProfileDialog({
    open,
    onOpenChange,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}) {
    const { user } = useAuth();
    const current = user as { id?: string; name?: string; email?: string } | null;

    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [saving, setSaving] = useState(false);

    // Re-seed each time the dialog opens so a cancelled edit does not persist
    // into the next one.
    useEffect(() => {
        if (!open) return;
        setName(current?.name ?? '');
        setEmail(current?.email ?? '');
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
    }, [open, current?.name, current?.email]);

    const changingPassword = newPassword.length > 0;
    const nameChanged = (current?.name ?? '') !== name;
    const emailChanged = (current?.email ?? '') !== email;
    const hasChanges = nameChanged || emailChanged || changingPassword;

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
                    // Only send what changed, so the server can tell "clear the
                    // name" apart from "leave it alone".
                    ...(nameChanged ? { name } : {}),
                    ...(emailChanged ? { email } : {}),
                    ...(changingPassword
                        ? { current_password: currentPassword, new_password: newPassword }
                        : {}),
                },
            });

            // The generated client resolves rather than throwing on 4xx/5xx.
            if (response.error || !response.data) {
                toast.error(detailFromError(response.error, 'Could not save your profile'));
                return;
            }

            // Refresh the httpOnly session cookie with the new token and user,
            // then reload so every consumer of useAuth() sees the change. A
            // reload is blunt but the auth context has no update path, and this
            // happens once per edit.
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
            window.location.reload();
        } catch {
            toast.error('Could not reach the server');
        } finally {
            setSaving(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Profile settings</DialogTitle>
                    <DialogDescription>
                        Update how your name appears and the credentials you sign in with.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
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
                        <p className="text-xs text-muted-foreground">
                            You sign in with this address.
                        </p>
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
                </div>

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
