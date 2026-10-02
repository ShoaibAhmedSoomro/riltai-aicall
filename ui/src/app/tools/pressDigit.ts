export const MAX_PRESS_DIGITS = 32;

/** What is wrong with the keys, or null. Mirrors the server (digits 0-9, * and #). */
export function validatePressDigits(digits: string): string | null {
    const text = digits.trim();
    if (!text) return 'Enter the keys to press, for example "1"';
    if (text.length > MAX_PRESS_DIGITS) return `At most ${MAX_PRESS_DIGITS} keys`;
    const bad = [...text].find((ch) => !/[0-9*#]/.test(ch));
    if (bad !== undefined) {
        return bad === ' ' ? 'Remove the spaces: type the keys together, like "123#"' : `"${bad}" is not a phone key. Use 0-9, * and #`;
    }
    return null;
}
