/**
 * Initials-based avatars.
 *
 * There is no user image anywhere in this product: the users table stores none,
 * and the hosted provider's picture is not exposed through the shared auth
 * context. Rather than fetch a third-party gravatar or invent an upload path,
 * the avatar is the user's initials on a colour they pick.
 *
 * The colour set is closed and mirrors AVATAR_COLORS in api/schemas/auth.py,
 * which rejects anything outside it. A free hex would let someone choose
 * something illegible on their own dashboard, and these are the only pairings
 * checked to hold up in both the light and dark themes.
 */

export const AVATAR_COLORS = ['slate', 'teal', 'indigo', 'amber', 'rose', 'violet'] as const;

export type AvatarColor = (typeof AVATAR_COLORS)[number];

/**
 * Background and foreground for each choice.
 *
 * Deliberately not the --chart-* tokens: those are tuned to be distinguishable
 * from each other as chart series, not to carry small text. These are solid
 * fills with white text, which stays legible at 24px.
 */
export const AVATAR_COLOR_CLASS: Record<string, string> = {
    slate: 'bg-slate-600 text-white',
    teal: 'bg-teal-600 text-white',
    indigo: 'bg-indigo-600 text-white',
    amber: 'bg-amber-600 text-white',
    rose: 'bg-rose-600 text-white',
    violet: 'bg-violet-600 text-white',
};

/**
 * Up to two initials from a display name, falling back to the email local part.
 *
 * Splits on spaces, dots, underscores and hyphens so "ali.shifaz" and
 * "ali_shifaz" both yield "AS" rather than "AL".
 */
export function avatarInitials(name?: string | null, email?: string | null): string {
    const source = (name || '').trim() || (email || '').split('@')[0] || '';
    const parts = source.split(/[\s._-]+/).filter(Boolean);
    if (!parts.length) return '?';
    return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase();
}
