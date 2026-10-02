"use client";

import { Loader2, Sparkles, Square } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConversationTimeline } from "@/components/workflow/conversation";

import { DisabledNotice, TypingIndicator } from "./shared";
import { useSimulatedChat } from "./useSimulatedChat";

export const DEFAULT_PERSONA =
    "Act like a skeptical prospect. Push on pricing, ask about integrations, and end the chat if the assistant becomes repetitive.";
const DEFAULT_TURNS = 8;
const MAX_TURNS = 20;

export function AiSimulatorPanel({
    workflowId,
    initialContextVariables,
    disabled,
    disabledReason,
}: {
    workflowId: number;
    initialContextVariables?: Record<string, string>;
    disabled: boolean;
    disabledReason: string | null;
}) {
    const [persona, setPersona] = useState(DEFAULT_PERSONA);
    const [turnsText, setTurnsText] = useState(String(DEFAULT_TURNS));
    const sim = useSimulatedChat({ workflowId, initialContextVariables, disabled });

    const turns = Math.min(MAX_TURNS, Math.max(1, Number.parseInt(turnsText, 10) || DEFAULT_TURNS));
    const idle = sim.phase === "idle" || sim.phase === "error";
    const running = sim.phase === "starting" || sim.phase === "running";

    return (
        <div className="flex min-h-0 flex-1 flex-col gap-3">
            {disabledReason ? <DisabledNotice reason={disabledReason} /> : null}

            {idle ? (
                <>
                    <p className="text-sm text-muted-foreground">
                        A pretend caller talks to this agent for you. Describe who they are; the run is then scored by
                        your quality checks like any other call.
                    </p>
                    <div className="space-y-2">
                        <Label htmlFor="sim-persona">The caller</Label>
                        <Textarea
                            id="sim-persona"
                            value={persona}
                            onChange={(event) => setPersona(event.target.value)}
                            maxLength={2000}
                            placeholder="Describe the simulated caller..."
                            className="min-h-32 resize-none text-sm leading-6"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="sim-turns">Longest conversation (caller turns, up to {MAX_TURNS})</Label>
                        <Input
                            id="sim-turns"
                            className="max-w-[6rem]"
                            inputMode="numeric"
                            value={turnsText}
                            onChange={(event) => setTurnsText(event.target.value)}
                        />
                    </div>
                    {sim.error ? (
                        <p role="alert" className="text-sm text-destructive">
                            {sim.error}
                        </p>
                    ) : null}
                    <Button
                        size="sm"
                        className="self-start"
                        disabled={disabled || !persona.trim()}
                        onClick={() => void sim.run(persona.trim(), turns)}
                    >
                        <Sparkles className="h-4 w-4" />
                        Run simulation
                    </Button>
                </>
            ) : (
                <>
                    <div className="min-h-0 flex-1">
                        <ConversationTimeline
                            items={sim.items}
                            autoScroll={true}
                            scrollBehavior="smooth"
                            emptyState={{
                                title: "Starting the simulation",
                                subtitle: "The agent speaks first, then the pretend caller replies.",
                            }}
                            pendingIndicator={running ? <TypingIndicator /> : null}
                            className="py-1"
                        />
                    </div>
                    <div className="flex items-center justify-between gap-3 border-t border-border/70 pt-3">
                        <p className="text-xs text-muted-foreground" role="status">
                            {running
                                ? `Running… ${sim.turns.filter((t) => t.user_message).length} caller turns so far`
                                : "Simulation finished. Its quality scores appear on the call's page."}
                        </p>
                        {running ? (
                            <Button type="button" variant="outline" size="sm" onClick={() => void sim.stop()}>
                                {sim.phase === "starting" ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                    <Square className="h-3.5 w-3.5" />
                                )}
                                Stop
                            </Button>
                        ) : (
                            <Button type="button" variant="outline" size="sm" onClick={sim.reset}>
                                New simulation
                            </Button>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
