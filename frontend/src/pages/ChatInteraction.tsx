import {useEffect, useMemo, useRef, useState} from "react";
import {useNavigate, useParams} from "react-router-dom";

import CloseIcon from "@mui/icons-material/Close";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Container,
  MenuItem,
  Snackbar,
  Stack,
  TextField,
  Typography,
  useTheme,
} from "@mui/material";
import IconButton from "@mui/material/IconButton";

import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";

import {useAuth} from "../auth/AuthContext";
import {type Chat, normalizeObjectId, useSystemApi} from "../api/system";
import {useChatApi} from "../api/chat";
import {useEvaluationApi} from "../api/evaluation";

import ChatCreator from "../components/chat/ChatCreator";
import ChatHeader from "../components/chat/ChatHeader";
import ChatDisplay from "../components/chat/ChatDisplay";
import ReferenceDisplay from "../components/references/ReferenceDisplay";

// -------------------- Layout helpers --------------------

/**
 * Simplified sizing model:
 * - One fixed panel max-height (defaults to "fills the rest of the page")
 * - One fixed wrapper width (can exceed viewport)
 * - One fixed reference width (split handle)
 */
const DEFAULT_FIXED_MAX_HEIGHT = "75vh";
const DEFAULT_WRAPPER_WIDTH = "lg";
const DEFAULT_REFERENCE_WIDTH = "30%";

const MIN_FIXED_HEIGHT = "25vh";
const MAX_FIXED_HEIGHT = "100vh";

const MIN_REFERENCE_WIDTH = "20%";
const MAX_REFERENCE_WIDTH = "75%";

const MIN_WRAPPER_WIDTH = "lg";
const MAX_WRAPPER_WIDTH = "90vw";

const HANDLE_HIT_PX = 12;
const HANDLE_GRAB_THICKNESS_PX = 4;
const HANDLE_GRAB_LENGTH_PX = 54;

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function parsePercentToRatio(spec: string): number {
  const s = (spec ?? "").trim();
  if (!s) return 0;

  if (s.endsWith("%")) {
    const v = parseFloat(s.slice(0, -1));
    return Number.isFinite(v) ? v / 100 : 0;
  }

  // Allow raw ratio strings, e.g. "0.3"
  const v = parseFloat(s);
  if (!Number.isFinite(v)) return 0;

  // If someone passes "30" assume percent.
  return v > 1 ? v / 100 : v;
}

type BreakpointKey = "xs" | "sm" | "md" | "lg" | "xl";

function isBreakpointKey(s: string): s is BreakpointKey {
  return s === "xs" || s === "sm" || s === "md" || s === "lg" || s === "xl";
}

function resolveCssPx(
  spec: string | number,
  _axis: "x" | "y",
  viewport: { w: number; h: number },
  themeBreakpointValues: Record<BreakpointKey, number>,
  basePx?: number,
): number {
  if (typeof spec === "number") return spec;

  const s = (spec ?? "").trim();
  if (!s) return 0;

  if (isBreakpointKey(s)) return themeBreakpointValues[s];

  const num = parseFloat(s);
  if (!Number.isFinite(num)) return 0;

  if (s.endsWith("px")) return num;
  if (s.endsWith("vw")) return (viewport.w * num) / 100;
  if (s.endsWith("vh")) return (viewport.h * num) / 100;
  if (s.endsWith("%")) {
    if (basePx == null) return 0;
    return (basePx * num) / 100;
  }

  // Fallback: treat as px-ish number string.
  return num;
}

function GrabBar({orientation}: { orientation: "vertical" | "horizontal" }) {
  const isV = orientation === "vertical";
  return (
    <Box
      className="grab"
      sx={{
        width: isV ? HANDLE_GRAB_THICKNESS_PX : HANDLE_GRAB_LENGTH_PX,
        height: isV ? HANDLE_GRAB_LENGTH_PX : HANDLE_GRAB_THICKNESS_PX,
        borderRadius: 999,
        bgcolor: "text.disabled",
        opacity: 0.35,
      }}
    />
  );
}

// -------------------- Page component --------------------

export default function ChatInteractionPage() {
  const auth = useAuth() as any;
  const theme = useTheme();
  const navigate = useNavigate();
  const {chatId: rawChatId} = useParams();
  const adminRole = import.meta.env.VITE_KEYCLOAK_ADMIN_ROLE ?? "admin";

  const chatId = rawChatId ?? "";
  const {getWorkflowById} = useSystemApi();
  const {getChatById, poseChat} = useChatApi();
  const {createAnswerFeedback, createRun, listEvaluators} = useEvaluationApi();

  const [showCreator, setShowCreator] = useState(false);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [showEvaluationDialog, setShowEvaluationDialog] = useState(false);

  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [submittingEvaluation, setSubmittingEvaluation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorToastOpen, setErrorToastOpen] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [successToastOpen, setSuccessToastOpen] = useState(false);

  const [chat, setChat] = useState<Chat | null>(null);
  const [workflowName, setWorkflowName] = useState<string | undefined>(undefined);
  const [selectedInteractionIndex, setSelectedInteractionIndex] = useState<number>(-1);
  const [evaluators, setEvaluators] = useState<any[]>([]);
  const [feedbackHelpful, setFeedbackHelpful] = useState<string>("");
  const [feedbackRating, setFeedbackRating] = useState<string>("");
  const [feedbackComment, setFeedbackComment] = useState<string>("");
  const [evaluationRunName, setEvaluationRunName] = useState("");
  const [evaluationManualMode, setEvaluationManualMode] = useState<"none" | "open" | "assigned" | "mixed">("open");
  const [evaluationAssignee, setEvaluationAssignee] = useState("");
  const [evaluationAssignments, setEvaluationAssignments] = useState("");

  const username: string | undefined = auth.username;
  const isAdmin = auth.initialized && auth.authenticated && auth.hasRole(adminRole);

  // --- Viewport (for vh/vw constraints) ---
  const [viewport, setViewport] = useState(() => ({
    w: typeof window !== "undefined" ? window.innerWidth : 0,
    h: typeof window !== "undefined" ? window.innerHeight : 0,
  }));

  useEffect(() => {
    const onResize = () => setViewport({w: window.innerWidth, h: window.innerHeight});
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    void (async () => {
      try {
        setEvaluators(await listEvaluators());
      } catch {
        // keep UI usable even if evaluator discovery is not set up yet
      }
    })();
  }, [isAdmin, listEvaluators]);

  const bp = theme.breakpoints.values as Record<BreakpointKey, number>;

  // --- Layout state ---

  // Refs used by resize logic
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Height: fixed *max* height
  const [autoFitHeight, setAutoFitHeight] = useState(true);
  const minFixedHeightPx = Math.max(0, resolveCssPx(MIN_FIXED_HEIGHT, "y", viewport, bp));
  const [fixedMaxHeightPx, setFixedMaxHeightPx] = useState<number>(() =>
    Math.max(minFixedHeightPx, resolveCssPx(DEFAULT_FIXED_MAX_HEIGHT, "y", viewport, bp)),
  );

  // Width: wrapper width in px (defaults to a breakpoint width like "lg")
  const [wrapperWidthPx, setWrapperWidthPx] = useState<number>(() =>
    Math.max(0, resolveCssPx(DEFAULT_WRAPPER_WIDTH, "x", viewport, bp)),
  );

  // Split: reference width as a ratio of the wrapper content width
  const [referenceWidthRatio, setReferenceWidthRatio] = useState<number>(() =>
    parsePercentToRatio(DEFAULT_REFERENCE_WIDTH),
  );

  // Scroll padding (used when wrapperWidthPx > available width)
  const [scrollPadPx, setScrollPadPx] = useState(0);

  // --- Derived constraints (resolved from responsive specs) ---
  const maxFixedHeightPx = Math.max(minFixedHeightPx, resolveCssPx(MAX_FIXED_HEIGHT, "y", viewport, bp));
  const maxWrapperWidthPx = Math.max(0, resolveCssPx(MAX_WRAPPER_WIDTH, "x", viewport, bp));
  const minWrapperFromSpecPx = Math.max(0, resolveCssPx(MIN_WRAPPER_WIDTH, "x", viewport, bp));

  const minRefRatio = clamp(parsePercentToRatio(MIN_REFERENCE_WIDTH), 0, 0.99);
  const maxRefRatio = clamp(parsePercentToRatio(MAX_REFERENCE_WIDTH), 0.01, 1);

  const MIN_CHAT_COL_PX = 360;
  const HANDLE_COL_PX = HANDLE_HIT_PX;
  const HANDLE_TOTAL_PX = HANDLE_COL_PX * 3;

  const referenceRatioClamped = clamp(referenceWidthRatio, minRefRatio, maxRefRatio);

  // Wrapper must be wide enough so the *chat* can still reach MIN_CHAT_COL_PX.
  // We treat the reference ratio as a ratio of the content width (wrapper minus handles).
  const minWrapperForChatPx = Math.ceil(
    HANDLE_TOTAL_PX + MIN_CHAT_COL_PX / Math.max(0.05, 1 - referenceRatioClamped),
  );

  const minWrapperWidthPx = Math.max(minWrapperFromSpecPx, minWrapperForChatPx);

  // Keep wrapper within bounds whenever constraints change (e.g., viewport resize).
  useEffect(() => {
    setWrapperWidthPx((w) => clamp(w, minWrapperWidthPx, maxWrapperWidthPx));
  }, [minWrapperWidthPx, maxWrapperWidthPx]);

  // Auto-fit: choose a sensible max height that fills the rest of the viewport.
  useEffect(() => {
    if (!autoFitHeight) return;

    const compute = () => {
      const el = panelRef.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top;
      const available = Math.floor(viewport.h - top - 16);
      setFixedMaxHeightPx(clamp(available, minFixedHeightPx, maxFixedHeightPx));
    };

    const raf = window.requestAnimationFrame(compute);
    window.addEventListener("resize", compute);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", compute);
    };
  }, [autoFitHeight, maxFixedHeightPx, viewport.h]);

  const panelHeightPx = clamp(fixedMaxHeightPx, minFixedHeightPx, maxFixedHeightPx);
  const wrapperWidthClampedPx = clamp(wrapperWidthPx, minWrapperWidthPx, maxWrapperWidthPx);

  const contentWidthPx = Math.max(0, wrapperWidthClampedPx - HANDLE_TOTAL_PX);
  const referenceWidthClampedPx = clamp(referenceRatioClamped, minRefRatio, maxRefRatio) * contentWidthPx;

  // When the wrapper exceeds the available width, pad the scroll container symmetrically
  // and scroll so the block stays centered.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const compute = () => {
      const availableW = el.clientWidth || viewport.w || window.innerWidth;
      const pad = wrapperWidthClampedPx > availableW ? Math.round((wrapperWidthClampedPx - availableW) / 2) : 0;
      setScrollPadPx(pad);

      // Keep the wrapper centered within the scroll area.
      el.scrollLeft = pad > 0 ? pad * 2 : 0;
    };

    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, [wrapperWidthClampedPx, viewport.w]);

  const dragWrapperState = useRef<{
    startX: number;
    startW: number;
    side: "left" | "right";
    minW: number;
    maxW: number;
  } | null>(null);

  function onWrapperResizeMouseDown(e: React.MouseEvent, side: "left" | "right") {
    if (e.button !== 0) return;
    e.preventDefault();

    const el = wrapperRef.current;
    if (!el) return;

    const currentW = el.getBoundingClientRect().width;
    const startW = clamp(currentW, minWrapperWidthPx, maxWrapperWidthPx);

    dragWrapperState.current = {
      startX: e.clientX,
      startW,
      side,
      minW: minWrapperWidthPx,
      maxW: maxWrapperWidthPx,
    };

    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;

    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    const onMove = (ev: MouseEvent) => {
      const st = dragWrapperState.current;
      if (!st) return;

      const dx = ev.clientX - st.startX;
      const signed = st.side === "right" ? dx : -dx;

      // symmetric resize: moving one edge by dx changes total width by 2*dx
      const nextW = clamp(st.startW + signed * 2, st.minW, st.maxW);
      setWrapperWidthPx(nextW);
    };

    const onUp = () => {
      dragWrapperState.current = null;
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  // For “nice feedback”: measure the actual panel container
  const [panelSize, setPanelSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const el = panelRef.current;
    if (!el) return;

    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const cr = entry.contentRect;
      setPanelSize({w: cr.width, h: cr.height});
    });

    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Drag handle between Chat and Refs (reference width)
  const dragRefState = useRef<{ startX: number; startRefPx: number; contentW: number } | null>(null);

  function onRefResizeMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();

    const el = wrapperRef.current;
    const wrapperW = el?.getBoundingClientRect().width ?? wrapperWidthClampedPx;
    const contentW = Math.max(1, wrapperW - HANDLE_TOTAL_PX);

    // Use the current rendered ref width at drag start.
    const startRefPx = clamp(referenceRatioClamped, minRefRatio, maxRefRatio) * contentW;

    dragRefState.current = {startX: e.clientX, startRefPx, contentW};

    const onMove = (ev: MouseEvent) => {
      const st = dragRefState.current;
      if (!st) return;

      const dx = ev.clientX - st.startX;
      const nextRefPx = st.startRefPx - dx; // dragging left increases refs

      const minRefPx = minRefRatio * st.contentW;
      const maxRefPx = maxRefRatio * st.contentW;

      const clampedPx = clamp(nextRefPx, minRefPx, maxRefPx);
      setReferenceWidthRatio(clampedPx / st.contentW);
    };

    const onUp = () => {
      dragRefState.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  // Bottom drag handle (panel max-height)
  const dragHeightState = useRef<{ startY: number; startH: number } | null>(null);

  function onHeightResizeMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();
    setAutoFitHeight(false);

    dragHeightState.current = {startY: e.clientY, startH: panelHeightPx};

    const onMove = (ev: MouseEvent) => {
      const st = dragHeightState.current;
      if (!st) return;
      const dy = ev.clientY - st.startY;
      setFixedMaxHeightPx(clamp(st.startH + dy, minFixedHeightPx, maxFixedHeightPx));
    };

    const onUp = () => {
      dragHeightState.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  // Load chat + workflow name
  useEffect(() => {
    if (!auth.initialized || !auth.authenticated) return;
    if (!chatId) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const c = await getChatById(chatId);
        if (cancelled) return;

        setChat(c);

        // default select last interaction
        const idx = (c.interactions?.length ?? 0) - 1;
        setSelectedInteractionIndex(idx >= 0 ? idx : -1);

        const wfId = normalizeObjectId((c as any).workflow_system_id);
        if (wfId) {
          try {
            const wf = await getWorkflowById(wfId);
            if (!cancelled) setWorkflowName(wf?.name ?? wfId);
          } catch {
            if (!cancelled) setWorkflowName(wfId);
          }
        } else {
          setWorkflowName(undefined);
        }
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ?? String(e));
        setErrorToastOpen(true);
        setChat(null);
        setWorkflowName(undefined);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.initialized, auth.authenticated, chatId]);

  const chatName = useMemo(() => {
    if (!chatId) return "Chat";
    if (!chat) return chatId;
    const name = chat.name?.trim();
    return name && name.length > 0 ? name : chatId;
  }, [chatId, chat]);

  const selectedRetrievalResults = useMemo(() => {
    if (!chat) return [];
    if (selectedInteractionIndex < 0) return [];
    const it = chat.interactions?.[selectedInteractionIndex];
    return it?.retrieval_output ?? [];
  }, [chat, selectedInteractionIndex]);

  const selectedInteraction = useMemo(() => {
    if (!chat) return null;
    if (selectedInteractionIndex < 0) return null;
    return chat.interactions?.[selectedInteractionIndex] ?? null;
  }, [chat, selectedInteractionIndex]);

  async function send(userInput: string) {
    if (!chatId) return;

    setSending(true);
    setError(null);

    try {
      const updatedChat = await poseChat(chatId, userInput);
      setChat(updatedChat);

      // keep selection on newest (common chat behavior)
      const idx = (updatedChat.interactions?.length ?? 0) - 1;
      setSelectedInteractionIndex(idx >= 0 ? idx : -1);
    } catch (e: any) {
      setError(e?.message ?? String(e));
      setErrorToastOpen(true);
    } finally {
      setSending(false);
    }
  }

  async function submitFeedback() {
    if (!selectedInteraction || selectedInteractionIndex < 0) return;
    setSubmittingFeedback(true);
    setError(null);
    try {
      await createAnswerFeedback({
        chat_id: chatId,
        interaction_index: selectedInteractionIndex,
        helpful: feedbackHelpful === "" ? null : feedbackHelpful === "yes",
        rating: feedbackRating === "" ? null : Number(feedbackRating),
        comment: feedbackComment.trim() || null,
      });
      setShowFeedbackDialog(false);
      setFeedbackHelpful("");
      setFeedbackRating("");
      setFeedbackComment("");
      setSuccessMessage("Feedback submitted.");
      setSuccessToastOpen(true);
    } catch (e: any) {
      setError(e?.message ?? String(e));
      setErrorToastOpen(true);
    } finally {
      setSubmittingFeedback(false);
    }
  }

  async function sendToEvaluation() {
    if (!chat || selectedInteractionIndex < 0) return;
    setSubmittingEvaluation(true);
    setError(null);
    try {
      const manualReviewAssignments = evaluationAssignments.trim()
        ? JSON.parse(evaluationAssignments)
        : [];
      await createRun({
        name: evaluationRunName.trim() || `chat-${chatId}-interaction-${selectedInteractionIndex + 1}`,
        workflow_system_id: normalizeObjectId((chat as any).workflow_system_id),
        source_type: "chat_snapshot",
        source_chat_id: chatId,
        source_interaction_index: selectedInteractionIndex,
        manual_review_mode: evaluationManualMode,
        assigned_evaluator_sub: evaluationAssignee || null,
        assigned_evaluator_username: evaluators.find((entry) => entry.sub === evaluationAssignee)?.username ?? null,
        manual_review_assignments: manualReviewAssignments,
      });
      setShowEvaluationDialog(false);
      setEvaluationRunName("");
      setEvaluationAssignments("");
      setSuccessMessage("Interaction sent to evaluation.");
      setSuccessToastOpen(true);
    } catch (e: any) {
      setError(e?.message ?? String(e));
      setErrorToastOpen(true);
    } finally {
      setSubmittingEvaluation(false);
    }
  }

  if (!chatId) {
    return <Alert severity="warning">No chat id in route.</Alert>;
  }

  return (
    <Stack
      spacing={2.5}
      sx={{
        height: "100dvh",
        minHeight: "100dvh",
        overflow: "hidden",
        width: "98vw",
        maxWidth: "98vw",
        marginLeft: "calc(-49vw + 50%)",
        marginRight: "calc(-49vw + 50%)",
        alignItems: "center",
      }}
    >
      <Container
        maxWidth="lg"
      >
        <ChatHeader
          chatName={chatName}
          chatId={chatId}
          username={username}
          workflowName={workflowName}
          workflowId={chat ? normalizeObjectId((chat as any).workflow_system_id) : undefined}
          onNewChat={() => setShowCreator(true)}
          rightSlot={
            <Stack direction="row" spacing={1}>
              <Button
                variant="outlined"
                onClick={() => setShowFeedbackDialog(true)}
                disabled={selectedInteractionIndex < 0}
                sx={{textTransform: "none"}}
              >
                Feedback
              </Button>
              {isAdmin ? (
                <Button
                  variant="contained"
                  onClick={() => {
                    setEvaluationRunName(`chat-${chatId}-interaction-${selectedInteractionIndex + 1}`);
                    setShowEvaluationDialog(true);
                  }}
                  disabled={selectedInteractionIndex < 0}
                  sx={{textTransform: "none"}}
                >
                  Send to evaluation
                </Button>
              ) : null}
            </Stack>
          }
        />
      </Container>

      {/* New chat popup */}
      <Dialog open={showCreator} onClose={() => setShowCreator(false)} fullWidth maxWidth="md">
        <DialogTitle sx={{fontWeight: 800}}>
          <Typography variant="h5" sx={{fontWeight: 800}}>New chat</Typography>
          <IconButton
            aria-label="close"
            onClick={() => setShowCreator(false)}
            sx={{position: "absolute", right: 8, top: 8}}
            size="small"
          >
            <CloseIcon/>
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <ChatCreator
            onCancel={() => setShowCreator(false)}
            onCreated={async (created) => {
              setShowCreator(false);
              const id = normalizeObjectId((created as any)._id);
              if (id) navigate(`/chat/${id}`);
            }}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={showFeedbackDialog} onClose={() => setShowFeedbackDialog(false)} fullWidth maxWidth="sm">
        <DialogTitle>Submit feedback</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography color="text.secondary">
              Share quick feedback about the currently selected interaction.
            </Typography>
            <TextField
              select
              label="Helpful"
              value={feedbackHelpful}
              onChange={(e) => setFeedbackHelpful(e.target.value)}
              fullWidth
            >
              <MenuItem value="">No answer</MenuItem>
              <MenuItem value="yes">Yes</MenuItem>
              <MenuItem value="no">No</MenuItem>
            </TextField>
            <TextField
              select
              label="Rating"
              value={feedbackRating}
              onChange={(e) => setFeedbackRating(e.target.value)}
              fullWidth
            >
              <MenuItem value="">No rating</MenuItem>
              {[1, 2, 3, 4, 5].map((value) => (
                <MenuItem key={value} value={String(value)}>
                  {value}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Comment"
              value={feedbackComment}
              onChange={(e) => setFeedbackComment(e.target.value)}
              multiline
              minRows={3}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowFeedbackDialog(false)} sx={{textTransform: "none"}}>
            Cancel
          </Button>
          <Button variant="contained" onClick={() => void submitFeedback()} disabled={submittingFeedback} sx={{textTransform: "none"}}>
            Submit
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={showEvaluationDialog} onClose={() => setShowEvaluationDialog(false)} fullWidth maxWidth="sm">
        <DialogTitle>Send interaction to evaluation</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <TextField
              label="Run name"
              value={evaluationRunName}
              onChange={(e) => setEvaluationRunName(e.target.value)}
              fullWidth
            />
            <TextField
              select
              label="Manual review mode"
              value={evaluationManualMode}
              onChange={(e) => setEvaluationManualMode(e.target.value as any)}
              fullWidth
            >
              <MenuItem value="none">none</MenuItem>
              <MenuItem value="open">open</MenuItem>
              <MenuItem value="assigned">assigned</MenuItem>
              <MenuItem value="mixed">mixed</MenuItem>
            </TextField>
            <TextField
              select
              label="Assigned evaluator"
              value={evaluationAssignee}
              onChange={(e) => setEvaluationAssignee(e.target.value)}
              disabled={evaluationManualMode === "open" || evaluationManualMode === "none"}
              fullWidth
            >
              <MenuItem value="">None</MenuItem>
              {evaluators.map((entry) => (
                <MenuItem key={entry.sub} value={entry.sub}>
                  {entry.username || entry.sub}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Mixed assignment JSON"
              value={evaluationAssignments}
              onChange={(e) => setEvaluationAssignments(e.target.value)}
              disabled={evaluationManualMode !== "mixed"}
              multiline
              minRows={3}
              helperText='Optional. Example: [{"question_id":"...","evaluator_sub":"...","evaluator_username":"alice"}]'
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowEvaluationDialog(false)} sx={{textTransform: "none"}}>
            Cancel
          </Button>
          <Button variant="contained" onClick={() => void sendToEvaluation()} disabled={submittingEvaluation} sx={{textTransform: "none"}}>
            Create evaluation item
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={errorToastOpen && Boolean(error)}
        autoHideDuration={8000}
        onClose={(_, reason) => {
          if (reason === "clickaway") return;
          setErrorToastOpen(false);
        }}
        anchorOrigin={{vertical: "bottom", horizontal: "right"}}
      >
        <Alert
          severity="error"
          variant="filled"
          onClose={() => setErrorToastOpen(false)}
          sx={{maxWidth: 720}}
        >
          {error}
        </Alert>
      </Snackbar>

      <Snackbar
        open={successToastOpen && Boolean(successMessage)}
        autoHideDuration={4000}
        onClose={(_, reason) => {
          if (reason === "clickaway") return;
          setSuccessToastOpen(false);
        }}
        anchorOrigin={{vertical: "bottom", horizontal: "right"}}
      >
        <Alert
          severity="success"
          variant="filled"
          onClose={() => setSuccessToastOpen(false)}
          sx={{maxWidth: 520}}
        >
          {successMessage}
        </Alert>
      </Snackbar>

      {/* Centered wrapper: adjustable overall width (can exceed viewport) */}
      <Box
        ref={scrollRef}
        sx={{
          width: "100%",
          height: "100%",
          overflowX: {xs: "visible", md: "auto"},
          overflowY: "visible",
          minHeight: 0,
          pl: {xs: 0, md: `${scrollPadPx}px`},
          pr: {xs: 0, md: `${scrollPadPx}px`},
        }}
      >
        <Box
          ref={wrapperRef}
          sx={{
            width: {xs: "100%", md: `${wrapperWidthClampedPx}px`},
            mx: "auto",
            position: "relative",
            height: "100%",
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Panel container: fixed max-height (auto-fits to the rest of the viewport by default) */}
          <Box
            ref={panelRef}
            sx={{
              position: "relative",
              flex: {xs: "0 0 auto", md: autoFitHeight ? "1 1 auto" : "0 0 auto"},
              height: {xs: "auto", md: autoFitHeight ? "auto" : `${panelHeightPx}px`},
              maxHeight: {xs: "none", md: autoFitHeight ? "none" : `${maxFixedHeightPx}px`},
              minHeight: {xs: 0, md: `${minFixedHeightPx}px`},
              overflow: "hidden",

              display: "grid",
              gap: 0,

              gridTemplateAreas: {
                xs: `"chat" "refs"`,
                // left handle | chat | middle handle | refs | right handle
                md: `"handleL chat handleM refs handleR"`,
              },

              gridTemplateColumns: {
                xs: "1fr",
                md: `${HANDLE_COL_PX}px minmax(${MIN_CHAT_COL_PX}px, 1fr) ${HANDLE_COL_PX}px ${referenceWidthClampedPx}px ${HANDLE_COL_PX}px`,
              },

              gridTemplateRows: {
                xs: "auto auto",
                md: "1fr",
              },

              columnGap: {xs: 2, md: 0.75},
              rowGap: {xs: 2, md: 0},
              alignItems: "stretch",
            }}
          >
            {/* Left handle (desktop only) */}
            <Box
              sx={{
                gridArea: "handleL",
                display: {xs: "none", md: "flex"},
                width: `${HANDLE_COL_PX}px`,
                cursor: "col-resize",
                borderRadius: 2,
                alignItems: "center",
                justifyContent: "center",
                touchAction: "none",
                px: 0.5, // padding so it doesn't hug the edge
                "&:hover": {bgcolor: "action.hover"},
                "&:hover .grab": {opacity: 0.9},
              }}
              onMouseDown={(e) => onWrapperResizeMouseDown(e, "left")}
              title="Drag to resize chat display width"
            >
              <GrabBar orientation="vertical"/>
            </Box>

            {/* Chat */}
            <Box sx={{gridArea: "chat", minWidth: 0, minHeight: 0, overflow: "hidden"}}>
              {loading ? (
                <Box sx={{display: "flex", justifyContent: "center", py: 6}}>
                  <CircularProgress/>
                </Box>
              ) : !chat ? (
                <Alert severity="warning">Chat could not be loaded.</Alert>
              ) : (
                <ChatDisplay
                  chat={chat}
                  selectedInteractionIndex={selectedInteractionIndex}
                  onSelectInteractionIndex={setSelectedInteractionIndex}
                  onSend={send}
                  sending={sending}
                  height="100%"
                  minHeightPx={`${minFixedHeightPx}px`}
                />
              )}
            </Box>

            {/* Middle handle (refs resize, desktop only) */}
            <Box
              sx={{
                gridArea: "handleM",
                display: {xs: "none", md: "flex"},
                width: `${HANDLE_COL_PX}px`,
                cursor: "col-resize",
                borderRadius: 2,
                alignItems: "center",
                justifyContent: "center",
                touchAction: "none",
                px: 0.5,
                "&:hover": {bgcolor: "action.hover"},
                "&:hover .grab": {opacity: 0.9},
              }}
              onMouseDown={onRefResizeMouseDown}
              title="Drag to resize reference panel"
            >
              <GrabBar orientation="vertical"/>
            </Box>

            {/* References */}
            <Box sx={{gridArea: "refs", minWidth: 0, minHeight: 0, overflow: "hidden"}}>
              {chat ? (
                <ReferenceDisplay
                  retrievalResults={selectedRetrievalResults}
                  height="100%"
                  stickyHeader
                  minHeightPx={`${minFixedHeightPx}px`}
                />
              ) : (
                <Box sx={{height: "100%"}}/>
              )}
            </Box>

            {/* Right handle (desktop only) */}
            <Box
              sx={{
                gridArea: "handleR",
                display: {xs: "none", md: "flex"},
                width: `${HANDLE_COL_PX}px`,
                cursor: "col-resize",
                borderRadius: 2,
                alignItems: "center",
                justifyContent: "center",
                touchAction: "none",
                px: 0.5,
                "&:hover": {bgcolor: "action.hover"},
                "&:hover .grab": {opacity: 0.9},
              }}
              onMouseDown={(e) => onWrapperResizeMouseDown(e, "right")}
              title="Drag to resize chat display width"
            >
              <GrabBar orientation="vertical"/>
            </Box>
          </Box>


          {/* Height drag handle BELOW the panel (desktop only) */}
          <Box
            sx={{
              display: {xs: "none", md: "flex"},
              height: HANDLE_HIT_PX,
              mt: 1,
              borderRadius: 2,
              cursor: "ns-resize",
              alignItems: "center",
              justifyContent: "center",
              touchAction: "none",
              "&:hover": {bgcolor: "action.hover"},
              "&:hover .grab": {opacity: 0.9},
            }}
            onMouseDown={onHeightResizeMouseDown}
            title="Drag to resize max height"
          >
            <GrabBar orientation="horizontal"/>
          </Box>
        </Box>
      </Box>
    </Stack>
  );
}
