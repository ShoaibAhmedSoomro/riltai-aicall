import type { AlertMetricResponse, AlertRuleCreate, AlertRuleResponse } from '@/client/types.gen';

/** The rule form as typed: numbers are strings until they are validated. */
export interface RuleForm {
    name: string;
    metric: string;
    comparator: string;
    threshold: string;
    matchValue: string;
    windowMinutes: string;
    severity: string;
    cooldownMinutes: string;
    /** '' means every agent. */
    scopeWorkflowId: string;
    channelUuids: string[];
    isActive: boolean;
}

export const EMPTY_RULE_FORM: RuleForm = {
    name: '',
    metric: '',
    comparator: 'gt',
    threshold: '',
    matchValue: '',
    windowMinutes: '60',
    severity: 'medium',
    cooldownMinutes: '60',
    scopeWorkflowId: '',
    channelUuids: [],
    isActive: true,
};

export const COMPARATOR_LABEL: Record<string, string> = {
    gt: 'is above',
    gte: 'is at least',
    lt: 'is below',
    lte: 'is at most',
    eq: 'equals',
};

export const SEVERITY_LABEL: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High' };

export function ruleToForm(rule: AlertRuleResponse): RuleForm {
    return {
        name: rule.name,
        metric: rule.metric,
        comparator: rule.comparator,
        threshold: rule.threshold == null ? '' : String(rule.threshold),
        matchValue: rule.match_value ?? '',
        windowMinutes: rule.window_minutes == null ? '60' : String(rule.window_minutes),
        severity: rule.severity,
        cooldownMinutes: String(rule.cooldown_minutes),
        scopeWorkflowId: rule.scope_workflow_id == null ? '' : String(rule.scope_workflow_id),
        channelUuids: [...rule.channel_uuids],
        isActive: rule.is_active,
    };
}

function wholeNumber(text: string): number | null {
    const t = text.trim();
    return /^\d+$/.test(t) ? Number(t) : null;
}

/** What is wrong with the form, in words the person can act on, or null. The server
 *  checks all of this again; this is so the message comes before the round trip. */
export function validateRuleForm(form: RuleForm, metric: AlertMetricResponse | undefined): string | null {
    if (!form.name.trim()) return 'Give the rule a name';
    if (!metric) return 'Choose what to watch';
    if (metric.value_type === 'number') {
        if (form.threshold.trim() === '' || Number.isNaN(Number(form.threshold))) {
            return `Enter the number to compare ${metric.label.toLowerCase()} against`;
        }
    }
    if (metric.value_type === 'text' && !form.matchValue.trim()) return 'Enter the value to look for';
    if (metric.trigger === 'window') {
        const w = wholeNumber(form.windowMinutes);
        if (w === null || w < 5 || w > 1440) return 'The period must be between 5 and 1440 minutes';
    }
    const c = wholeNumber(form.cooldownMinutes);
    if (c === null || c < 1 || c > 10080) return 'Wait time between alerts must be between 1 minute and 7 days';
    return null;
}

export function formToRequest(form: RuleForm, metric: AlertMetricResponse): AlertRuleCreate {
    return {
        name: form.name.trim(),
        is_active: form.isActive,
        scope_workflow_id: form.scopeWorkflowId ? Number(form.scopeWorkflowId) : null,
        metric: form.metric,
        comparator: form.comparator as AlertRuleCreate['comparator'],
        threshold: metric.value_type === 'number' ? Number(form.threshold) : null,
        match_value: metric.value_type === 'text' ? form.matchValue.trim() : null,
        window_minutes: metric.trigger === 'window' ? Number(form.windowMinutes) : null,
        severity: form.severity as AlertRuleCreate['severity'],
        cooldown_minutes: Number(form.cooldownMinutes),
        channel_uuids: form.channelUuids,
    };
}

/** "Failure rate in the window is above 20 % over 30 minutes". */
export function ruleSummary(rule: AlertRuleResponse, metric: AlertMetricResponse | undefined): string {
    if (!metric) return rule.metric;
    if (metric.value_type === 'flag') return metric.label;
    if (metric.value_type === 'text') return `${metric.label}: ${rule.match_value ?? ''}`;
    const unit = metric.unit ? ` ${metric.unit}` : '';
    const period = rule.window_minutes ? ` over ${rule.window_minutes} min` : '';
    return `${metric.label} ${COMPARATOR_LABEL[rule.comparator] ?? rule.comparator} ${rule.threshold}${unit}${period}`;
}

/** Emails from a comma, semicolon, space or line separated box, without duplicates. */
export function parseRecipients(text: string): string[] {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const part of text.split(/[\s,;]+/)) {
        const address = part.trim();
        if (address && !seen.has(address.toLowerCase())) {
            seen.add(address.toLowerCase());
            out.push(address);
        }
    }
    return out;
}
