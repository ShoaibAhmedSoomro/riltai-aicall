'use client';

import { Bot, ChevronDown, LayoutTemplate, PlusIcon, Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';
import { toast } from 'sonner';

import { createWorkflowApiV1WorkflowCreateDefinitionPost } from '@/client/sdk.gen';
import { OnboardingTooltip } from '@/components/onboarding/OnboardingTooltip';
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useOnboarding } from '@/context/OnboardingContext';
import { useAuth } from '@/lib/auth';
import logger from '@/lib/logger';
import { getRandomId } from '@/lib/utils';

// Start -> End, joined by an `end_call` transition. A lone start node has no way to
// hang up (the engine only ends a call from an end node), so a blank agent must
// come with one. This shape is also what the prompt-only editor recognises
// (lib/agentShape.ts): write the prompt, test, publish.
const BLANK_WORKFLOW_DEFINITION = {
    nodes: [
        {
            id: "1",
            type: "startCall",
            position: { x: 175, y: 60 },
            data: {
                prompt: "# Goal\nYou are a helpful agent who is handing a conversation over voice with a human. This is a voice conversation, so transcripts can be error prone.\n\n## Rules\n- Language: UK English but does not have to be correct english\n- Keep responses short and 2-3 sentences max\n- If you have to repeat something that you said in your previous two turns, then rephrase a bit while keeping the same meaning. Never repeat the exact same words as in your previous 2 responses.\n\n## Speech Handling\n- There could be multiple transcription errors. \n- Accept variations: yes/yeah/yep/aye, no/nah/nope\n- If user says \"sorry?\" or \"pardon me\" or \"can you repeat\"  or \"what?\", they might not have heard you- so just repeat what you just said.\n\n### Flow\nStart by saying \"Hi\". Be polite and courteous. ",
                name: "start call",
                allow_interrupt: false,
                add_global_prompt: false,
                delayed_start: false,
                is_start: true,
                extraction_enabled: false,
            },
        },
        {
            id: "2",
            type: "endCall",
            position: { x: 175, y: 320 },
            data: {
                prompt: "Thank the caller and say a short, polite goodbye.",
                name: "end call",
                add_global_prompt: false,
                is_end: true,
                extraction_enabled: false,
            },
        },
    ],
    edges: [
        {
            id: "1-2",
            source: "1",
            target: "2",
            type: "custom",
            animated: true,
            data: {
                label: "End Call",
                condition: "The conversation is finished, the caller says goodbye, or the caller asks to end the call.",
            },
        },
    ],
    viewport: { x: 808, y: 269, zoom: 0.75 },
};

export function CreateWorkflowButton() {
    const router = useRouter();
    const { user, getAccessToken } = useAuth();
    const [isCreating, setIsCreating] = useState(false);
    const { hasCompletedAction } = useOnboarding();
    const triggerRef = useRef<HTMLButtonElement>(null);

    const handleAgentBuilder = () => {
        router.push('/workflow/create');
    };

    const handleTemplates = () => {
        router.push('/workflow/templates');
    };

    const handleBlankCanvas = async () => {
        if (isCreating || !user) return;
        setIsCreating(true);

        try {
            const accessToken = await getAccessToken();
            const name = `Workflow-${getRandomId()}`;
            const response = await createWorkflowApiV1WorkflowCreateDefinitionPost({
                body: {
                    name,
                    workflow_definition: BLANK_WORKFLOW_DEFINITION as unknown as { [key: string]: unknown },
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                router.push(`/workflow/${response.data.id}`);
            }
        } catch (err) {
            logger.error(`Error creating blank workflow: ${err}`);
            toast.error('Failed to create workflow');
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <>
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button ref={triggerRef} disabled={isCreating}>
                    <PlusIcon className="w-4 h-4" />
                    {isCreating ? 'Creating...' : 'Create Agent'}
                    <ChevronDown className="w-4 h-4" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={handleAgentBuilder} className="cursor-pointer">
                    <Bot className="w-4 h-4 mr-2" />
                    <div>
                        <div className="font-medium">Use Agent Builder</div>
                        <div className="text-xs text-muted-foreground">AI generates a workflow from your description</div>
                    </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleTemplates} className="cursor-pointer">
                    <Sparkles className="w-4 h-4 mr-2" />
                    <div>
                        <div className="font-medium">Start from a template</div>
                        <div className="text-xs text-muted-foreground">Receptionist, booking, sales and more, ready to edit</div>
                    </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleBlankCanvas} disabled={isCreating} className="cursor-pointer">
                    <LayoutTemplate className="w-4 h-4 mr-2" />
                    <div>
                        <div className="font-medium">Blank Canvas</div>
                        <div className="text-xs text-muted-foreground">Start from scratch with an empty workflow</div>
                    </div>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
        <OnboardingTooltip
            tooltipKey="template_gallery"
            targetRef={triggerRef}
            title="Skip the blank page"
            message="Start from a ready-made agent: receptionist, booking, sales and support."
            enabled={!hasCompletedAction('agent_from_template')}
            showNext={false}
        />
        </>
    );
}
