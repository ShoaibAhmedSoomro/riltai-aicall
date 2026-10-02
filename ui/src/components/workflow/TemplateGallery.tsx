'use client';

import { Loader2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

import {
    duplicateWorkflowTemplateApiV1WorkflowTemplatesDuplicatePost,
    getWorkflowTemplateApiV1WorkflowTemplatesTemplateIdGet,
} from '@/client/sdk.gen';
import type { WorkflowTemplateDetailResponse, WorkflowTemplateResponse } from '@/client/types.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useOnboarding } from '@/context/OnboardingContext';
import { detailFromError } from '@/lib/apiError';

import { TemplateCard } from './TemplateCard';
import { categoriesOf, categoryLabel, defaultAgentName, filterByCategory, previewSteps } from './templates';

interface TemplateGalleryProps {
    templates: WorkflowTemplateResponse[];
}

export function TemplateGallery({ templates }: TemplateGalleryProps) {
    const router = useRouter();
    const { markActionCompleted } = useOnboarding();
    const [category, setCategory] = useState<string | null>(null);
    const [chosen, setChosen] = useState<WorkflowTemplateResponse | null>(null);
    const [detail, setDetail] = useState<WorkflowTemplateDetailResponse | null>(null);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [name, setName] = useState('');
    const [creating, setCreating] = useState(false);

    const categories = categoriesOf(templates);
    const visible = filterByCategory(templates, category);

    const open = async (template: WorkflowTemplateResponse) => {
        setChosen(template);
        setDetail(null);
        setName(defaultAgentName(template.template_name));
        setLoadingDetail(true);
        const res = await getWorkflowTemplateApiV1WorkflowTemplatesTemplateIdGet({
            path: { template_id: template.id },
        }).catch(() => null);
        setLoadingDetail(false);
        if (!res || res.error || !res.data) {
            // The card still has what is needed to create; only the step list is missing.
            if (res?.error) toast.error(detailFromError(res.error, 'Could not load the preview'));
            return;
        }
        setDetail(res.data);
    };

    const close = () => {
        if (!creating) setChosen(null);
    };

    const create = async () => {
        if (!chosen || creating || !name.trim()) return;
        setCreating(true);
        const res = await duplicateWorkflowTemplateApiV1WorkflowTemplatesDuplicatePost({
            body: { template_id: chosen.id, workflow_name: name.trim() },
        }).catch(() => null);
        if (!res || res.error || !res.data) {
            toast.error(detailFromError(res?.error, 'Could not create the agent'));
            setCreating(false);
            return;
        }
        markActionCompleted('agent_from_template');
        router.push(`/workflow/${res.data.id}`);
    };

    if (templates.length === 0) {
        return (
            <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                No templates are available yet. You can still build an agent from scratch.
            </p>
        );
    }

    const steps = previewSteps(detail?.template_json as { nodes?: [] } | undefined);

    return (
        <>
            <div className="mb-6 flex flex-wrap gap-2" role="group" aria-label="Filter by category">
                <Button
                    size="sm"
                    variant={category === null ? 'default' : 'outline'}
                    aria-pressed={category === null}
                    onClick={() => setCategory(null)}
                >
                    All
                </Button>
                {categories.map((c) => (
                    <Button
                        key={c}
                        size="sm"
                        variant={category === c ? 'default' : 'outline'}
                        aria-pressed={category === c}
                        onClick={() => setCategory(c)}
                    >
                        {categoryLabel(c)}
                    </Button>
                ))}
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {visible.map((t) => (
                    <TemplateCard
                        key={t.id}
                        name={t.template_name}
                        description={t.template_description}
                        category={t.category}
                        onPreview={() => open(t)}
                    />
                ))}
            </div>

            <Dialog open={chosen !== null} onOpenChange={(o) => !o && close()}>
                <DialogContent className="sm:max-w-lg">
                    <DialogHeader>
                        <Badge variant="secondary" className="mb-1 w-fit">
                            {chosen ? categoryLabel(chosen.category) : ''}
                        </Badge>
                        <DialogTitle>{chosen?.template_name}</DialogTitle>
                        <DialogDescription>{chosen?.template_description}</DialogDescription>
                    </DialogHeader>

                    <div>
                        <p className="mb-2 text-sm font-medium">How the call goes</p>
                        {loadingDetail ? (
                            <p className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" /> Loading steps…
                            </p>
                        ) : steps.length > 0 ? (
                            <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                                {steps.map((s, i) => (
                                    <li key={`${i}-${s}`}>{s}</li>
                                ))}
                            </ol>
                        ) : (
                            <p className="text-sm text-muted-foreground">
                                Open the agent after creating it to see the full flow.
                            </p>
                        )}
                        <p className="mt-3 text-xs text-muted-foreground">
                            You get your own copy. Change the business name, prompts and voice, then test it
                            before you publish.
                        </p>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="template-agent-name">Agent name</Label>
                        <Input
                            id="template-agent-name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && create()}
                        />
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={close} disabled={creating}>
                            Cancel
                        </Button>
                        <Button onClick={create} disabled={creating || !name.trim()}>
                            {creating ? 'Creating…' : 'Use this template'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
