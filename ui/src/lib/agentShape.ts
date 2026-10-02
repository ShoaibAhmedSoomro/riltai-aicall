/**
 * Does this agent have the shape of a single prompt: one start, one end, one edge
 * between them, and no global persona?
 *
 * That shape runs as exactly one prompt (the engine composes the start node's prompt
 * and nothing else, plus the one `end_call` transition), so a prompt-only editor can
 * show it honestly. It is derived from the graph and never stored: there is no flag
 * to keep in sync, and the moment someone adds a node on the canvas the shape stops
 * matching.
 */
interface ShapeNode {
    id: string;
    type?: string;
}
interface ShapeEdge {
    source: string;
    target: string;
}

export function isSinglePromptShape(
    nodes: ShapeNode[] | null | undefined,
    edges: ShapeEdge[] | null | undefined,
): boolean {
    if (!nodes || !edges) return false;
    if (nodes.length !== 2 || edges.length !== 1) return false;
    const start = nodes.find((n) => n.type === 'startCall');
    const end = nodes.find((n) => n.type === 'endCall');
    if (!start || !end) return false;
    return edges[0].source === start.id && edges[0].target === end.id;
}
