import type { OrgPhoneNumberResponse } from "@/client/types.gen";

/**
 * Does this number match what was typed? Looks at the number (ignoring spacing
 * and punctuation, so "050 123" finds "+971501234567"), its label, the agent
 * that answers it, and its provider.
 */
export function matchesPhoneNumber(
    n: Pick<
        OrgPhoneNumberResponse,
        "address" | "address_normalized" | "label" | "inbound_workflow_name" | "telephony_configuration_name" | "telephony_provider"
    >,
    query: string,
): boolean {
    const q = query.trim().toLowerCase();
    if (!q) return true;

    const text = [n.label, n.inbound_workflow_name, n.telephony_configuration_name, n.telephony_provider]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
    if (text.includes(q)) return true;

    // Compare digits only, so spaces, dashes and the leading + do not matter.
    const digits = q.replace(/\D/g, "");
    if (digits.length === 0) return false;
    const haystack = `${n.address}${n.address_normalized}`.replace(/\D/g, "");
    return haystack.includes(digits);
}
