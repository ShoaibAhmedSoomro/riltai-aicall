import type { LucideIcon } from 'lucide-react';
import {
    Bot,
    FileAudio,
    FileText,
    KeyRound,
    Megaphone,
    PhoneCall,
    SlidersHorizontal,
    Wrench,
} from 'lucide-react';

/**
 * The create-shaped actions a user can actually complete, in one place, so the
 * top-bar menu and the dashboard panel cannot drift apart.
 *
 * Only three creates in this app are reachable by a plain URL:
 * /workflow/create, /campaigns/new, and /telephony-configurations?add=1 (the one
 * page that reads a query param to open its own dialog). Everything else lives
 * in a useState dialog inside a specific page with no deep-link support, so
 * those entries navigate to the page and `landsOnPage` marks them as such: the
 * menu says "Open" rather than implying a dialog will appear.
 *
 * Two things a reference dashboard would offer are deliberately absent. There is
 * no "new agent from template": the endpoints exist but the gallery component is
 * rendered nowhere, so it would be a dead end. And "new model configuration" is
 * not a create at all, it is a single org-level save, so it appears as
 * "Configure AI models" instead.
 */
export interface QuickAction {
    id: string;
    label: string;
    /** One short line for the dashboard panel; the menu shows label only. */
    description: string;
    href: string;
    icon: LucideIcon;
    /**
     * False when the href opens the create form directly. True when it only
     * lands on the page that owns the form.
     */
    landsOnPage: boolean;
    /** Shown when the action can fail for a fresh organization. */
    precondition?: string;
}

export const QUICK_ACTIONS: QuickAction[] = [
    {
        id: 'agent',
        label: 'New voice agent',
        description: 'Build a call flow in the visual editor',
        href: '/workflow/create',
        icon: Bot,
        landsOnPage: false,
    },
    {
        id: 'campaign',
        label: 'New campaign',
        description: 'Dial a list of contacts with an agent',
        href: '/campaigns/new',
        icon: Megaphone,
        landsOnPage: false,
        // The form needs all four before it can be submitted.
        precondition: 'Needs an active agent, a telephony configuration and a contact CSV',
    },
    {
        id: 'telephony',
        label: 'Connect telephony',
        description: 'Add a provider or your own SIP carrier',
        href: '/telephony-configurations?add=1',
        icon: PhoneCall,
        landsOnPage: false,
    },
    {
        id: 'models',
        label: 'Configure AI models',
        description: 'Set the LLM, speech-to-text and voice',
        href: '/model-configurations',
        icon: SlidersHorizontal,
        landsOnPage: true,
    },
    {
        id: 'tool',
        label: 'New tool',
        description: 'Let an agent call your API mid-conversation',
        href: '/tools',
        icon: Wrench,
        landsOnPage: true,
    },
    {
        id: 'document',
        label: 'Upload knowledge',
        description: 'Give an agent documents to answer from',
        href: '/files',
        icon: FileText,
        landsOnPage: true,
    },
    {
        id: 'recording',
        label: 'Upload audio',
        description: 'Add pre-recorded prompts an agent can play',
        href: '/recordings',
        icon: FileAudio,
        landsOnPage: true,
    },
    {
        id: 'apikey',
        label: 'Create API key',
        description: 'Trigger calls from your own code',
        href: '/api-keys',
        icon: KeyRound,
        landsOnPage: true,
    },
];
