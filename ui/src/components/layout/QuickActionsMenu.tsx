'use client';

import { ChevronDown, Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { QUICK_ACTIONS } from '@/lib/quickActions';

/**
 * The create menu in the app header.
 *
 * Items come from the shared QUICK_ACTIONS list so this and the dashboard's
 * quick-actions panel cannot drift. Only three of them open a create form
 * directly; the rest land on the page that owns the form, and those are grouped
 * separately under their own heading so the menu does not promise a dialog that
 * will not appear.
 */
export function QuickActionsMenu() {
    const router = useRouter();

    const direct = QUICK_ACTIONS.filter((a) => !a.landsOnPage);
    const onPage = QUICK_ACTIONS.filter((a) => a.landsOnPage);

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button size="sm" className="gap-1.5">
                    <Plus className="size-4" />
                    <span className="hidden sm:inline">Create</span>
                    <ChevronDown className="size-3.5 opacity-70" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                    Create
                </DropdownMenuLabel>
                {direct.map((action) => (
                    <DropdownMenuItem
                        key={action.id}
                        onClick={() => router.push(action.href)}
                        className="cursor-pointer"
                    >
                        <action.icon className="size-4" />
                        {action.label}
                    </DropdownMenuItem>
                ))}

                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                    Go to
                </DropdownMenuLabel>
                {onPage.map((action) => (
                    <DropdownMenuItem
                        key={action.id}
                        onClick={() => router.push(action.href)}
                        className="cursor-pointer"
                    >
                        <action.icon className="size-4" />
                        {action.label}
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
