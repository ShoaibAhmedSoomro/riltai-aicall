import { Eye } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import { categoryLabel } from './templates';

interface TemplateCardProps {
    name: string;
    description: string;
    category: string;
    onPreview: () => void;
}

/** One card in the gallery. Presentational: the gallery owns fetching and creating. */
export function TemplateCard({ name, description, category, onPreview }: TemplateCardProps) {
    return (
        <div className="flex flex-col rounded-lg border bg-card p-4 text-card-foreground shadow-sm transition-shadow hover:shadow-md">
            <Badge variant="secondary" className="mb-3 w-fit">
                {categoryLabel(category)}
            </Badge>
            <h3 className="mb-1 text-base font-semibold">{name}</h3>
            <p className="mb-4 flex-1 text-sm text-muted-foreground">{description}</p>
            <Button variant="outline" className="w-full" onClick={onPreview}>
                <Eye className="mr-2 h-4 w-4" />
                Preview and use
            </Button>
        </div>
    );
}
