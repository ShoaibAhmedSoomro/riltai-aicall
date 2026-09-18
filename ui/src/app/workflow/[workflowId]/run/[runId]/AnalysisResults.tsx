'use client';

import { CheckCircle2, MinusCircle, XCircle } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * Post-call extraction and checks, read out of the run's `annotations`.
 *
 * The thing this component exists to get right: THREE states, not two. A field
 * or check can have passed, failed, or never been assessed — because the model
 * omitted it, because it would not coerce to its declared type, or because the
 * analysis call failed outright. Collapsing "not analysed" into a falsy value
 * would show a $0, an empty string or a red cross for something nobody ever
 * measured, which is a stronger claim than the raw JSON dump this replaces.
 *
 * That is why the stored result carries `fields` and `checks_configured`
 * alongside the results: the reader needs to know what was ASKED, not only
 * what came back. It cannot be recovered from the graph either — draft
 * definition rows mutate in place and `definition_id` is nullable.
 */

interface ConfiguredField {
    name: string;
    type: string;
}

interface CheckResult {
    name: string;
    passed: boolean;
    reason?: string | null;
    score?: number | null;
}

interface Analysis {
    fields?: ConfiguredField[];
    checks_configured?: string[];
    extracted?: Record<string, string | number | boolean>;
    checks?: CheckResult[];
    error?: string;
}

/** `annotations` is a shared merge target, so pick out only QA analysis. */
function analysesFrom(annotations: Record<string, unknown> | null): Analysis[] {
    if (!annotations) return [];
    return Object.entries(annotations)
        .filter(([key]) => key.startsWith('qa_'))
        .map(([, value]) => (value as { analysis?: Analysis } | null)?.analysis)
        .filter((a): a is Analysis => {
            if (!a || typeof a !== 'object') return false;
            // An analysis with nothing configured is {} — nothing was asked,
            // so there is nothing to report and no empty card to render.
            return Boolean(a.fields?.length || a.checks_configured?.length);
        });
}

function formatValue(value: string | number | boolean) {
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    return String(value);
}

function NotAnalysed() {
    return <span className="text-sm italic text-muted-foreground">Not analysed</span>;
}

export function AnalysisResults({ annotations }: { annotations: Record<string, unknown> | null }) {
    const analyses = analysesFrom(annotations);
    if (analyses.length === 0) return null;

    return (
        <div className="space-y-6">
            {analyses.map((analysis, i) => {
                const extracted = analysis.extracted ?? {};
                const byName = new Map((analysis.checks ?? []).map((c) => [c.name, c]));

                return (
                    <section key={i} className="space-y-4">
                        <div className="flex items-baseline justify-between gap-3">
                            <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                Call analysis
                            </h3>
                            {analysis.error && (
                                <span className="text-xs text-muted-foreground">
                                    Analysis did not complete for this call.
                                </span>
                            )}
                        </div>

                        {(analysis.fields?.length ?? 0) > 0 && (
                            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                {analysis.fields!.map((field) => {
                                    const value = extracted[field.name];
                                    return (
                                        <div
                                            key={field.name}
                                            className="rounded-xl border border-border bg-muted/40 px-4 py-3"
                                        >
                                            <p className="truncate text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                                                {field.name}
                                            </p>
                                            <p className="mt-2 text-lg font-semibold text-foreground">
                                                {/* `=== undefined`, not a falsy test: a real
                                                    `false` and a real `0` are answers. */}
                                                {value === undefined ? <NotAnalysed /> : formatValue(value)}
                                            </p>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {(analysis.checks_configured?.length ?? 0) > 0 && (
                            <ul className="divide-y divide-border/60 rounded-xl border border-border">
                                {analysis.checks_configured!.map((name) => {
                                    const check = byName.get(name);
                                    // The icon is the ONLY indicator of a
                                    // check's state when it has no reason
                                    // text, so it is labelled rather than
                                    // aria-hidden -- a decorative marker that
                                    // carries the whole meaning is not
                                    // decorative.
                                    const [Icon, state] =
                                        check === undefined
                                            ? [MinusCircle, 'Not analysed']
                                            : check.passed
                                              ? [CheckCircle2, 'Passed']
                                              : [XCircle, 'Failed'];
                                    return (
                                        <li key={name} className="flex items-start gap-3 px-4 py-3">
                                            <Icon
                                                className={cn(
                                                    'mt-0.5 size-4 shrink-0',
                                                    check === undefined
                                                        ? 'text-muted-foreground'
                                                        : check.passed
                                                          ? 'text-emerald-600 dark:text-emerald-400'
                                                          : 'text-destructive',
                                                )}
                                                role="img"
                                                aria-label={state}
                                            />
                                            <span className="min-w-0 flex-1">
                                                <span className="block truncate text-sm font-medium">{name}</span>
                                                {check === undefined ? (
                                                    <NotAnalysed />
                                                ) : (
                                                    check.reason && (
                                                        <span className="block text-xs text-muted-foreground">
                                                            {check.reason}
                                                        </span>
                                                    )
                                                )}
                                            </span>
                                            {/* Only when a score was asked for AND returned.
                                                `!= null` keeps a legitimate 0. */}
                                            {check?.score != null && (
                                                <span className="shrink-0 text-sm font-semibold tabular-nums">
                                                    {check.score}
                                                </span>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </section>
                );
            })}
        </div>
    );
}
