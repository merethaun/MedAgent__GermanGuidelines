import React, {useEffect, useMemo, useState} from "react";
import {useNavigate} from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  SelectChangeEvent,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import {useAuth} from "../auth/AuthContext";

/** Adjust these types to match your backend models if needed */
type WorkflowConfig = {
  _id?: string;
  id?: string;
  name: string;
};

type ChatInput = {
  _id?: string | null;
  name?: string | null;
  workflow_system_id: string;
  username: string;
  interactions: any[]; // empty init
};

type ChatOutput = {
  _id?: string;
  id?: string;
  name?: string | null;
  workflow_system_id: string;
  username?: string;
  interactions?: any[];
};

function getId(x: { _id?: string; id?: string }) {
  return x._id ?? x.id ?? "";
}

export default function ChatCreator(props: {
  apiBaseUrl?: string; // optional override
  initialWorkflowId?: string;
  onWorkflowSelected?: (wfId: string) => void;
  onChatCreated?: (chat: ChatOutput) => void;
  navigateToChat?: boolean; // default true
}) {
  const {
    apiBaseUrl,
    initialWorkflowId,
    onWorkflowSelected,
    onChatCreated,
    navigateToChat = true,
  } = props;

  const auth = useAuth();
  const navigate = useNavigate();

  const API_BASE = useMemo(() => {
    // Choose whichever env var you already use in the project
    return (
      apiBaseUrl ??
      (import.meta as any).env?.VITE_API_BASE_URL ??
      (import.meta as any).env?.VITE_BACKEND_URL ??
      ""
    );
  }, [apiBaseUrl]);

  const [workflows, setWorkflows] = useState<WorkflowConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // current selected workflow system (stored in state as requested)
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>(initialWorkflowId ?? "");
  const [chatName, setChatName] = useState<string>("");

  // You may need to adapt this depending on how your AuthContext exposes the token.
  const token: string | undefined =
    (auth as any).token ?? (auth as any).accessToken ?? (auth as any).keycloak?.token;

  const username: string = auth?.username ?? "No user";

  async function fetchWorkflows() {
    if (!token) {
      setError("Not authenticated (missing token).");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/system/workflows`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Failed to load workflows (${res.status}): ${text}`);
      }

      const data = (await res.json()) as WorkflowConfig[];
      setWorkflows(data);

      // Initialize selection if empty
      if (!selectedWorkflowId && data.length > 0) {
        const firstId = getId(data[0]);
        setSelectedWorkflowId(firstId);
        onWorkflowSelected?.(firstId);
      }
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  async function createChat() {
    if (!token) {
      setError("Not authenticated (missing token).");
      return;
    }
    if (!selectedWorkflowId) {
      setError("Please select a workflow first.");
      return;
    }

    setCreating(true);
    setError(null);

    const payload: ChatInput = {
      workflow_system_id: selectedWorkflowId,
      username,
      interactions: [], // init with empty interaction list
      name: chatName.trim() ? chatName.trim() : null,
    };

    try {
      const res = await fetch(`${API_BASE}/system/workflows/${selectedWorkflowId}/chats`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Failed to create chat (${res.status}): ${text}`);
      }

      const created = (await res.json()) as ChatOutput;
      onChatCreated?.(created);

      const createdId = getId(created);
      if (navigateToChat && createdId) {
        navigate(`/chat/${createdId}`);
      }
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setCreating(false);
    }
  }

  useEffect(() => {
    if (auth?.initialized && auth?.authenticated) {
      fetchWorkflows();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth?.initialized, auth?.authenticated, token]);

  const selectedWorkflowName =
    workflows.find((w) => getId(w) === selectedWorkflowId)?.name ?? "";

  const handleSelect = (e: SelectChangeEvent<string>) => {
    const wfId = e.target.value;
    setSelectedWorkflowId(wfId);
    onWorkflowSelected?.(wfId);
  };

  const disabled = !auth?.initialized || !auth?.authenticated || !token;

  return (
    <Card variant="outlined" sx={{borderRadius: 2}}>
      <CardContent>
        <Stack spacing={2}>
          <Stack spacing={0.5}>
            <Typography variant="h6" fontWeight={700}>
              Create chat
            </Typography>
            <Typography variant="body2" color="text.secondary">
              User: <b>{username}</b>
            </Typography>
          </Stack>

          {error ? <Alert severity="error">{error}</Alert> : null}

          <Stack direction={{xs: "column", sm: "row"}} spacing={2} alignItems="stretch">
            <FormControl fullWidth disabled={disabled || loading}>
              <InputLabel id="wf-select-label">Workflow</InputLabel>
              <Select
                labelId="wf-select-label"
                label="Workflow"
                value={selectedWorkflowId}
                onChange={handleSelect}
              >
                {workflows.map((wf) => {
                  const id = getId(wf);
                  return (
                    <MenuItem key={id} value={id}>
                      {wf.name}
                    </MenuItem>
                  );
                })}
              </Select>
            </FormControl>

            <TextField
              fullWidth
              label="Chat name (optional)"
              value={chatName}
              onChange={(e) => setChatName(e.target.value)}
              disabled={disabled || creating}
              placeholder={selectedWorkflowName ? `e.g., ${selectedWorkflowName} session` : "e.g., Study session"}
            />
          </Stack>

          <Stack direction="row" spacing={1} alignItems="center">
            <Button
              variant="contained"
              onClick={createChat}
              disabled={disabled || loading || creating || !selectedWorkflowId}
              sx={{textTransform: "none"}}
            >
              {creating ? "Creating…" : "Create chat"}
            </Button>

            {loading ? <CircularProgress size={22}/> : null}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}
