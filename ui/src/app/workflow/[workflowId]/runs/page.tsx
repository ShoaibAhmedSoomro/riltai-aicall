"use client";

import { useParams, useSearchParams } from "next/navigation";

import { AgentTabs } from "../AgentTabs";
import { WorkflowExecutions } from "../components/WorkflowExecutions";

export default function WorkflowRunsPage() {
    const { workflowId } = useParams();
    const searchParams = useSearchParams();

    return (
        <>
            <AgentTabs workflowId={Number(workflowId)} />
            <WorkflowExecutions
                workflowId={Number(workflowId)}
                searchParams={searchParams}
            />
        </>
    );
}
