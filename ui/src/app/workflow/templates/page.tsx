import Link from 'next/link';

import { getWorkflowTemplatesApiV1WorkflowTemplatesGet } from '@/client/sdk.gen';
import { Button } from '@/components/ui/button';
import { TemplateGallery } from '@/components/workflow/TemplateGallery';
import { getServerAccessToken } from '@/lib/auth/server';
import logger from '@/lib/logger';

export const dynamic = 'force-dynamic';

export default async function TemplatesPage() {
    const accessToken = await getServerAccessToken();

    let error: string | null = null;
    let templates: Awaited<ReturnType<typeof getWorkflowTemplatesApiV1WorkflowTemplatesGet>>['data'] = [];

    if (!accessToken) {
        error = 'Authentication required. Please refresh the page.';
    } else {
        try {
            const res = await getWorkflowTemplatesApiV1WorkflowTemplatesGet({
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (res.error) error = 'Failed to load templates. Please try again later.';
            else templates = res.data ?? [];
        } catch (err) {
            logger.error(`Error fetching templates: ${err}`);
            error = 'Failed to load templates. Please try again later.';
        }
    }

    return (
        <div className="container mx-auto px-4 py-8">
            <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold">Start from a template</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Ready-made agents with a working call flow. Pick one, make it yours, test it, publish.
                    </p>
                </div>
                <Button asChild variant="outline">
                    <Link href="/workflow">Back to agents</Link>
                </Button>
            </div>
            {error ? <p className="text-red-500">{error}</p> : <TemplateGallery templates={templates ?? []} />}
        </div>
    );
}
