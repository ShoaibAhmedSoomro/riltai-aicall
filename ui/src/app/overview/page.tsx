'use client';

import { Bot, Clock, FlaskConical, Megaphone, Phone, PhoneCall, RefreshCw } from 'lucide-react';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { useOrgConfig } from '@/context/OrgConfigContext';
import { useTelephonyConfigWarnings } from '@/context/TelephonyConfigWarningsContext';
import { useAuth } from '@/lib/auth';

import { BusiestAgentsPanel } from './components/BusiestAgentsPanel';
import { CallVolumeChart } from './components/CallVolumeChart';
import { DurationHistogram } from './components/DurationHistogram';
import { OutcomeDonut } from './components/OutcomeDonut';
import { Panel } from './components/Panel';
import { QuickActionsPanel } from './components/QuickActionsPanel';
import { RecentCallsPanel } from './components/RecentCallsPanel';
import {
    AgentHealthPanel,
    AlertsPanel,
    AnswerRatePanel,
    CompliancePanel,
    ContactsPanel,
    ConversionPanel,
    CostVsMarginPanel,
    PerformancePanel,
    PipelinePanel,
    RegionsPanel,
    RevenuePanel,
    SampleKpiTiles,
    UnitEconomicsPanel,
} from './components/SamplePanels';
import { SetupHealthPanel } from './components/SetupHealthPanel';
import { StatCard } from './components/StatCard';
import { SAMPLE_PANEL_IDS } from './sampleData';
import { useDashboardData } from './useDashboardData';

function greeting(): string {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 18) return 'Good afternoon';
    return 'Good evening';
}

/** Period talk time: hours once past an hour, otherwise minutes. */
function talkTime(seconds: number): string {
    const m = seconds / 60;
    if (m < 60) return `${m < 10 ? m.toFixed(1) : Math.round(m)}m`;
    const h = Math.floor(m / 60);
    return `${h}h ${String(Math.round(m % 60)).padStart(2, '0')}m`;
}

export default function OverviewPage() {
    const { user } = useAuth();
    const { orgContext, organizationPreferences } = useOrgConfig();
    const { telnyxMissingWebhookPublicKeyCount, vonageMissingSignatureSecretCount } =
        useTelephonyConfigWarnings();

    // Reports are date-bounded, so they need a timezone. Precedence: the user's
    // own profile setting, then the organization default, then the browser.
    // The header names the zone in force so a dated figure is never ambiguous.
    const userTimezone = (user as { profile?: { timezone?: string | null } } | null)?.profile?.timezone;
    const data = useDashboardData(userTimezone || organizationPreferences?.timezone || null);

    const firstName =
        (user as { displayName?: string } | null)?.displayName?.split(' ')[0] ??
        (user as { name?: string } | null)?.name?.split(' ')[0] ??
        null;

    const runningCampaigns = data.campaigns?.byState?.running ?? 0;
    const phoneNumbers = (data.telephony ?? []).reduce((n, c) => n + (c.phone_number_count ?? 0), 0);
    const dispositionTotal = (data.dispositions ?? []).reduce((n, d) => n + d.count, 0);
    const durationTotal = (data.durations ?? []).reduce((n, d) => n + d.count, 0);
    const weekTotal = (data.dayVolume ?? []).reduce((n, d) => n + d.calls, 0);

    return (
        <div className="mx-auto max-w-[1600px] px-4 py-6 lg:px-6">
            {/* ── Title row */}
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-sm text-muted-foreground">
                        {greeting()}
                        {firstName ? `, ${firstName}` : ''} 👋
                    </p>
                    <h1 className="mt-0.5 text-2xl font-semibold tracking-tight">Operations Overview</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Live view of your voice agents, calls and configuration. Dated figures use{' '}
                        <span className="font-medium text-foreground">{data.timezone}</span>
                        {userTimezone
                            ? ' from your profile.'
                            : organizationPreferences?.timezone
                              ? ' from the organization default.'
                              : ' from your browser.'}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={data.refresh} disabled={data.loading}>
                        <RefreshCw className={data.loading ? 'animate-spin' : undefined} />
                        Refresh
                    </Button>
                    <Button size="sm" asChild>
                        <Link href="/reports">Daily report</Link>
                    </Button>
                </div>
            </div>

            {/* One disclosure for the whole page, so the Sample badges are
                explained once rather than only on hover. */}
            <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-[var(--chart-4)]/35 bg-[var(--chart-4)]/[0.07] px-3 py-2.5">
                <FlaskConical className="mt-0.5 size-4 shrink-0 text-[var(--chart-4)]" aria-hidden />
                <p className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">
                        {SAMPLE_PANEL_IDS.length} panels show sample figures.
                    </span>{' '}
                    Revenue, answer rate, contact rate, compliance and geography are not
                    measured by the platform yet, so those are placeholders for layout and
                    are not from your account. Anything without a{' '}
                    <span className="font-medium text-foreground">Sample</span> badge is
                    read live from your data.
                </p>
            </div>

            {/* ── KPI row. Every tile links to the page that explains it. */}
            <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
                <StatCard
                    label="Voice agents"
                    icon={Bot}
                    href="/workflow"
                    loading={data.loading && data.agents === null}
                    unavailable={!data.loading && data.agents === null ? 'Unavailable' : undefined}
                    value={(data.agents?.total ?? 0).toLocaleString()}
                    hint={
                        data.agents
                            ? `${data.agents.active} active · ${data.agents.archived} archived`
                            : undefined
                    }
                />
                <StatCard
                    label="Calls today"
                    icon={Phone}
                    href="/reports"
                    loading={data.loading && data.callsToday === null}
                    unavailable={!data.loading && data.callsToday === null ? 'Unavailable' : undefined}
                    value={(data.callsToday ?? 0).toLocaleString()}
                    // total_runs counts every run row: inbound, outbound, browser
                    // tests and text chats, completed or not. Label accordingly.
                    hint="All runs started today"
                />
                <StatCard
                    label={`Calls this week`}
                    icon={PhoneCall}
                    href="/usage"
                    loading={data.loading && data.dayVolume === null}
                    unavailable={!data.loading && data.dayVolume === null ? 'Unavailable' : undefined}
                    value={weekTotal.toLocaleString()}
                    hint="Last 7 days"
                />
                <StatCard
                    label="Calls all time"
                    icon={Phone}
                    href="/usage"
                    loading={data.loading && data.totalCalls === null}
                    unavailable={!data.loading && data.totalCalls === null ? 'Unavailable' : undefined}
                    value={(data.totalCalls ?? 0).toLocaleString()}
                    hint="Runs with recorded usage"
                />
                <StatCard
                    label="Talk time"
                    icon={Clock}
                    href="/usage"
                    loading={data.loading && data.period === null}
                    unavailable={!data.loading && data.period === null ? 'Unavailable' : undefined}
                    value={talkTime(data.period?.total_duration_seconds ?? 0)}
                    hint="This billing period"
                />
                <StatCard
                    label="Campaigns"
                    icon={Megaphone}
                    href="/campaigns"
                    loading={data.loading && data.campaigns === null}
                    unavailable={!data.loading && data.campaigns === null ? 'Unavailable' : undefined}
                    value={(data.campaigns?.total ?? 0).toLocaleString()}
                    hint={
                        runningCampaigns > 0
                            ? `${runningCampaigns} running · ${data.campaigns?.activeRows.toLocaleString()} calls queued`
                            : 'None running'
                    }
                />
                <SampleKpiTiles />
            </div>

            {/* ── Charts */}
            <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
                <Panel
                    title="Call volume"
                    subtitle="Last 7 days, counted per day"
                    action={{ label: 'Usage', href: '/usage' }}
                    loading={data.loading && data.dayVolume === null}
                    empty={
                        data.dayVolume && weekTotal === 0
                            ? 'No calls in the last 7 days.'
                            : !data.loading && data.dayVolume === null
                              ? 'Call volume could not be loaded.'
                              : undefined
                    }
                >
                    {data.dayVolume && <CallVolumeChart data={data.dayVolume} timezone={data.timezone} />}
                </Panel>

                <Panel
                    title="How calls ended"
                    subtitle="Today · top 5 outcomes plus the remainder"
                    action={{ label: 'Reports', href: '/reports' }}
                    loading={data.loading && data.dispositions === null}
                    empty={
                        data.dispositions && dispositionTotal === 0
                            ? 'No calls today yet, so there are no outcomes to break down.'
                            : !data.loading && data.dispositions === null
                              ? 'Outcomes could not be loaded.'
                              : undefined
                    }
                >
                    {data.dispositions && dispositionTotal > 0 && (
                        <OutcomeDonut data={data.dispositions} total={dispositionTotal} />
                    )}
                </Panel>

                <Panel
                    title="Call length"
                    subtitle="Today · calls that recorded a duration"
                    action={{ label: 'Reports', href: '/reports' }}
                    loading={data.loading && data.durations === null}
                    empty={
                        data.durations && durationTotal === 0
                            ? 'No completed calls today, so there are no durations to chart.'
                            : !data.loading && data.durations === null
                              ? 'Durations could not be loaded.'
                              : undefined
                    }
                >
                    {data.durations && durationTotal > 0 && <DurationHistogram data={data.durations} />}
                </Panel>
            </div>

            {/* ── Operational panels */}
            <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
                <SetupHealthPanel
                    orgContext={orgContext}
                    telephony={data.telephony}
                    agents={data.agents}
                    apiKeyCount={data.apiKeyCount}
                    preferences={organizationPreferences}
                    telnyxMissingWebhookKeys={telnyxMissingWebhookPublicKeyCount}
                    vonageMissingSignatureSecrets={vonageMissingSignatureSecretCount}
                    loading={data.loading && data.telephony === null}
                />
                <RecentCallsPanel runs={data.recentCalls} loading={data.loading && data.recentCalls === null} />
                <BusiestAgentsPanel
                    agents={data.busiestAgents}
                    truncated={data.busiestAgentsTruncated}
                    windowSize={100}
                    loading={data.loading && data.busiestAgents === null}
                />
            </div>

            {/* ── Reach + actions */}
            <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
                <Panel
                    title="Telephony"
                    subtitle={`${(data.telephony ?? []).length} configuration${(data.telephony ?? []).length === 1 ? '' : 's'} · ${phoneNumbers} number${phoneNumbers === 1 ? '' : 's'}`}
                    action={{ label: 'Manage', href: '/telephony-configurations' }}
                    loading={data.loading && data.telephony === null}
                    empty={
                        data.telephony && data.telephony.length === 0
                            ? 'No telephony connected yet. Add a provider or your own SIP carrier to take calls.'
                            : undefined
                    }
                    bodyClassName="p-0"
                >
                    <ul className="divide-y divide-border/60">
                        {(data.telephony ?? []).map((config) => (
                            <li key={config.id}>
                                <Link
                                    href={`/telephony-configurations/${config.id}`}
                                    className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-accent/40"
                                >
                                    <span className="min-w-0 flex-1">
                                        <span className="block truncate text-sm font-medium">{config.name}</span>
                                        <span className="block truncate text-xs text-muted-foreground">
                                            {config.provider}
                                            {config.connectivity ? ` · ${config.connectivity.toUpperCase()}` : ''}
                                            {config.is_default_outbound ? ' · default outbound' : ''}
                                        </span>
                                    </span>
                                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                                        {(config.phone_number_count ?? 0).toLocaleString()}{' '}
                                        {config.phone_number_count === 1 ? 'number' : 'numbers'}
                                    </span>
                                </Link>
                            </li>
                        ))}
                    </ul>
                </Panel>

                <div className="xl:col-span-2">
                    <QuickActionsPanel />
                </div>
            </div>

            {/* ── Illustrative rows. Everything below carries a Sample badge:
                these mirror the reference layout for panels the platform does
                not measure. Delete a panel here and its export in sampleData.ts
                once a real source exists. */}
            <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
                <RevenuePanel />
                <CostVsMarginPanel />
                <AnswerRatePanel />
            </div>

            <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
                <PerformancePanel />
                <PipelinePanel />
                <ConversionPanel />
            </div>

            <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                <AgentHealthPanel />
                <ContactsPanel />
            </div>

            <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
                <CompliancePanel />
                <UnitEconomicsPanel />
                <RegionsPanel />
            </div>

            <div className="mt-3">
                <AlertsPanel />
            </div>
        </div>
    );
}
