'use client';

import { FlaskConical } from 'lucide-react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

/**
 * Marks a panel whose numbers are illustrative.
 *
 * Every panel fed from sampleData.ts carries this. It is not decoration: a
 * dashboard that mixes measured and invented figures without saying which is
 * which is worse than one with empty panels, because someone will eventually
 * make a decision on a number that was never real.
 */
export function SampleBadge() {
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <span className="inline-flex shrink-0 cursor-help items-center gap-1 rounded-full border border-[var(--chart-4)]/40 bg-[var(--chart-4)]/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--chart-4)]">
                    <FlaskConical className="size-2.5" aria-hidden />
                    Sample
                </span>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-64">
                <p>
                    Illustrative figures. The platform does not measure this yet, so these
                    numbers are placeholders for layout and are not from your account.
                </p>
            </TooltipContent>
        </Tooltip>
    );
}
