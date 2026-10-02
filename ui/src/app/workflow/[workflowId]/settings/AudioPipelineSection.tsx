"use client";

import { AudioLines } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import { detailFromError } from "@/lib/apiError";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import {
    applyForm,
    type AudioPipelineForm,
    BACKUP_VOICE_PROVIDERS,
    type DenoisingMode,
    formFromConfig,
    isFormDirty,
    validateAudioForm,
} from "./audioPipeline";

const PUBLISH_REMINDER = "Publish the agent to apply the changes.";

export function AudioPipelineSection({
    workflowConfigurations,
    workflowName,
    onSave,
}: {
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    onSave: (configurations: WorkflowConfigurations, workflowName: string) => Promise<void>;
}) {
    const initial = useMemo(() => formFromConfig(workflowConfigurations), [workflowConfigurations]);
    const [form, setForm] = useState<AudioPipelineForm>(initial);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const dirty = isFormDirty(form, initial);

    useUnsavedChanges("audio", dirty);

    const set = <K extends keyof AudioPipelineForm>(key: K, value: AudioPipelineForm[K]) =>
        setForm((f) => ({ ...f, [key]: value }));

    const save = async () => {
        const problem = validateAudioForm(form);
        if (problem) {
            setError(problem);
            return;
        }
        setError(null);
        setSaving(true);
        try {
            await onSave(applyForm(workflowConfigurations, form), workflowName);
            toast.success(`Audio and call settings saved. ${PUBLISH_REMINDER}`);
        } catch (e) {
            setError(detailFromError(e, "Could not save these settings"));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card id="audio">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <AudioLines className="h-4 w-4" />
                    Audio &amp; Calls
                </CardTitle>
                <CardDescription>
                    How the agent hears the caller, handles keypresses and phone menus, and what it does if its voice provider fails.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                <div className="space-y-2">
                    <Label htmlFor="audio-denoising">Background noise</Label>
                    <Select value={form.denoising} onValueChange={(v) => set("denoising", v as DenoisingMode)}>
                        <SelectTrigger id="audio-denoising" className="max-w-xs">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="none">Off</SelectItem>
                            <SelectItem value="rnnoise">Reduce background noise</SelectItem>
                        </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                        Cleans the caller&apos;s audio before the agent listens. It also changes how the agent decides the caller
                        has started or stopped speaking, so test a call after turning it on.
                    </p>
                </div>

                <div className="space-y-3 rounded-md border p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <Label htmlFor="audio-dtmf">Caller keypad</Label>
                            <p className="text-xs text-muted-foreground">
                                Let the agent hear keys the caller presses (&quot;press 1 to confirm&quot;). Pressing a key
                                interrupts the agent.
                            </p>
                        </div>
                        <Switch id="audio-dtmf" checked={form.dtmfEnabled} onCheckedChange={(v) => set("dtmfEnabled", v)} />
                    </div>
                    {form.dtmfEnabled && (
                        <div className="space-y-2">
                            <Label htmlFor="audio-dtmf-timeout">Wait for more keys (seconds)</Label>
                            <Input
                                id="audio-dtmf-timeout"
                                className="max-w-[8rem]"
                                inputMode="decimal"
                                value={form.dtmfTimeout}
                                onChange={(e) => set("dtmfTimeout", e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground">
                                After the last key, the agent waits this long, or until the caller presses #.
                            </p>
                        </div>
                    )}
                </div>

                <div className="flex items-center justify-between rounded-md border p-4">
                    <div>
                        <Label htmlFor="audio-ivr">Hang up on phone menus</Label>
                        <p className="text-xs text-muted-foreground">
                            If an outbound call is answered by an automated menu (&quot;press 1 for billing&quot;), end it and
                            record the outcome as &quot;ivr_detected&quot;. Only the first 30 seconds are checked. Uses the
                            agent&apos;s own model.
                        </p>
                    </div>
                    <Switch id="audio-ivr" checked={form.ivrEnabled} onCheckedChange={(v) => set("ivrEnabled", v)} />
                </div>

                <div className="space-y-3 rounded-md border p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <Label htmlFor="audio-fallback">Backup voice</Label>
                            <p className="text-xs text-muted-foreground">
                                If the voice provider has an outage mid-call, switch to this one instead of going silent.
                            </p>
                        </div>
                        <Switch
                            id="audio-fallback"
                            checked={form.fallbackEnabled}
                            onCheckedChange={(v) => set("fallbackEnabled", v)}
                        />
                    </div>
                    {form.fallbackEnabled && (
                        <div className="grid gap-4 sm:grid-cols-2">
                            <div className="space-y-2">
                                <Label htmlFor="audio-fb-provider">Provider</Label>
                                <Select value={form.fallbackProvider} onValueChange={(v) => set("fallbackProvider", v)}>
                                    <SelectTrigger id="audio-fb-provider">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {BACKUP_VOICE_PROVIDERS.map((p) => (
                                            <SelectItem key={p.value} value={p.value}>
                                                {p.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="audio-fb-voice">Voice (optional)</Label>
                                <Input
                                    id="audio-fb-voice"
                                    value={form.fallbackVoice}
                                    onChange={(e) => set("fallbackVoice", e.target.value)}
                                    placeholder="Provider default"
                                />
                            </div>
                            <div className="space-y-2 sm:col-span-2">
                                <Label htmlFor="audio-fb-key">API key</Label>
                                <Input
                                    id="audio-fb-key"
                                    type="password"
                                    autoComplete="off"
                                    value={form.fallbackApiKey}
                                    onChange={(e) => set("fallbackApiKey", e.target.value)}
                                    placeholder="Leave empty to use your organization's key for the same provider"
                                />
                            </div>
                        </div>
                    )}
                </div>

                {error && (
                    <p role="alert" className="text-sm text-destructive">
                        {error}
                    </p>
                )}
            </CardContent>
            <CardFooter className="justify-end gap-3 border-t pt-6">
                {dirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
                <Button onClick={save} disabled={saving || !dirty}>
                    {saving ? "Saving..." : "Save Audio & Call Settings"}
                </Button>
            </CardFooter>
        </Card>
    );
}
