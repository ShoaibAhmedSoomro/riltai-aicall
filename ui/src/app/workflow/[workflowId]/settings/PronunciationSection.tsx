"use client";

import { AlertTriangle, Plus, Trash2, Volume2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import { detailFromError } from "@/lib/apiError";
import type { SpeechNormalization, WorkflowConfigurations } from "@/types/workflow-configurations";

import {
    applyForm,
    formFromConfig,
    isDirty,
    MAX_FROM,
    MAX_OVERRIDES,
    MAX_TO,
    NEW_OVERRIDE,
    type PronunciationForm,
    validateForm,
} from "./pronunciation";

const PUBLISH_REMINDER = "Publish the agent to apply the changes.";

const FORMATTING: Array<{ key: Exclude<keyof SpeechNormalization, "enabled" | "number_digit_cutoff">; label: string; example: string }> = [
    { key: "strip_markdown", label: "Remove markdown", example: "**bold** is read as bold" },
    { key: "expand_phone_numbers", label: "Phone numbers digit by digit", example: "0501234567" },
    { key: "normalize_acronyms", label: "Spell out acronyms", example: "API is read A P I" },
    { key: "expand_currency", label: "Money amounts", example: "$42.50 is forty-two dollars fifty" },
    { key: "expand_numbers", label: "Numbers as words", example: "120 is one hundred twenty" },
    { key: "expand_percentages", label: "Percentages", example: "50% is fifty percent" },
    { key: "expand_units", label: "Units", example: "5km is five kilometers" },
    { key: "email_to_speech", label: "Email addresses", example: "a@b.com is a at b dot com" },
    { key: "normalize_dates", label: "Dates", example: "2026-10-02 is October second" },
];

export function PronunciationSection({
    workflowConfigurations,
    workflowName,
    usesRealtime,
    onSave,
}: {
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    /** True when the agent runs on a speech-to-speech model: no text-to-speech stage. */
    usesRealtime: boolean;
    onSave: (configurations: WorkflowConfigurations, workflowName: string) => Promise<void>;
}) {
    const initial = useMemo(() => formFromConfig(workflowConfigurations), [workflowConfigurations]);
    const [form, setForm] = useState<PronunciationForm>(initial);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const dirty = isDirty(form, initial);
    useUnsavedChanges("pronunciation", dirty);

    const setRow = (index: number, patch: Partial<(typeof form.overrides)[number]>) =>
        setForm((f) => ({ ...f, overrides: f.overrides.map((o, i) => (i === index ? { ...o, ...patch } : o)) }));
    const setNormalization = (patch: Partial<SpeechNormalization>) =>
        setForm((f) => ({ ...f, normalization: { ...f.normalization, ...patch } }));

    const save = async () => {
        const problem = validateForm(form);
        if (problem) {
            setError(problem);
            return;
        }
        setError(null);
        setSaving(true);
        try {
            await onSave(applyForm(workflowConfigurations, form), workflowName);
            toast.success(`Pronunciation saved. ${PUBLISH_REMINDER}`);
        } catch (e) {
            setError(detailFromError(e, "Could not save pronunciation"));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card id="pronunciation">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <Volume2 className="h-4 w-4" />
                    Pronunciation
                </CardTitle>
                <CardDescription>
                    Changes how the agent <strong>says</strong> things. The Dictionary above works the other way: it helps the
                    agent <strong>hear</strong> words. Use this when a name, brand or abbreviation is spoken wrongly.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {usesRealtime && (
                    <div role="alert" className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                        <p>
                            This agent uses a speech-to-speech model, which speaks directly and has no text-to-speech step to
                            change. These settings will have no effect until the agent uses a separate voice.
                        </p>
                    </div>
                )}

                <div className="space-y-3">
                    <div className="hidden grid-cols-[1fr_1fr_auto_auto_auto] gap-3 text-xs font-medium text-muted-foreground sm:grid">
                        <span>Say this</span>
                        <span>Speak it as</span>
                        <span>Whole word</span>
                        <span>Match case</span>
                        <span className="w-9" />
                    </div>
                    {form.overrides.length === 0 && (
                        <p className="text-sm text-muted-foreground">
                            No pronunciations yet. For example: say <code>AED</code> as <code>dirhams</code>.
                        </p>
                    )}
                    {form.overrides.map((o, i) => (
                        <div key={i} className="grid items-center gap-3 sm:grid-cols-[1fr_1fr_auto_auto_auto]">
                            <Input
                                aria-label={`Say this, row ${i + 1}`}
                                value={o.from_text}
                                maxLength={MAX_FROM}
                                onChange={(e) => setRow(i, { from_text: e.target.value })}
                                placeholder="AED"
                            />
                            <Input
                                aria-label={`Speak it as, row ${i + 1}`}
                                value={o.to_text}
                                maxLength={MAX_TO}
                                onChange={(e) => setRow(i, { to_text: e.target.value })}
                                placeholder="dirhams"
                            />
                            <label className="flex items-center gap-1.5 text-sm">
                                <Checkbox checked={o.whole_word} onCheckedChange={(v) => setRow(i, { whole_word: v === true })} />
                                <span className="sm:sr-only">Whole word</span>
                            </label>
                            <label className="flex items-center gap-1.5 text-sm">
                                <Checkbox checked={o.match_case} onCheckedChange={(v) => setRow(i, { match_case: v === true })} />
                                <span className="sm:sr-only">Match case</span>
                            </label>
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                aria-label={`Remove row ${i + 1}`}
                                onClick={() => setForm((f) => ({ ...f, overrides: f.overrides.filter((_, j) => j !== i) }))}
                            >
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        </div>
                    ))}
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={form.overrides.length >= MAX_OVERRIDES}
                        onClick={() => setForm((f) => ({ ...f, overrides: [...f.overrides, { ...NEW_OVERRIDE }] }))}
                    >
                        <Plus className="mr-1 h-4 w-4" aria-hidden /> Add pronunciation
                    </Button>
                    <p className="text-xs text-muted-foreground">
                        Text is matched exactly as typed (symbols mean themselves). Rules apply top to bottom, before the
                        formatting below.
                    </p>
                </div>

                <details className="rounded-md border p-4" open={form.normalization.enabled}>
                    <summary className="cursor-pointer text-sm font-medium">Number &amp; date formatting</summary>
                    <div className="mt-4 space-y-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <Label htmlFor="norm-enabled">Rewrite text before it is spoken</Label>
                                <p className="text-xs text-muted-foreground">
                                    Off by default. Turning it on changes how the agent sounds, so place a test call after.
                                </p>
                            </div>
                            <Switch
                                id="norm-enabled"
                                checked={form.normalization.enabled}
                                onCheckedChange={(v) => setNormalization({ enabled: v })}
                            />
                        </div>
                        {form.normalization.enabled && (
                            <div className="grid gap-3 sm:grid-cols-2">
                                {FORMATTING.map(({ key, label, example }) => (
                                    <label key={key} className="flex items-start gap-2 text-sm">
                                        <Checkbox
                                            checked={form.normalization[key]}
                                            onCheckedChange={(v) => setNormalization({ [key]: v === true })}
                                            className="mt-0.5"
                                        />
                                        <span>
                                            {label}
                                            <span className="block text-xs text-muted-foreground">{example}</span>
                                        </span>
                                    </label>
                                ))}
                                {form.normalization.expand_numbers && (
                                    <div className="space-y-1 sm:col-span-2">
                                        <Label htmlFor="norm-cutoff">Read numbers above this digit by digit</Label>
                                        <Input
                                            id="norm-cutoff"
                                            className="max-w-[10rem]"
                                            inputMode="numeric"
                                            value={form.normalization.number_digit_cutoff ?? ""}
                                            onChange={(e) =>
                                                setNormalization({
                                                    number_digit_cutoff: e.target.value.trim() === "" ? null : Number(e.target.value),
                                                })
                                            }
                                        />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </details>

                {error && (
                    <p role="alert" className="text-sm text-destructive">
                        {error}
                    </p>
                )}
            </CardContent>
            <CardFooter className="justify-end gap-3 border-t pt-6">
                {dirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
                <Button onClick={save} disabled={saving || !dirty}>
                    {saving ? "Saving..." : "Save Pronunciation"}
                </Button>
            </CardFooter>
        </Card>
    );
}
