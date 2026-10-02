"use client";

import { Loader2, Sparkles } from "lucide-react";

import type { RecordingResponseSchema } from "@/client/types.gen";
import { MentionTextarea } from "@/components/flow/MentionTextarea";
import { useStarterHandbook } from "@/components/flow/useStarterHandbook";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** The slice of the start node this view reads and writes. */
export interface SinglePromptValues {
    prompt: string;
    greeting: string;
    /** An audio greeting can't be edited as text here; the flow editor owns it. */
    greetingIsAudio: boolean;
}

interface SinglePromptEditorProps {
    values: SinglePromptValues;
    onChange: (patch: Partial<Pick<SinglePromptValues, "prompt" | "greeting">>) => void;
    recordings: RecordingResponseSchema[];
    readOnly: boolean;
    onSwitchToFlow: () => void;
}

/**
 * A prompt-only view of an agent that is a single prompt. It is a view, not a
 * second model: it edits the start node of the same definition the canvas shows and
 * saves through the same path. Save, Test and Publish are the header's and the
 * tester rail's, unchanged.
 */
export function SinglePromptEditor({
    values,
    onChange,
    recordings,
    readOnly,
    onSwitchToFlow,
}: SinglePromptEditorProps) {
    const { insert, inserting } = useStarterHandbook();

    return (
        <div className="h-full overflow-y-auto">
            <div className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-8">
                <div>
                    <h2 className="text-lg font-semibold">Write the prompt</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        This agent is one prompt: the caller hears the greeting, then the agent follows
                        your instructions until the call ends. Need branching, tools or several steps?{" "}
                        <button
                            type="button"
                            onClick={onSwitchToFlow}
                            className="font-medium text-primary underline-offset-2 hover:underline"
                        >
                            Switch to the flow editor
                        </button>
                        .
                    </p>
                </div>

                <div className="grid gap-2">
                    <Label htmlFor="single-prompt-greeting">Greeting</Label>
                    <Input
                        id="single-prompt-greeting"
                        value={values.greeting}
                        disabled={readOnly || values.greetingIsAudio}
                        placeholder="What the agent says first, e.g. Hello, how can I help?"
                        onChange={(e) => onChange({ greeting: e.target.value })}
                    />
                    <p className="text-xs text-muted-foreground">
                        {values.greetingIsAudio
                            ? "This agent opens with a recording. Change it in the flow editor."
                            : "Leave empty to let the agent open the call from the prompt."}
                    </p>
                </div>

                <div className="grid gap-2">
                    <div className="flex items-center justify-between gap-2">
                        <Label>Prompt</Label>
                        {!readOnly && (
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={inserting}
                                onClick={() => insert(values.prompt, (prompt) => onChange({ prompt }))}
                            >
                                {inserting ? (
                                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                ) : (
                                    <Sparkles className="mr-1 h-3 w-3" />
                                )}
                                Insert starter handbook
                            </Button>
                        )}
                    </div>
                    <MentionTextarea
                        value={values.prompt}
                        onChange={(prompt) => !readOnly && onChange({ prompt })}
                        placeholder="Who the agent is, what it should achieve on the call, and how it should sound."
                        className="min-h-[55vh] resize-y"
                        recordings={recordings}
                    />
                    <p className="text-xs text-muted-foreground">
                        Test it from the panel on the right, then Publish when it sounds right.
                    </p>
                </div>
            </div>
        </div>
    );
}
