/** Node types whose prompt field offers "Insert starter handbook". */
const NODE_TYPES_WITH_HANDBOOK = new Set(['globalNode', 'startCall']);

export function offersStarterHandbook(nodeType: string | undefined, propertyName: string): boolean {
    return propertyName === 'prompt' && !!nodeType && NODE_TYPES_WITH_HANDBOOK.has(nodeType);
}

/**
 * Put the handbook into a prompt without ever throwing away what is there: an
 * empty prompt becomes the handbook, a written one keeps its text and gets the
 * handbook after a blank line. Inserting twice does not stack copies.
 */
export function applyStarter(current: string, starter: string): string {
    const text = current.trim();
    if (!text) return starter;
    if (text.includes(starter.trim())) return current;
    return `${current.replace(/\s+$/, '')}\n\n${starter}`;
}
