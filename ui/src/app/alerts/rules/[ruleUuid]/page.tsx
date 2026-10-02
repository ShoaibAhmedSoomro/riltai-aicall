'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import {
    createRuleApiV1AlertsRulesPost,
    deleteRuleApiV1AlertsRulesRuleUuidDelete,
    getRuleApiV1AlertsRulesRuleUuidGet,
    getWorkflowsSummaryApiV1WorkflowSummaryGet,
    listAlertMetricsApiV1AlertsMetricsGet,
    listChannelsApiV1AlertsChannelsGet,
    updateRuleApiV1AlertsRulesRuleUuidPatch,
} from '@/client/sdk.gen';
import type { AlertChannelResponse, AlertMetricResponse, WorkflowSummaryResponse } from '@/client/types.gen';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';

import { COMPARATOR_LABEL, EMPTY_RULE_FORM, formToRequest, type RuleForm, ruleToForm, SEVERITY_LABEL, validateRuleForm } from '../../alertForm';
import { AlertsTabs } from '../../AlertsTabs';

const ALL_AGENTS = 'all';

export default function AlertRuleEditorPage() {
    const { ruleUuid } = useParams<{ ruleUuid: string }>();
    const isNew = ruleUuid === 'new';
    const router = useRouter();
    const { loading: authLoading, isAuthenticated } = useAuth();

    const [form, setForm] = useState<RuleForm>(EMPTY_RULE_FORM);
    const [metrics, setMetrics] = useState<AlertMetricResponse[]>([]);
    const [channels, setChannels] = useState<AlertChannelResponse[]>([]);
    const [agents, setAgents] = useState<WorkflowSummaryResponse[]>([]);
    const [loaded, setLoaded] = useState(isNew);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (authLoading || !isAuthenticated) return;
        let cancelled = false;
        (async () => {
            const [m, c, a] = await Promise.all([
                listAlertMetricsApiV1AlertsMetricsGet(),
                listChannelsApiV1AlertsChannelsGet(),
                getWorkflowsSummaryApiV1WorkflowSummaryGet({ query: { status: 'active' } }),
            ]);
            if (cancelled) return;
            setMetrics(m.data?.metrics ?? []);
            setChannels(c.data ?? []);
            setAgents(a.data ?? []);
            if (!isNew) {
                const r = await getRuleApiV1AlertsRulesRuleUuidGet({ path: { rule_uuid: ruleUuid } });
                if (cancelled) return;
                if (r.error || !r.data) {
                    setError(detailFromError(r.error, 'Could not load this rule'));
                    return;
                }
                setForm(ruleToForm(r.data));
            }
            setLoaded(true);
        })();
        return () => {
            cancelled = true;
        };
    }, [authLoading, isAuthenticated, isNew, ruleUuid]);

    const metric = useMemo(() => metrics.find((x) => x.key === form.metric), [metrics, form.metric]);
    const set = <K extends keyof RuleForm>(key: K, value: RuleForm[K]) => setForm((f) => ({ ...f, [key]: value }));

    const save = async () => {
        const problem = validateRuleForm(form, metric);
        if (problem || !metric) {
            setError(problem);
            return;
        }
        setSaving(true);
        setError(null);
        const body = formToRequest(form, metric);
        const res = isNew
            ? await createRuleApiV1AlertsRulesPost({ body })
            : await updateRuleApiV1AlertsRulesRuleUuidPatch({
                  path: { rule_uuid: ruleUuid },
                  // Clearing the scope has its own flag: an omitted field means "unchanged".
                  body: { ...body, scope_workflow_id: body.scope_workflow_id ?? undefined, clear_scope: !form.scopeWorkflowId },
              });
        setSaving(false);
        if (res.error) {
            setError(detailFromError(res.error, 'Could not save the rule'));
            return;
        }
        toast.success(isNew ? 'Rule created' : 'Rule saved');
        router.push('/alerts/rules');
    };

    const remove = async () => {
        if (!window.confirm(`Delete “${form.name}”? Alerts it already raised are kept.`)) return;
        const res = await deleteRuleApiV1AlertsRulesRuleUuidDelete({ path: { rule_uuid: ruleUuid } });
        if (res.error) {
            toast.error(detailFromError(res.error, 'Could not delete the rule'));
            return;
        }
        toast.success('Rule deleted');
        router.push('/alerts/rules');
    };

    const perCall = metrics.filter((m) => m.trigger === 'run_completed');
    const overTime = metrics.filter((m) => m.trigger === 'window');

    return (
        <div className="container mx-auto max-w-3xl px-4 py-8">
            <h1 className="mb-4 text-2xl font-bold">{isNew ? 'New alert rule' : 'Edit alert rule'}</h1>
            <AlertsTabs />
            {!loaded ? (
                <p className="text-sm text-muted-foreground">{error ?? 'Loading…'}</p>
            ) : (
                <form
                    className="grid gap-6"
                    onSubmit={(e) => {
                        e.preventDefault();
                        void save();
                    }}
                >
                    <div className="grid gap-2">
                        <Label htmlFor="rule-name">Name</Label>
                        <Input id="rule-name" value={form.name} onChange={(e) => set('name', e.target.value)} />
                    </div>

                    <div className="grid gap-2">
                        <Label htmlFor="rule-metric">Watch for</Label>
                        <Select value={form.metric} onValueChange={(v) => set('metric', v)}>
                            <SelectTrigger id="rule-metric">
                                <SelectValue placeholder="Choose what to watch" />
                            </SelectTrigger>
                            <SelectContent>
                                {perCall.length > 0 && (
                                    <>
                                        <div className="px-2 py-1 text-xs font-semibold text-muted-foreground">
                                            When a call finishes
                                        </div>
                                        {perCall.map((m) => (
                                            <SelectItem key={m.key} value={m.key}>
                                                {m.label}
                                            </SelectItem>
                                        ))}
                                    </>
                                )}
                                {overTime.length > 0 && (
                                    <>
                                        <div className="px-2 py-1 text-xs font-semibold text-muted-foreground">
                                            Over a period of time
                                        </div>
                                        {overTime.map((m) => (
                                            <SelectItem key={m.key} value={m.key}>
                                                {m.label}
                                            </SelectItem>
                                        ))}
                                    </>
                                )}
                            </SelectContent>
                        </Select>
                        {metric && <p className="text-xs text-muted-foreground">{metric.description}</p>}
                    </div>

                    {metric?.value_type === 'number' && (
                        <div className="grid grid-cols-2 gap-4">
                            <div className="grid gap-2">
                                <Label htmlFor="rule-comparator">When it</Label>
                                <Select value={form.comparator} onValueChange={(v) => set('comparator', v)}>
                                    <SelectTrigger id="rule-comparator">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {Object.entries(COMPARATOR_LABEL).map(([k, label]) => (
                                            <SelectItem key={k} value={k}>
                                                {label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="grid gap-2">
                                <Label htmlFor="rule-threshold">Value{metric.unit ? ` (${metric.unit})` : ''}</Label>
                                <Input
                                    id="rule-threshold"
                                    inputMode="decimal"
                                    value={form.threshold}
                                    onChange={(e) => set('threshold', e.target.value)}
                                />
                            </div>
                        </div>
                    )}

                    {metric?.value_type === 'text' && (
                        <div className="grid gap-2">
                            <Label htmlFor="rule-match">Value to look for</Label>
                            <Input id="rule-match" value={form.matchValue} onChange={(e) => set('matchValue', e.target.value)} />
                        </div>
                    )}

                    {metric?.trigger === 'window' && (
                        <div className="grid gap-2">
                            <Label htmlFor="rule-window">Look at the last (minutes)</Label>
                            <Input
                                id="rule-window"
                                inputMode="numeric"
                                value={form.windowMinutes}
                                onChange={(e) => set('windowMinutes', e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground">Checked every five minutes.</p>
                        </div>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                        <div className="grid gap-2">
                            <Label htmlFor="rule-agent">Agent</Label>
                            <Select
                                value={form.scopeWorkflowId || ALL_AGENTS}
                                onValueChange={(v) => set('scopeWorkflowId', v === ALL_AGENTS ? '' : v)}
                            >
                                <SelectTrigger id="rule-agent">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value={ALL_AGENTS}>All agents</SelectItem>
                                    {agents.map((a) => (
                                        <SelectItem key={a.id} value={String(a.id)}>
                                            {a.name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid gap-2">
                            <Label htmlFor="rule-severity">Severity</Label>
                            <Select value={form.severity} onValueChange={(v) => set('severity', v)}>
                                <SelectTrigger id="rule-severity">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {Object.entries(SEVERITY_LABEL).map(([k, label]) => (
                                        <SelectItem key={k} value={k}>
                                            {label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="grid gap-2">
                        <Label htmlFor="rule-cooldown">Wait between alerts (minutes)</Label>
                        <Input
                            id="rule-cooldown"
                            inputMode="numeric"
                            value={form.cooldownMinutes}
                            onChange={(e) => set('cooldownMinutes', e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">
                            A condition that stays true alerts once, then stays quiet for this long.
                        </p>
                    </div>

                    <fieldset className="grid gap-2">
                        <legend className="mb-1 text-sm font-medium">Tell</legend>
                        {channels.length === 0 ? (
                            <p className="text-sm text-muted-foreground">
                                No channels yet.{' '}
                                <Link href="/alerts/channels" className="underline">
                                    Add one
                                </Link>{' '}
                                to be notified outside the app. The alert is always shown on the Alerts page.
                            </p>
                        ) : (
                            channels.map((c) => (
                                <label key={c.channel_uuid} className="flex items-center gap-2 text-sm">
                                    <Checkbox
                                        checked={form.channelUuids.includes(c.channel_uuid)}
                                        onCheckedChange={(on) =>
                                            set(
                                                'channelUuids',
                                                on
                                                    ? [...form.channelUuids, c.channel_uuid]
                                                    : form.channelUuids.filter((u) => u !== c.channel_uuid),
                                            )
                                        }
                                    />
                                    {c.name}
                                    <span className="text-xs text-muted-foreground">({c.type})</span>
                                </label>
                            ))
                        )}
                    </fieldset>

                    <label className="flex items-center gap-2 text-sm">
                        <Switch checked={form.isActive} onCheckedChange={(v) => set('isActive', v)} />
                        Rule is on
                    </label>

                    {error && (
                        <p role="alert" className="text-sm text-destructive">
                            {error}
                        </p>
                    )}

                    <div className="flex items-center justify-between">
                        <div className="flex gap-2">
                            <Button type="submit" disabled={saving}>
                                {saving ? 'Saving…' : 'Save rule'}
                            </Button>
                            <Button asChild type="button" variant="outline">
                                <Link href="/alerts/rules">Cancel</Link>
                            </Button>
                        </div>
                        {!isNew && (
                            <Button type="button" variant="ghost" className="text-destructive" onClick={remove}>
                                Delete
                            </Button>
                        )}
                    </div>
                </form>
            )}
        </div>
    );
}
