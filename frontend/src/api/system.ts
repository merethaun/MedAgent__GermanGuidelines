import {useCallback} from "react";
import {useAuthedFetch} from "./http";

// ----- Types mirroring backend -----

export type RetrievalResult = {
  // keep minimal; not needed for list page
  [k: string]: any;
};

export type WorkflowComponentExecutionResult = {
  component_id: string;
  execution_order: number;
  input: Record<string, any>;
  output: Record<string, any>;
};

export type ChatInteraction = {
  user_input: string;
  time_question_input: string; // datetime ISO string from FastAPI/Pydantic
  generator_output?: string | null;
  time_response_output?: string | null;
  retrieval_output: RetrievalResult[];
  retrieval_latency?: number | null;
  workflow_execution: WorkflowComponentExecutionResult[];
};

export type Chat = {
  _id?: any; // ObjectId serialized (string or {$oid: string})
  name?: string | null;
  workflow_system_id: any; // ObjectId serialized
  username: string;
  interactions: ChatInteraction[];
};

export type NodeConfig = {
  component_id: string;
  name: string;
  type: string;
  parameters: Record<string, any>;
};

export type EdgeConfig = {
  source: string;
  target: string;
};

export type WorkflowConfig = {
  _id?: any;
  name: string;
  nodes: NodeConfig[];
  edges: EdgeConfig[];
};

// ----- Helpers -----

function qs(params: Record<string, string | undefined>) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== "") sp.set(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function readBodySafe(res: Response) {
  const text = await res.text().catch(() => "");
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

/**
 * Normalize Mongo ObjectId representations coming from FastAPI/Pydantic
 * (string, {$oid: string}, "ObjectId('...')", etc.) to a 24-hex string.
 */
export function normalizeObjectId(v: any): string {
  if (!v) return "";
  if (typeof v === "string") {
    const m = v.match(/[0-9a-fA-F]{24}/);
    return m ? m[0] : v;
  }
  if (typeof v === "object") {
    if (typeof v.$oid === "string") return v.$oid;
    if (typeof v.oid === "string") return v.oid;
    if (typeof v.id === "string") return v.id;
    if (typeof v._id === "string") return v._id;
  }
  return String(v);
}

// ----- Hook API -----

export function useSystemApi() {
  const authedFetch = useAuthedFetch();

  const listChats = useCallback(
    async (args?: { user_name?: string; workflow_id?: string }) => {
      const query = qs({user_name: args?.user_name, workflow_id: args?.workflow_id});
      const res = await authedFetch(`/system/chats${query}`, {method: "GET"});
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(`GET /system/chats failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`);
      }
      return (await res.json()) as Chat[];
    },
    [authedFetch],
  );

  const getWorkflowById = useCallback(
    async (wfId: string) => {
      const res = await authedFetch(`/system/workflows/${encodeURIComponent(wfId)}`, {method: "GET"});
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `GET /system/workflows/${wfId} failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return (await res.json()) as WorkflowConfig;
    },
    [authedFetch],
  );

  return {listChats, getWorkflowById};
}
