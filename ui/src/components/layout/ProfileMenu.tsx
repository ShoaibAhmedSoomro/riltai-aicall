'use client';

import { ExternalLink, LogOut, Settings, UserCog } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAuth } from '@/lib/auth';

import { ProfileDialog } from './ProfileDialog';

/** Up to two initials from a name, falling back to the email local part. */
function initials(name?: string | null, email?: string | null): string {
    const source = (name || '').trim() || (email || '').split('@')[0] || '';
    const parts = source.split(/[\s._-]+/).filter(Boolean);
    if (!parts.length) return '?';
    return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase();
}

/**
 * The account menu in the app header.
 *
 * There is no avatar image anywhere in this product: the users table stores no
 * image, and the hosted provider's picture is not exposed through the shared
 * auth context. Initials are derived instead, so the control looks finished
 * without inventing a storage path or fetching a third-party gravatar.
 *
 * The edit entry differs by provider on purpose. The local provider gets an
 * in-app dialog, because until now it had no way to change any user detail at
 * all. The hosted provider gets a link to its own account settings, which
 * already cover profile, email, password, MFA, passkeys and sessions.
 */
export function ProfileMenu() {
    const { user, logout, provider } = useAuth();
    const router = useRouter();
    const [editing, setEditing] = useState(false);

    const details = user as { name?: string; displayName?: string; email?: string; primaryEmail?: string } | null;
    const name = details?.name || details?.displayName || null;
    const email = details?.email || details?.primaryEmail || null;
    const isLocal = provider !== 'stack';

    if (!user) return null;

    return (
        <>
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        variant="ghost"
                        className="h-8 gap-2 px-1.5"
                        aria-label="Account menu"
                    >
                        <span
                            aria-hidden
                            className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground"
                        >
                            {initials(name, email)}
                        </span>
                        <span className="hidden max-w-[9rem] truncate text-sm font-medium sm:inline">
                            {name || email || 'Account'}
                        </span>
                    </Button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" className="w-64">
                    <DropdownMenuLabel className="font-normal">
                        <span className="block truncate text-sm font-medium">{name || 'Unnamed user'}</span>
                        {email && (
                            <span className="block truncate text-xs text-muted-foreground">{email}</span>
                        )}
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />

                    {isLocal ? (
                        <DropdownMenuItem onClick={() => setEditing(true)} className="cursor-pointer">
                            <UserCog className="size-4" />
                            Profile settings
                        </DropdownMenuItem>
                    ) : (
                        <DropdownMenuItem
                            onClick={() => router.push('/handler/account-settings')}
                            className="cursor-pointer"
                        >
                            <UserCog className="size-4" />
                            Account settings
                            <ExternalLink className="ml-auto size-3 opacity-60" />
                        </DropdownMenuItem>
                    )}

                    <DropdownMenuItem onClick={() => router.push('/settings')} className="cursor-pointer">
                        <Settings className="size-4" />
                        Platform settings
                    </DropdownMenuItem>

                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => void logout()} className="cursor-pointer">
                        <LogOut className="size-4" />
                        Sign out
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>

            {isLocal && <ProfileDialog open={editing} onOpenChange={setEditing} />}
        </>
    );
}
