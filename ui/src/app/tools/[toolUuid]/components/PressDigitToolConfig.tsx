"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { validatePressDigits } from "../../pressDigit";

export interface PressDigitToolConfigProps {
    name: string;
    onNameChange: (name: string) => void;
    description: string;
    onDescriptionChange: (description: string) => void;
    digits: string;
    onDigitsChange: (digits: string) => void;
    urgent: boolean;
    onUrgentChange: (urgent: boolean) => void;
}

export function PressDigitToolConfig({
    name,
    onNameChange,
    description,
    onDescriptionChange,
    digits,
    onDigitsChange,
    urgent,
    onUrgentChange,
}: PressDigitToolConfigProps) {
    const problem = digits === "" ? null : validatePressDigits(digits);

    return (
        <Card>
            <CardHeader>
                <CardTitle>Press Digit Configuration</CardTitle>
                <CardDescription>
                    Lets the agent press fixed keys on the call, for example to choose an option in a phone menu
                    or enter an extension. The keys are set here, not chosen by the agent.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                <div className="space-y-2">
                    <Label htmlFor="tool-name">Tool Name</Label>
                    <Input
                        id="tool-name"
                        value={name}
                        onChange={(e) => onNameChange(e.target.value)}
                        placeholder="e.g., Press 1 for billing"
                    />
                </div>

                <div className="space-y-2">
                    <Label htmlFor="tool-description">Description</Label>
                    <p className="text-xs text-muted-foreground">
                        Tell the agent exactly when to use it, e.g. &quot;Press when the menu offers billing as option 1.&quot;
                    </p>
                    <Textarea
                        id="tool-description"
                        value={description}
                        onChange={(e) => onDescriptionChange(e.target.value)}
                        placeholder="When should the agent press these keys?"
                        rows={3}
                    />
                </div>

                <div className="space-y-2">
                    <Label htmlFor="press-digits">Keys to press</Label>
                    <Input
                        id="press-digits"
                        className="font-mono"
                        value={digits}
                        onChange={(e) => onDigitsChange(e.target.value)}
                        placeholder="1"
                        aria-invalid={problem !== null}
                        aria-describedby="press-digits-help"
                        autoComplete="off"
                    />
                    <p
                        id="press-digits-help"
                        role={problem ? "alert" : undefined}
                        className={problem ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
                    >
                        {problem ?? "Digits 0-9, * and #, in order. For example 1, 0 or 123#."}
                    </p>
                </div>

                <div className="flex items-center justify-between rounded-md border p-4">
                    <div className="space-y-0.5">
                        <Label htmlFor="press-urgent">Send immediately</Label>
                        <p className="text-xs text-muted-foreground">
                            Press the keys right away, ahead of anything the agent is still saying.
                        </p>
                    </div>
                    <Switch id="press-urgent" checked={urgent} onCheckedChange={onUrgentChange} />
                </div>

                <p className="text-xs text-muted-foreground">
                    Keys are sent as tones in the call audio. A phone system that only listens for signalled keys
                    may not hear them; test against the system you are calling.
                </p>
            </CardContent>
        </Card>
    );
}
