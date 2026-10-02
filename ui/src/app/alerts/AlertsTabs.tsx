'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';

const TABS = [
    { href: '/alerts', label: 'Alerts', match: (p: string) => p === '/alerts' },
    { href: '/alerts/rules', label: 'Rules', match: (p: string) => p.startsWith('/alerts/rules') },
    { href: '/alerts/channels', label: 'Channels', match: (p: string) => p.startsWith('/alerts/channels') },
];

/** The three views of alerting: what happened, what to watch for, where to tell. */
export function AlertsTabs() {
    const pathname = usePathname();
    return (
        <nav aria-label="Alerting" className="mb-6 flex gap-1 border-b">
            {TABS.map((tab) => {
                const active = tab.match(pathname);
                return (
                    <Link
                        key={tab.href}
                        href={tab.href}
                        aria-current={active ? 'page' : undefined}
                        className={cn(
                            '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
                            active
                                ? 'border-primary text-foreground'
                                : 'border-transparent text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {tab.label}
                    </Link>
                );
            })}
        </nav>
    );
}
