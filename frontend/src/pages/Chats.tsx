import {useEffect, useMemo, useRef, useState} from "react";
import {useNavigate} from "react-router-dom";
import {useAuth} from "../auth/AuthContext";

import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import {type Chat, normalizeObjectId, useSystemApi} from "../api/system";

const DEBUG = true; // set to false when done

function fmtTime(iso?: string | null): string | undefined {
  if (!iso) return undefined;
  // Best-effort: show ISO or a short local time.
  // If you want Berlin local formatting with date+time, we can adjust.
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function lastInteractionSummary(chat: Chat): { label: string; time?: string } {
  const last = chat.interactions?.[chat.interactions.length - 1];
  if (!last) return {label: "—"};

  const time = fmtTime(last.time_response_output ?? last.time_question_input);

  // Prefer showing the question; optionally include whether response exists
  const q = (last.user_input ?? "").trim();
  const hasAnswer = !!(last.generator_output && last.generator_output.trim().length > 0);
  const prefix = hasAnswer ? "" : "[no answer] ";

  const label = (prefix + q).trim();
  return {label: label ? label.slice(0, 110) : "—", time};
}

export default function ChatsPage() {
  const auth = useAuth() as any;
  const navigate = useNavigate();
  const {listChats, getWorkflowById} = useSystemApi();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [chats, setChats] = useState<Chat[]>([]);
  const [workflowNameById, setWorkflowNameById] = useState<Record<string, string>>({});

  const didAutoLoadRef = useRef(false);

  const username: string | undefined = auth.username;

  async function loadOnce() {
    setLoading(true);
    setError(null);

    try {
      // 1) Fetch chats filtered by username
      const result = await listChats({user_name: username});
      if (DEBUG) console.log("[Chats] listChats:", result);

      setChats(result ?? []);

      // 2) Fetch workflow names for unique workflow ids
      const wfIds = Array.from(
        new Set((result ?? []).map((c) => normalizeObjectId((c as any).workflow_system_id)).filter(Boolean)),
      );

      if (DEBUG) console.log("[Chats] unique workflow ids:", wfIds);

      // Only fetch missing
      const missing = wfIds.filter((id) => !workflowNameById[id]);

      if (missing.length > 0) {
        const pairs = await Promise.all(
          missing.map(async (wfId) => {
            try {
              const wf = await getWorkflowById(wfId);
              if (DEBUG) console.log(`[Workflow] ${wfId}:`, wf);
              return [wfId, wf.name ?? wfId] as const;
            } catch (e) {
              console.warn("[Workflow] failed:", wfId, e);
              return [wfId, wfId] as const;
            }
          }),
        );

        setWorkflowNameById((prev) => {
          const next = {...prev};
          for (const [id, name] of pairs) next[id] = name;
          return next;
        });
      }
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
      setChats([]);
      setWorkflowNameById({});
    } finally {
      setLoading(false);
    }
  }

  // Auto-load exactly once when auth is ready
  useEffect(() => {
    if (!auth.initialized || !auth.authenticated) return;
    if (didAutoLoadRef.current) return;

    didAutoLoadRef.current = true;
    loadOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.initialized, auth.authenticated]);

  const rows = useMemo(() => {
    return chats.map((c) => {
      const chatId = normalizeObjectId((c as any)._id);
      const chatName = c.name && c.name.trim().length > 0 ? c.name : chatId;

      const wfId = normalizeObjectId((c as any).workflow_system_id);
      const wfName = workflowNameById[wfId] ?? wfId;

      const last = lastInteractionSummary(c);

      return {
        chatId,
        chatName,
        wfName,
        lastLabel: last.label,
        lastTime: last.time,
      };
    });
  }, [chats, workflowNameById]);

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4" sx={{fontWeight: 800}}>
            Chats
          </Typography>
          <Typography color="text.secondary">
            Showing chats for <b>{username ?? "—"}</b>
          </Typography>
        </Box>

        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            onClick={() => loadOnce()}
            disabled={loading || !(auth.initialized && auth.authenticated)}
            sx={{textTransform: "none"}}
          >
            Reload
          </Button>
          <Button variant="contained" disabled sx={{textTransform: "none"}}>
            New chat
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Card variant="outlined">
        <CardContent sx={{p: 0}}>
          {loading ? (
            <Box sx={{display: "flex", justifyContent: "center", py: 6}}>
              <CircularProgress/>
            </Box>
          ) : rows.length === 0 ? (
            <Box sx={{p: 3}}>
              <Typography sx={{fontWeight: 700}}>No chats found</Typography>
              <Typography color="text.secondary">
                Either there are no chats for this user, or the backend returned none.
              </Typography>
            </Box>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{fontWeight: 800}}>Chat</TableCell>
                    <TableCell sx={{fontWeight: 800}}>Workflow system</TableCell>
                    <TableCell sx={{fontWeight: 800}}>Last interaction</TableCell>
                    <TableCell sx={{fontWeight: 800}} align="right">
                      Action
                    </TableCell>
                  </TableRow>
                </TableHead>

                <TableBody>
                  {rows.map((r) => (
                    <TableRow
                      key={r.chatId}
                      hover
                      onClick={() => navigate(`/chat/${r.chatId}`)}
                      sx={{cursor: "pointer"}}
                    >
                      <TableCell>{r.chatName}</TableCell>

                      <TableCell>{r.wfName}</TableCell>

                      <TableCell>
                        <Typography
                          variant="body2"
                          sx={{
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            maxWidth: 560,
                          }}
                        >
                          {r.lastLabel}
                        </Typography>
                        {r.lastTime && (
                          <Typography variant="caption" color="text.secondary">
                            {r.lastTime}
                          </Typography>
                        )}
                      </TableCell>

                      <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          variant="outlined"
                          size="small"
                          sx={{textTransform: "none"}}
                          onClick={() => navigate(`/chat/${r.chatId}`)}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
