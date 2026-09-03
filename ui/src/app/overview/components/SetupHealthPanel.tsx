'use client';

import { AlertTriangle, ArrowRight, Check } from 'lucide-react';
import Link from 'next/link';

import type { OrganizationContextResponse, OrganizationPreferences, TelephonyConfigurationListItem, WorkflowCountResponse } from '@/client/types.gen';
import { cn } from '@/lib/utils';

import { Panel } from './Panel';

type CheckState = 'ok' | 'action' | 'unknown';

interface Check {
    label: string;
    state: CheckState;
    /** What is true right now, or what to do about it. */
    detail: string;
    href: string;
}

/**
 * Configuration health, with a link to the page that fixes each row.
 *
 * This is the honest version of the reference dashboard's "risk and compliance"
 * table. Every row is a real assertion from a real endpoint, not a score:
 *
 *   model config      /organizations/context -> model_services.config_source
 *   telephony         /organizations/telephony-configs (the list carries
 *                     phone_number_count, is_ready_for_outbound and
 *                     outbound_blocked_reason, which is why it beats the
 *                     warnings endpoint as an alert source)
 *   webhook secrets   /organizations/telephony-config-warnings, which covers
 *                     telnyx and vonage ONLY
 *   agents            /workflow/count
 *   api keys          /user/api-keys, counting is_active
 *   timezone          /organizations/preferences
 *
 * Onboarding state is deliberately NOT a row. Its context exposes only
 * fail-closed predicates that read TRUE while loading and stay TRUE if the
 * fetch fails, so a progress row built on it would claim "all complete" on
 * error.
 *
 * A source that failed to load becomes 'unknown' rather than silently 'ok',
 * because a green tick nobody verified is worse than an honest blank.
 */
export function SetupHealthPanel({
    orgContext,
    telephony,
    agents,
    apiKeyCount,
    preferences,
    telnyxMissingWebhookKeys,
    vonageMissingSignatureSecrets,
    loading,
}: {
    orgContext: OrganizationContextResponse | null;
    telephony: TelephonyConfigurationListItem[] | null;
    agents: WorkflowCountResponse | null;
    apiKeyCount: number | null;
    preferences: OrganizationPreferences | null;
    telnyxMissingWebhookKeys: number;
    vonageMissingSignatureSecrets: number;
    loading: boolean;
}) {
    const checks: Check[] = [];

    // ── AI services
    const configSource = orgContext?.model_services?.config_source;
    checks.push({
        label: 'AI models configured',
        state: !configSource ? 'unknown' : configSource === 'empty' ? 'action' : 'ok',
        detail:
            configSource === 'empty'
                ? 'No provider keys saved yet, so calls cannot run'
                : configSource === 'legacy_user_v1'
                  ? 'Using the legacy per-user configuration'
                  : configSource === 'organization_v2'
                    ? 'Organization configuration in use'
                    : 'Could not read the configuration',
        href: '/model-configurations',
    });

    // ── Voice agents
    checks.push({
        label: 'Voice agent created',
        state: agents === null ? 'unknown' : agents.total === 0 ? 'action' : 'ok',
        detail:
            agents === null
                ? 'Could not read the agent count'
                : agents.total === 0
                  ? 'Build your first agent to start taking calls'
                  : `${agents.active} active of ${agents.total}`,
        href: agents && agents.total === 0 ? '/workflow/create' : '/workflow',
    });

    // ── Telephony
    const configuredCount = telephony?.length ?? 0;
    const phoneNumbers = (telephony ?? []).reduce((n, c) => n + (c.phone_number_count ?? 0), 0);
    const blocked = (telephony ?? []).filter((c) => c.is_ready_for_outbound === false);

    checks.push({
        label: 'Telephony connected',
        state: telephony === null ? 'unknown' : configuredCount === 0 ? 'action' : 'ok',
        detail:
            telephony === null
                ? 'Could not read telephony configurations'
                : configuredCount === 0
                  ? 'Connect a provider or your own SIP carrier'
                  : `${configuredCount} configuration${configuredCount === 1 ? '' : 's'}`,
        href: configuredCount === 0 ? '/telephony-configurations?add=1' : '/telephony-configurations',
    });

    if (configuredCount > 0) {
        checks.push({
            label: 'Phone number attached',
            state: phoneNumbers === 0 ? 'action' : 'ok',
            detail:
                phoneNumbers === 0
                    ? 'No numbers attached, so inbound calls cannot arrive'
                    : `${phoneNumbers} number${phoneNumbers === 1 ? '' : 's'}`,
            href: '/telephony-configurations',
        });

        if (blocked.length > 0) {
            checks.push({
                label: 'Outbound calling ready',
                state: 'action',
                // The API gives a specific reason per configuration; show it
                // rather than a generic "not ready".
                detail: blocked[0].outbound_blocked_reason || `${blocked.length} configuration blocked`,
                href: `/telephony-configurations/${blocked[0].id}`,
            });
        }

        const missingSecrets = telnyxMissingWebhookKeys + vonageMissingSignatureSecrets;
        if (missingSecrets > 0) {
            checks.push({
                label: 'Webhook verification',
                state: 'action',
                detail: `${missingSecrets} configuration${missingSecrets === 1 ? '' : 's'} missing a signing secret`,
                href: '/telephony-configurations',
            });
        }
    }

    // ── Access + locale
    checks.push({
        label: 'API key issued',
        state: apiKeyCount === null ? 'unknown' : apiKeyCount === 0 ? 'action' : 'ok',
        detail:
            apiKeyCount === null
                ? 'Could not read API keys'
                : apiKeyCount === 0
                  ? 'Needed to trigger calls from your own code'
                  : `${apiKeyCount} active`,
        href: '/api-keys',
    });

    checks.push({
        label: 'Reporting timezone',
        state: preferences?.timezone ? 'ok' : 'action',
        detail: preferences?.timezone
            ? preferences.timezone
            : 'Unset, so reports fall back to your browser timezone',
        href: '/settings',
    });

    const needsAction = checks.filter((c) => c.state === 'action').length;

    return (
        <Panel
            title="Setup & health"
            subtitle={
                loading
                    ? undefined
                    : needsAction === 0
                      ? 'Everything checked is in order'
                      : `${needsAction} item${needsAction === 1 ? '' : 's'} need attention`
            }
            loading={loading}
            bodyClassName="p-0"
        >
            <ul className="divide-y divide-border/60">
                {checks.map((check) => (
                    <li key={check.label}>
                        <Link
                            href={check.href}
                            className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                        >
                            <span
                                aria-hidden
                                className={cn(
                                    'flex size-5 shrink-0 items-center justify-center rounded-full',
                                    check.state === 'ok' && 'bg-[var(--chart-2)]/15 text-[var(--chart-2)]',
                                    check.state === 'action' && 'bg-destructive/15 text-destructive',
                                    check.state === 'unknown' && 'bg-muted text-muted-foreground',
                                )}
                            >
                                {check.state === 'ok' ? (
                                    <Check className="size-3" />
                                ) : check.state === 'action' ? (
                                    <AlertTriangle className="size-3" />
                                ) : (
                                    <span className="text-[10px] font-bold">?</span>
                                )}
                            </span>
                            <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-medium">{check.label}</span>
                                <span className="block truncate text-xs text-muted-foreground">{check.detail}</span>
                            </span>
                            <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                        </Link>
                    </li>
                ))}
            </ul>
        </Panel>
    );
}
