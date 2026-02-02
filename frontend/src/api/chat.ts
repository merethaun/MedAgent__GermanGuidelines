import {useCallback} from "react";
import {useAuthedFetch} from "./http";
import {type Chat, type WorkflowConfig} from "./system";

async function readBodySafe(res: Response) {
  const text = await res.text().catch(() => "");
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export type CreateChatArgs = {
  wfId: string;
  username: string;
  name?: string | null;
};

export function useChatApi() {
  const authedFetch = useAuthedFetch();

  const listWorkflows = useCallback(async () => {
    const res = await authedFetch(`/system/workflows`, {method: "GET"});
    if (!res.ok) {
      const body = await readBodySafe(res);
      throw new Error(`GET /system/workflows failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`);
    }
    return (await res.json()) as WorkflowConfig[];
  }, [authedFetch]);

  const createChatForWorkflow = useCallback(
    async (args: CreateChatArgs) => {
      const payload = {
        workflow_system_id: args.wfId,
        username: args.username ?? "No user",
        name: args.name ?? null,
        interactions: [],
      };

      const res = await authedFetch(`/system/workflows/${encodeURIComponent(args.wfId)}/chats`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `POST /system/workflows/${args.wfId}/chats failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }

      return (await res.json()) as Chat;
    },
    [authedFetch],
  );

  const getChatById = useCallback(
    async (chatId: string) => {
      const res = await authedFetch(`/system/chats/${encodeURIComponent(chatId)}`, {method: "GET"});
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `GET /system/chats/${chatId} failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return (await res.json()) as Chat;
    },
    [authedFetch],
  );

  const poseChat = useCallback(
    async (chatId: string, userInput: string) => {
      const sp = new URLSearchParams({user_input: userInput});
      const res = await authedFetch(`/system/chats/${encodeURIComponent(chatId)}/pose?${sp.toString()}`, {
        method: "POST",
      });
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `POST /system/chats/${chatId}/pose failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return (await res.json()) as Chat;
    },
    [authedFetch],
  );

  return {listWorkflows, createChatForWorkflow, getChatById, poseChat};
}