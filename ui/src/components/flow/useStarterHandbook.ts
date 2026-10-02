import { useState } from "react";
import { toast } from "sonner";

import { getPromptingGuideTopicApiV1PromptingGuideTopicIdGet } from "@/client/sdk.gen";
import { detailFromError } from "@/lib/apiError";

import { applyStarter } from "./starterHandbook";

/**
 * "Insert starter handbook" for a prompt field. The text is fetched from the server
 * so there is one copy (shared with the MCP guide); it is added to the prompt, never
 * replacing what is written there.
 */
export function useStarterHandbook() {
    const [inserting, setInserting] = useState(false);

    const insert = async (current: string, onChange: (next: string) => void) => {
        setInserting(true);
        const res = await getPromptingGuideTopicApiV1PromptingGuideTopicIdGet({
            path: { topic_id: "common_guidelines" },
        }).catch(() => null);
        setInserting(false);
        const starter = (res?.data as { starter_template?: string } | undefined)?.starter_template;
        if (!res || res.error || !starter) {
            toast.error(detailFromError(res?.error, "Could not load the starter handbook"));
            return;
        }
        onChange(applyStarter(current, starter));
    };

    return { insert, inserting };
}
