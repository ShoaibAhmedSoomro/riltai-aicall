"use client";

import { ExternalLink, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { SETTINGS_DOCUMENTATION_URLS } from "@/constants/documentation";
import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import {
    type GovernanceConfiguration,
    type GuardrailAction,
    type GuardrailCategory,
    type RedactionCategory,
    type StorageMode,
    type WorkflowConfigurations,
} from "@/types/workflow-configurations";

const INHERIT = "inherit";
const FOREVER = "forever";

const STORAGE_MODES: { value: StorageMode | typeof INHERIT; label: string; hint: string }[] = [
    { value: INHERIT, label: "Use the organization default", hint: "Set under Settings → Data Retention." },
    { value: "everything", label: "Keep everything", hint: "Recording, transcript and details, as they are today." },
    {
        value: "except_pii",
        label: "Keep everything except personal details",
        hint: "Personal details are replaced with a placeholder before anything is saved.",
    },
    {
        value: "basic_only",
        label: "Keep basic details only",
        hint: "No recording and no transcript. Outcome, duration and cost are kept. Expired calls also lose their captured details.",
    },
];

const RETENTION_OPTIONS = [
    { value: INHERIT, label: "Use the organization default" },
    { value: "30", label: "30 days" },
    { value: "60", label: "60 days" },
    { value: "90", label: "90 days" },
    { value: "180", label: "180 days" },
    { value: "365", label: "1 year" },
    { value: FOREVER, label: "Keep forever" },
];

const REDACTION_CATEGORIES: { value: RedactionCategory; label: string }[] = [
    { value: "phone", label: "Phone numbers" },
    { value: "email", label: "Email addresses" },
    { value: "card", label: "Payment card numbers" },
    { value: "national_id", label: "ID and passport numbers" },
    { value: "address", label: "Street addresses" },
    { value: "dob", label: "Dates of birth" },
];

const GUARDRAIL_CATEGORIES: { value: GuardrailCategory; label: string }[] = [
    { value: "hate", label: "Hateful content" },
    { value: "harassment", label: "Harassment or threats" },
    { value: "self_harm", label: "Self-harm" },
    { value: "sexual_content", label: "Sexual content" },
    { value: "violence", label: "Violence" },
    { value: "illegal_activity", label: "Illegal activity" },
    { value: "medical_advice", label: "Medical advice" },
    { value: "legal_advice", label: "Legal advice" },
    { value: "financial_advice", label: "Financial advice" },
];

const ACTIONS: { value: GuardrailAction; label: string; hint: string }[] = [
    { value: "log_only", label: "Only record it", hint: "The agent still hears the caller." },
    { value: "deflect", label: "Decline and carry on", hint: "The agent never sees the words; a fixed reply is spoken." },
    { value: "end_call", label: "Decline and end the call", hint: "As above, then the call ends." },
];

function toggle<T>(list: T[], value: T, on: boolean): T[] {
    const without = list.filter((v) => v !== value);
    return on ? [...without, value] : without;
}

function retentionToSelect(days: number | null): string {
    if (days === null) return INHERIT;
    if (days === 0) return FOREVER;
    return String(days);
}

function selectToRetention(value: string): number | null {
    if (value === INHERIT) return null;
    if (value === FOREVER) return 0;
    return Number(value);
}

export function GovernanceSection({
    workflowConfigurations,
    workflowName,
    onSave,
}: {
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    onSave: (configurations: WorkflowConfigurations, workflowName: string) => Promise<void>;
}) {
    const saved = workflowConfigurations.governance_configuration;
    const [gov, setGov] = useState<GovernanceConfiguration>(saved);
    const [isSaving, setIsSaving] = useState(false);

    const isDirty = useMemo(() => JSON.stringify(gov) !== JSON.stringify(saved), [gov, saved]);
    useUnsavedChanges("governance", isDirty);

    const basicOnly = gov.storage_mode === "basic_only";
    const mode = STORAGE_MODES.find((m) => m.value === (gov.storage_mode ?? INHERIT));
    const action = ACTIONS.find((a) => a.value === gov.guardrails.on_violation);

    const patch = (update: Partial<GovernanceConfiguration>) => setGov((prev) => ({ ...prev, ...update }));
    const patchGuardrails = (update: Partial<GovernanceConfiguration["guardrails"]>) =>
        setGov((prev) => ({ ...prev, guardrails: { ...prev.guardrails, ...update } }));

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await onSave({ ...workflowConfigurations, governance_configuration: gov }, workflowName);
            toast.success("Data & safety settings saved. Publish the agent to apply the changes.");
        } catch (error) {
            console.error("Failed to save data & safety settings:", error);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id="governance">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <ShieldCheck className="h-4 w-4" />
                    Data &amp; Safety
                </CardTitle>
                <CardDescription>
                    What this agent keeps from a call, for how long, and what is screened. Applies to
                    calls that start after you publish.{" "}
                    <a
                        href={SETTINGS_DOCUMENTATION_URLS.governance}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-0.5 underline"
                    >
                        Learn more <ExternalLink className="h-3 w-3" />
                    </a>
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-6">
                {/* What is kept */}
                <div className="space-y-2">
                    <Label className="text-xs">What to keep</Label>
                    <Select
                        value={gov.storage_mode ?? INHERIT}
                        onValueChange={(v) => patch({ storage_mode: v === INHERIT ? null : (v as StorageMode) })}
                    >
                        <SelectTrigger className="max-w-sm">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {STORAGE_MODES.map((m) => (
                                <SelectItem key={m.value} value={m.value}>
                                    {m.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">{mode?.hint}</p>
                </div>

                <div className="space-y-2">
                    <Label className="text-xs">Delete a call&apos;s recording, transcript and logs after</Label>
                    <Select
                        value={retentionToSelect(gov.retention_days)}
                        onValueChange={(v) => patch({ retention_days: selectToRetention(v) })}
                    >
                        <SelectTrigger className="max-w-sm">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {RETENTION_OPTIONS.map((o) => (
                                <SelectItem key={o.value} value={o.value}>
                                    {o.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                        The date is fixed when each call starts, so changing this later does not alter
                        calls that already happened. The call&apos;s outcome, duration and cost are
                        always kept so reports do not change.
                    </p>
                </div>

                <Separator />

                {/* Recording */}
                <div className="space-y-4">
                    <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1">
                            <Label htmlFor="gov_record_audio" className="text-xs">Record the call audio</Label>
                            <p className="text-xs text-muted-foreground">
                                Off means audio is never captured, not captured and deleted later.
                            </p>
                        </div>
                        <Switch
                            id="gov_record_audio"
                            checked={gov.record_audio && !basicOnly}
                            disabled={basicOnly}
                            onCheckedChange={(v) => patch({ record_audio: v })}
                        />
                    </div>
                    <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1">
                            <Label htmlFor="gov_store_transcript" className="text-xs">Save the transcript</Label>
                            <p className="text-xs text-muted-foreground">
                                Off also removes the spoken words from the call log. Call analysis and
                                quality checks need a transcript, so they have nothing to read.
                            </p>
                        </div>
                        <Switch
                            id="gov_store_transcript"
                            checked={gov.store_transcript && !basicOnly}
                            disabled={basicOnly}
                            onCheckedChange={(v) => patch({ store_transcript: v })}
                        />
                    </div>
                    {basicOnly && (
                        <p className="text-xs text-muted-foreground">
                            &quot;Keep basic details only&quot; turns both off.
                        </p>
                    )}
                </div>

                <Separator />

                {/* Redaction */}
                <div className="space-y-3">
                    <div className="space-y-1">
                        <Label className="text-xs">Remove personal details from what is saved</Label>
                        <p className="text-xs text-muted-foreground">
                            Matching text in the transcript and call log is replaced with a placeholder
                            before it is stored.{" "}
                            {gov.storage_mode === "except_pii" && gov.redaction_categories.length === 0
                                ? "With none ticked, every kind below is removed."
                                : "Tick the kinds to remove."}{" "}
                            This finds numbers and fixed formats; it does not catch names, or numbers
                            spoken as words.
                        </p>
                    </div>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {REDACTION_CATEGORIES.map((c) => (
                            <label key={c.value} className="flex items-center gap-2 text-sm">
                                <Checkbox
                                    checked={gov.redaction_categories.includes(c.value)}
                                    onCheckedChange={(v) =>
                                        patch({ redaction_categories: toggle(gov.redaction_categories, c.value, v === true) })
                                    }
                                />
                                {c.label}
                            </label>
                        ))}
                    </div>
                    <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1">
                            <Label htmlFor="gov_redact_context" className="text-xs">
                                Also remove them from the details captured during the call
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                Off by default: those details feed webhooks and integrations, which would
                                receive placeholders instead of real values.
                            </p>
                        </div>
                        <Switch
                            id="gov_redact_context"
                            checked={gov.redact_gathered_context}
                            onCheckedChange={(v) => patch({ redact_gathered_context: v })}
                        />
                    </div>
                </div>

                <Separator />

                {/* Guardrails */}
                <div className="space-y-4">
                    <div className="space-y-1">
                        <Label className="text-xs">Safety checks</Label>
                        <p className="text-xs text-muted-foreground">
                            The caller&apos;s words are screened live, at no cost to response time. The agent&apos;s
                            replies are reviewed after the call and recorded on the call&apos;s details; they are
                            not held back while the call is running.
                        </p>
                    </div>
                    <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1">
                            <Label htmlFor="gov_jailbreak" className="text-xs">
                                Catch callers trying to override the agent
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                Spots attempts like &quot;ignore your instructions&quot; or &quot;reveal your prompt&quot;.
                                Not available with realtime voice models.
                            </p>
                        </div>
                        <Switch
                            id="gov_jailbreak"
                            checked={gov.guardrails.input_jailbreak}
                            onCheckedChange={(v) => patchGuardrails({ input_jailbreak: v })}
                        />
                    </div>
                    {gov.guardrails.input_jailbreak && (
                        <div className="space-y-2">
                            <Label className="text-xs">When one is caught</Label>
                            <Select
                                value={gov.guardrails.on_violation}
                                onValueChange={(v) => patchGuardrails({ on_violation: v as GuardrailAction })}
                            >
                                <SelectTrigger className="max-w-sm">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {ACTIONS.map((a) => (
                                        <SelectItem key={a.value} value={a.value}>
                                            {a.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground">{action?.hint}</p>
                        </div>
                    )}
                    <div className="space-y-2">
                        <Label className="text-xs">Review the agent&apos;s replies for</Label>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            {GUARDRAIL_CATEGORIES.map((c) => (
                                <label key={c.value} className="flex items-center gap-2 text-sm">
                                    <Checkbox
                                        checked={gov.guardrails.output_categories.includes(c.value)}
                                        onCheckedChange={(v) =>
                                            patchGuardrails({
                                                output_categories: toggle(gov.guardrails.output_categories, c.value, v === true),
                                            })
                                        }
                                    />
                                    {c.label}
                                </label>
                            ))}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Uses the agent&apos;s own language model after the call, so it adds to that
                            call&apos;s model usage.
                        </p>
                    </div>
                </div>
            </CardContent>
            <CardFooter className="justify-end gap-3 border-t pt-6">
                {isDirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
                <Button onClick={handleSave} disabled={isSaving || !isDirty}>
                    {isSaving ? "Saving..." : "Save Data & Safety"}
                </Button>
            </CardFooter>
        </Card>
    );
}
