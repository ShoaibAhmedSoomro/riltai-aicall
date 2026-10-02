/** Small, pure helpers for the contacts pages. */

import type { ContactResponse } from "@/client/types.gen";

/** The standard fields. A custom field must not reuse one (the API refuses it too). */
export const RESERVED_FIELD_NAMES = ["phone_number", "first_name", "last_name", "email", "contact_uuid"];

/** What the API accepts as a custom field name: a template-variable-safe identifier. */
export const FIELD_NAME_RE = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

export function contactName(c: Pick<ContactResponse, "first_name" | "last_name">): string | null {
    const name = [c.first_name, c.last_name].filter(Boolean).join(" ").trim();
    return name || null;
}

export function validateFieldName(name: string, taken: string[] = []): string | null {
    if (!FIELD_NAME_RE.test(name)) {
        return "Use letters, digits and underscores, starting with a letter";
    }
    if (RESERVED_FIELD_NAMES.includes(name)) return `"${name}" is a standard field`;
    if (taken.includes(name)) return "That field already exists";
    return null;
}

/**
 * A usable custom-field name from a CSV header: "Employer Name" → "employer_name".
 * Never returns a reserved name or one in `taken`, so a column can always be kept.
 */
export function fieldNameFromHeader(header: string, taken: string[] = []): string {
    let name = header
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");
    if (!name) name = "field";
    if (!/^[a-z]/.test(name)) name = `f_${name}`;
    name = name.slice(0, 64);
    const unavailable = new Set([...taken, ...RESERVED_FIELD_NAMES]);
    let candidate = name;
    for (let i = 2; unavailable.has(candidate); i++) {
        candidate = `${name.slice(0, 60)}_${i}`;
    }
    return candidate;
}

export type ColumnGuess = {
    phone_number: string | null;
    first_name: string | null;
    last_name: string | null;
    email: string | null;
};

const GUESSES: [keyof ColumnGuess, RegExp][] = [
    ["email", /e-?mail/i],
    ["first_name", /^(first|given)[\s_-]*(name)?$/i],
    ["last_name", /^(last|sur|family)[\s_-]*(name)?$/i],
    ["phone_number", /phone|mobile|cell|msisdn|\btel\b|whatsapp|contact[\s_-]*(no|number)|number/i],
];

/** Pre-select the obvious columns so the mapping step starts mostly done. */
export function guessColumns(headers: string[]): ColumnGuess {
    const guess: ColumnGuess = { phone_number: null, first_name: null, last_name: null, email: null };
    const used = new Set<string>();
    for (const [field, pattern] of GUESSES) {
        const hit = headers.find((h) => !used.has(h) && pattern.test(h.trim()));
        if (hit) {
            guess[field] = hit;
            used.add(hit);
        }
    }
    return guess;
}

/** Numbers pasted one per line, or separated by commas or semicolons. */
export function parsePhoneList(text: string): string[] {
    return text
        .split(/[\n\r,;]+/)
        .map((s) => s.trim())
        .filter(Boolean);
}

export function importSummary(imp: {
    created_count?: number;
    updated_count?: number;
    skipped_count?: number;
    invalid_count?: number;
    mode?: string;
}): string {
    const created = imp.created_count ?? 0;
    const updated = imp.updated_count ?? 0;
    const skipped = imp.skipped_count ?? 0;
    const invalid = imp.invalid_count ?? 0;
    const noun = imp.mode === "suppression" ? "added to the do-not-call list" : "new";
    const parts = [`${created.toLocaleString()} ${noun}`];
    if (updated) parts.push(`${updated.toLocaleString()} updated`);
    if (skipped) {
        parts.push(`${skipped.toLocaleString()} ${imp.mode === "suppression" ? "already on the list" : "already existed"}`);
    }
    if (invalid) parts.push(`${invalid.toLocaleString()} rejected`);
    return parts.join(" · ");
}
