import {useEffect, useMemo, useState} from "react";
import {Alert, Button, CircularProgress, FormControl, InputLabel, MenuItem, Select, Stack, TextField, Typography,} from "@mui/material";

import {useAuth} from "../../auth/AuthContext";
import {type Chat, normalizeObjectId, type WorkflowConfig} from "../../api/system";
import {useChatApi} from "../../api/chat";

const DEBUG = false;

export default function ChatCreator(props: {
  onCreated?: (chat: Chat) => void | Promise<void>;
  onCancel?: () => void;
}) {
  const {onCreated, onCancel} = props;

  const auth = useAuth() as any;
  const {listWorkflows, createChatForWorkflow} = useChatApi();

  const username: string = auth.username ?? "No user";

  const [loadingWfs, setLoadingWfs] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [workflows, setWorkflows] = useState<WorkflowConfig[]>([]);
  const [selectedWfId, setSelectedWfId] = useState<string>("");
  const [chatName, setChatName] = useState<string>("");

  const selectedWfName = useMemo(() => {
    const wf = workflows.find((w) => normalizeObjectId((w as any)._id) === selectedWfId);
    return wf?.name ?? "";
  }, [workflows, selectedWfId]);

  async function loadWorkflows() {
    setLoadingWfs(true);
    setError(null);

    try {
      const wfs = await listWorkflows();
      if (DEBUG) console.log("[ChatCreator] workflows:", wfs);

      setWorkflows(wfs ?? []);

      const firstId = selectedWfId || normalizeObjectId((wfs?.[0] as any)?._id);
      if (!selectedWfId && firstId) setSelectedWfId(firstId);
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
      setWorkflows([]);
      setSelectedWfId("");
    } finally {
      setLoadingWfs(false);
    }
  }

  useEffect(() => {
    if (!auth.initialized || !auth.authenticated) return;
    loadWorkflows();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.initialized, auth.authenticated]);

  async function create() {
    if (!selectedWfId) {
      setError("Please select a workflow system first.");
      return;
    }

    setCreating(true);
    setError(null);

    try {
      const created = await createChatForWorkflow({
        wfId: selectedWfId,
        username,
        name: chatName.trim() ? chatName.trim() : null,
      });

      if (DEBUG) console.log("[ChatCreator] created chat:", created);

      await onCreated?.(created);
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
    } finally {
      setCreating(false);
    }
  }

  const disabled = !(auth.initialized && auth.authenticated) || loadingWfs || creating;

  return (
    <Stack spacing={2}>
      <Stack spacing={1}>
        <Typography sx={{fontWeight: 800}} variant="h6">
          Create a new chat
        </Typography>
        <Typography color="text.secondary">
          User: <b>{username}</b>
        </Typography>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {loadingWfs ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <CircularProgress size={18}/>
          <Typography color="text.secondary">Loading workflows…</Typography>
        </Stack>
      ) : workflows.length === 0 ? (
        <Alert severity="warning">No workflows available (or backend returned none).</Alert>
      ) : (
        <Stack direction={{xs: "column", sm: "row"}} spacing={2} alignItems="stretch">
          <FormControl fullWidth disabled={disabled}>
            <InputLabel id="wf-select-label">Workflow system</InputLabel>
            <Select
              labelId="wf-select-label"
              label="Workflow system"
              value={selectedWfId}
              onChange={(e) => setSelectedWfId(e.target.value)}
            >
              {workflows.map((wf) => {
                const id = normalizeObjectId((wf as any)._id);
                return (
                  <MenuItem key={id} value={id}>
                    {wf.name ?? id}
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
            disabled={disabled}
            placeholder={selectedWfName ? `e.g., ${selectedWfName} session` : "e.g., Study session"}
          />
        </Stack>
      )}

      <Stack direction="row" spacing={1}>
        <Button
          variant="contained"
          color="success"  // ✅ uses theme.palette.success.main
          onClick={create}
          disabled={disabled || !selectedWfId || workflows.length === 0}
          sx={{textTransform: "none"}}
        >
          {creating ? "Creating…" : "Create chat"}
        </Button>

        {onCancel && (
          <Button
            variant="outlined"
            onClick={onCancel}
            disabled={creating}
            sx={{textTransform: "none"}}
          >
            Cancel
          </Button>
        )}
      </Stack>
    </Stack>
  );
}
