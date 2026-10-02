/**
 * Pure helpers for the template gallery, kept apart from the components so the
 * rules (which chips show, what the new agent is called, what the preview lists)
 * are tested without rendering.
 */

// The order chips appear in. Any category the server adds later still shows,
// after these, labelled from its slug.
const CATEGORY_ORDER = [
    'receptionist',
    'appointment-booking',
    'customer-support',
    'lead-qualification',
    'outbound-sales',
] as const;

const CATEGORY_LABELS: Record<string, string> = {
    receptionist: 'Receptionist',
    'appointment-booking': 'Appointment booking',
    'customer-support': 'Customer support',
    'lead-qualification': 'Lead qualification',
    'outbound-sales': 'Outbound sales',
    general: 'General',
};

export function categoryLabel(slug: string): string {
    if (CATEGORY_LABELS[slug]) return CATEGORY_LABELS[slug];
    const words = slug.replace(/[-_]+/g, ' ').trim();
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : 'General';
}

interface HasCategory {
    category: string;
}

/** The categories that have at least one template, in display order. */
export function categoriesOf(templates: HasCategory[]): string[] {
    const present = new Set(templates.map((t) => t.category));
    const known = CATEGORY_ORDER.filter((c) => present.has(c));
    const extra = [...present].filter((c) => !(CATEGORY_ORDER as readonly string[]).includes(c)).sort();
    return [...known, ...extra];
}

/** `null` means all. */
export function filterByCategory<T extends HasCategory>(templates: T[], category: string | null): T[] {
    return category ? templates.filter((t) => t.category === category) : templates;
}

/** What a new agent made from this template is called: the name, not "Copy of". */
export function defaultAgentName(templateName: string): string {
    return templateName.trim() || 'New agent';
}

interface PreviewNode {
    type?: string;
    data?: { name?: string; prompt?: string };
}

/**
 * The steps a call goes through, for the preview: every node except the global
 * persona, in the order the definition lists them (generated templates list them
 * top to bottom). The global node is described separately.
 */
export function previewSteps(definition: { nodes?: PreviewNode[] } | null | undefined): string[] {
    return (definition?.nodes ?? [])
        .filter((n) => n.type !== 'globalNode')
        .map((n) => n.data?.name?.trim() || '')
        .filter(Boolean);
}
