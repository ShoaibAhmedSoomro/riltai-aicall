import { cn } from '@/lib/utils';

const TONE: Record<string, string> = {
    high: 'bg-destructive/15 text-destructive',
    medium: 'bg-[var(--chart-4)]/15 text-[var(--chart-4)]',
    low: 'bg-muted text-muted-foreground',
};

/** Severity is shown as a word as well as a colour, so it never depends on colour alone. */
export function SeverityChip({ severity }: { severity: string }) {
    return (
        <span
            className={cn(
                'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase',
                TONE[severity] ?? TONE.low,
            )}
        >
            {severity}
        </span>
    );
}
