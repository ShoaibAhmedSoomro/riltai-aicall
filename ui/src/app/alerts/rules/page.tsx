'use client';

import { Plus } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { listAlertMetricsApiV1AlertsMetricsGet, listRulesApiV1AlertsRulesGet, updateRuleApiV1AlertsRulesRuleUuidPatch } from '@/client/sdk.gen';
import type { AlertMetricResponse, AlertRuleResponse } from '@/client/types.gen';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';
import { formatDateTime } from '@/lib/dateTime';

import { ruleSummary } from '../alertForm';
import { AlertsTabs } from '../AlertsTabs';
import { SeverityChip } from '../SeverityChip';

export default function AlertRulesPage() {
    const { loading: authLoading, isAuthenticated } = useAuth();
    const [rules, setRules] = useState<AlertRuleResponse[] | null>(null);
    const [metrics, setMetrics] = useState<Record<string, AlertMetricResponse>>({});
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        const [r, m] = await Promise.all([listRulesApiV1AlertsRulesGet(), listAlertMetricsApiV1AlertsMetricsGet()]);
        if (r.error) {
            setError(detailFromError(r.error, 'Could not load rules'));
            return;
        }
        setError(null);
        setRules(r.data ?? []);
        setMetrics(Object.fromEntries((m.data?.metrics ?? []).map((x) => [x.key, x])));
    }, []);

    useEffect(() => {
        if (authLoading || !isAuthenticated) return;
        void load();
    }, [authLoading, isAuthenticated, load]);

    const toggle = async (rule: AlertRuleResponse, isActive: boolean) => {
        const res = await updateRuleApiV1AlertsRulesRuleUuidPatch({
            path: { rule_uuid: rule.rule_uuid },
            body: { is_active: isActive },
        });
        if (res.error || !res.data) {
            toast.error(detailFromError(res.error, 'Could not change the rule'));
            return;
        }
        setRules((prev) => prev?.map((r) => (r.rule_uuid === rule.rule_uuid ? res.data! : r)) ?? prev);
    };

    return (
        <div className="container mx-auto px-4 py-8">
            <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold">Alert rules</h1>
                    <p className="mt-1 text-sm text-muted-foreground">What to watch for, and who to tell.</p>
                </div>
                <Button asChild>
                    <Link href="/alerts/rules/new">
                        <Plus className="mr-1 h-4 w-4" aria-hidden /> New rule
                    </Link>
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
                    {rules === null ? (
                        <p className="p-8 text-center text-sm text-muted-foreground">Loading…</p>
                    ) : rules.length === 0 ? (
                        <div className="flex flex-col items-center gap-2 p-10 text-center">
                            <p className="font-medium">No rules yet</p>
                            <p className="max-w-md text-sm text-muted-foreground">
                                A rule watches your calls and tells you when something needs attention, such as a call
                                failing or too few calls coming in.
                            </p>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Rule</TableHead>
                                    <TableHead>Condition</TableHead>
                                    <TableHead>Severity</TableHead>
                                    <TableHead>Last fired</TableHead>
                                    <TableHead className="text-right">On</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rules.map((rule) => (
                                    <TableRow key={rule.rule_uuid}>
                                        <TableCell className="font-medium">
                                            <Link href={`/alerts/rules/${rule.rule_uuid}`} className="hover:underline">
                                                {rule.name}
                                            </Link>
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {ruleSummary(rule, metrics[rule.metric])}
                                        </TableCell>
                                        <TableCell>
                                            <SeverityChip severity={rule.severity} />
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {rule.last_fired_at ? formatDateTime(rule.last_fired_at) : 'Never'}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Switch
                                                checked={rule.is_active}
                                                onCheckedChange={(v) => toggle(rule, v)}
                                                aria-label={`${rule.name} is ${rule.is_active ? 'on' : 'off'}`}
                                            />
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
