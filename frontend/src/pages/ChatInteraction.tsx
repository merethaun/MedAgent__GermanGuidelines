import {useEffect, useMemo, useRef, useState} from "react";
import {useNavigate, useParams} from "react-router-dom";

import CloseIcon from "@mui/icons-material/Close";
import {Alert, Box, Button, CircularProgress, Divider, Slider, Stack, Typography,} from "@mui/material";
import IconButton from "@mui/material/IconButton";

import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";

import {useAuth} from "../auth/AuthContext";
import {type Chat, normalizeObjectId, useSystemApi} from "../api/system";
import {useChatApi} from "../api/chat";

import ChatCreator from "../components/chat/ChatCreator";
import ChatHeader from "../components/chat/ChatHeader";
import ChatDisplay from "../components/chat/ChatDisplay";
import ReferenceDisplay from "../components/references/ReferenceDisplay";

const DEBUG = false;

// -------------------- Layout helpers --------------------

/**
 * Simplified sizing model:
 * - One fixed panel max-height (defaults to "fills the rest of the page")
 * - One fixed wrapper width (can exceed viewport)
 * - One fixed reference width (split handle)
 */
const DEFAULT_FIXED_MAX_HEIGHT_PX = 760;
const DEFAULT_WRAPPER_WIDTH_PX = 1600;
const DEFAULT_REFERENCE_WIDTH_PX = 420;

const MIN_FIXED_HEIGHT_PX = 320;
const MAX_FIXED_HEIGHT_PX = 2600;

const MIN_REFERENCE_WIDTH_PX = 320;
const MAX_REFERENCE_WIDTH_PX = 780;

const MIN_WRAPPER_WIDTH_PX = 900;
const MAX_WRAPPER_WIDTH_PX = 3600;

const HANDLE_HIT_PX = 12;
const HANDLE_GRAB_THICKNESS_PX = 4;
const HANDLE_GRAB_LENGTH_PX = 54;

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
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

type PreviewFocus = "height" | "width" | "refs" | null;

function LayoutPreview(props: {
  wrapperWidthPx: number;
  fixedMaxHeightPx: number;
  referenceWidthPx: number;
  focus: PreviewFocus;
  maxW?: number; // preview box max width
  maxH?: number; // preview box max height
}) {
  const {
    wrapperWidthPx,
    fixedMaxHeightPx,
    referenceWidthPx,
    focus,
    maxW = 260,
    maxH = 160,
  } = props;

  const w = Math.max(1, wrapperWidthPx);
  const h = Math.max(1, fixedMaxHeightPx);
  const refW = Math.max(0, Math.min(referenceWidthPx, w));
  const chatW = Math.max(0, w - refW);

  // Scale content down so it always fits in preview bounds.
  const scale = Math.min(maxW / w, maxH / h, 1);

  const outline = (isOn: boolean) => ({
    outline: isOn ? "2px solid" : "1px solid",
    outlineColor: isOn ? "primary.main" : "divider",
  });

  return (
    <Box
      sx={{
        width: maxW,
        height: maxH,
        borderColor: "divider",
        p: 1,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        gap: 0.75,
        flexShrink: 0,
      }}
    >
      {/* The scaled “mini-map” */}
      <Box sx={{position: "relative", width: "100%", flex: 1, overflow: "hidden"}}>
        <Box
          sx={{
            position: "absolute",
            left: "50%",
            top: 0,
            transform: `translateX(-50%) scale(${scale})`,
            transformOrigin: "top center",
            width: w,
            height: h,
            borderRadius: 1.5,
            bgcolor: "background.paper",
            ...outline(focus === "width" || focus === "height"),
          }}
        >
          {/* Chat area */}
          <Box
            sx={{
              position: "absolute",
              left: 0,
              top: 0,
              width: chatW,
              height: h,
              borderRadius: "6px 0 0 6px",
              bgcolor: "action.hover",
              ...(focus === "width" ? outline(true) : {}),
              outlineOffset: -1,
            }}
          />

          {/* Reference panel */}
          <Box
            sx={{
              position: "absolute",
              right: 0,
              top: 0,
              width: refW,
              height: h,
              borderRadius: "0 6px 6px 0",
              bgcolor: "action.selected",
              ...outline(focus === "refs"),
              outlineOffset: -1,
            }}
          />

          {/* Middle divider (ref resize handle position) */}
          <Box
            sx={{
              position: "absolute",
              left: chatW - 1,
              top: 0,
              width: 2,
              height: h,
              bgcolor: focus === "refs" ? "primary.main" : "divider",
              opacity: focus === "refs" ? 1 : 0.8,
            }}
          />

          {/* Bottom “height handle” indicator */}
          <Box
            sx={{
              position: "absolute",
              left: "20%",
              bottom: 6,
              width: "60%",
              height: 6,
              borderRadius: 999,
              bgcolor: focus === "height" ? "primary.main" : "divider",
              opacity: focus === "height" ? 1 : 0.9,
            }}
          />
        </Box>
      </Box>

      {/* Dimensions (kept tiny) */}
      <Box sx={{display: "flex", justifyContent: "space-between", gap: 1}}>
        <Typography variant="caption" sx={{opacity: 0.8}}>
          {Math.round(w)}×{Math.round(h)} px
        </Typography>
        <Typography variant="caption" sx={{opacity: 0.8}}>
          refs: {Math.round(refW)} px
        </Typography>
      </Box>
    </Box>
  );
}


// -------------------- Page component --------------------

export default function ChatInteractionPage() {
  const auth = useAuth() as any;
  const navigate = useNavigate();
  const {chatId: rawChatId} = useParams();

  const chatId = rawChatId ?? "";
  const {getWorkflowById} = useSystemApi();
  const {getChatById, poseChat} = useChatApi();

  const [showCreator, setShowCreator] = useState(false);

  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [chat, setChat] = useState<Chat | null>(null);
  const [workflowName, setWorkflowName] = useState<string | undefined>(undefined);
  const [selectedInteractionIndex, setSelectedInteractionIndex] = useState<number>(-1);

  const username: string | undefined = auth.username;

  // --- Layout state ---
  const [showLayout, setShowLayout] = useState(false);
  const [previewFocus, setPreviewFocus] = useState<PreviewFocus>(null);

  // Height: one fixed *max* height (defaults to "fills the rest of the page")
  const [autoFitHeight, setAutoFitHeight] = useState(true);
  const [fixedMaxHeightPx, setFixedMaxHeightPx] = useState(DEFAULT_FIXED_MAX_HEIGHT_PX);

  // Width: one fixed wrapper width (can exceed viewport)
  const [wrapperWidthPx, setWrapperWidthPx] = useState(DEFAULT_WRAPPER_WIDTH_PX);

  // Split: fixed reference width
  const [referenceWidthPx, setReferenceWidthPx] = useState(DEFAULT_REFERENCE_WIDTH_PX);

  // Scroll container (used when wrapperWidthPx > available width)
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [scrollPadPx, setScrollPadPx] = useState(0);

  const wrapperRef = useRef<HTMLDivElement | null>(null);

  const dragWrapperState = useRef<{
    startX: number;
    startW: number;
    side: "left" | "right";
    minW: number;
  } | null>(null);

  const MIN_CHAT_COL_PX = 360;
  const HANDLE_COL_PX = HANDLE_HIT_PX;

  // Wrapper must be wide enough for: chat + middle handle + refs
  const minWrapperWidthPx = Math.max(
    MIN_WRAPPER_WIDTH_PX,
    MIN_CHAT_COL_PX +
    HANDLE_COL_PX +
    clamp(referenceWidthPx, MIN_REFERENCE_WIDTH_PX, MAX_REFERENCE_WIDTH_PX),
  );

  // Keep wrapper wide enough when refs width changes.
  useEffect(() => {
    setWrapperWidthPx((w) => clamp(w, minWrapperWidthPx, MAX_WRAPPER_WIDTH_PX));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minWrapperWidthPx]);

  // Auto-fit: choose a sensible initial max height that fills the rest of the viewport.
  useEffect(() => {
    if (!autoFitHeight) return;

    const compute = () => {
      const el = panelRef.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top;
      const available = Math.floor(window.innerHeight - top - 16);
      setFixedMaxHeightPx(clamp(available, MIN_FIXED_HEIGHT_PX, MAX_FIXED_HEIGHT_PX));
    };

    const raf = window.requestAnimationFrame(compute);
    window.addEventListener("resize", compute);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", compute);
    };
  }, [autoFitHeight]);

  // When the wrapper exceeds the available width, pad the scroll container symmetrically
  // and scroll so the block stays centered.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const compute = () => {
      const availableW = el.clientWidth || window.innerWidth;
      const pad = wrapperWidthPx > availableW ? Math.round((wrapperWidthPx - availableW) / 2) : 0;
      setScrollPadPx(pad);
      el.scrollLeft = pad > 0 ? pad * 2 : 0;
    };

    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, [wrapperWidthPx]);

  function onWrapperResizeMouseDown(e: React.MouseEvent, side: "left" | "right") {
    if (e.button !== 0) return;
    e.preventDefault();

    const el = wrapperRef.current;
    if (!el) return;

    const currentW = el.getBoundingClientRect().width;

    const startW = clamp(currentW, minWrapperWidthPx, MAX_WRAPPER_WIDTH_PX);

    dragWrapperState.current = {
      startX: e.clientX,
      startW,
      side,
      minW: minWrapperWidthPx,
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
      const nextW = clamp(st.startW + signed * 2, st.minW, MAX_WRAPPER_WIDTH_PX);
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
  const panelRef = useRef<HTMLDivElement | null>(null);
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
  const dragRefState = useRef<{ startX: number; startW: number } | null>(null);

  function onRefResizeMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();
    dragRefState.current = {startX: e.clientX, startW: referenceWidthPx};

    const onMove = (ev: MouseEvent) => {
      const st = dragRefState.current;
      if (!st) return;
      const dx = ev.clientX - st.startX;
      setReferenceWidthPx(clamp(st.startW - dx, MIN_REFERENCE_WIDTH_PX, MAX_REFERENCE_WIDTH_PX));
      // NOTE: st.startW - dx makes dragging left increase refs, right decrease refs
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
    dragHeightState.current = {startY: e.clientY, startH: fixedMaxHeightPx};

    const onMove = (ev: MouseEvent) => {
      const st = dragHeightState.current;
      if (!st) return;
      const dy = ev.clientY - st.startY;
      setFixedMaxHeightPx(clamp(st.startH + dy, MIN_FIXED_HEIGHT_PX, MAX_FIXED_HEIGHT_PX));
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

  async function send(userInput: string) {
    if (!chatId) return;

    setSending(true);
    setError(null);

    try {
      const updated = await poseChat(chatId, userInput);
      setChat(updated);

      // keep selection on newest (common chat behavior)
      const idx = (updated.interactions?.length ?? 0) - 1;
      setSelectedInteractionIndex(idx >= 0 ? idx : -1);

      if (DEBUG) console.log("[ChatInteraction] updated chat:", updated);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setSending(false);
    }
  }

  if (!chatId) {
    return <Alert severity="warning">No chat id in route.</Alert>;
  }

  const panelHeightPx = clamp(fixedMaxHeightPx, MIN_FIXED_HEIGHT_PX, MAX_FIXED_HEIGHT_PX);
  const wrapperWidthClampedPx = clamp(wrapperWidthPx, minWrapperWidthPx, MAX_WRAPPER_WIDTH_PX);
  const referenceWidthClampedPx = clamp(referenceWidthPx, MIN_REFERENCE_WIDTH_PX, MAX_REFERENCE_WIDTH_PX);

  return (
    <Stack spacing={2.5}>
      <ChatHeader
        chatName={chatName}
        chatId={chatId}
        username={username}
        workflowName={workflowName}
        workflowId={chat ? normalizeObjectId((chat as any).workflow_system_id) : undefined}
        onNewChat={() => setShowCreator(true)}
        rightSlot={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" onClick={() => setShowLayout(true)} sx={{textTransform: "none"}}>
              Layout
            </Button>
            <Button variant="outlined" disabled sx={{textTransform: "none"}}>
              Export
            </Button>
          </Stack>
        }
      />

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

      {/* Layout dialog */}
      <Dialog open={showLayout} onClose={() => setShowLayout(false)} fullWidth maxWidth="md">
        <DialogTitle sx={{fontWeight: 800}}>
          <Typography variant="h5" sx={{fontWeight: 800}}>Layout</Typography>
          <IconButton
            aria-label="close"
            onClick={() => setShowLayout(false)}
            sx={{position: "absolute", right: 8, top: 8}}
            size="small"
          >
            <CloseIcon/>
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2.25}>
            <Stack direction={{xs: "column", md: "row"}} spacing={2} alignItems={{md: "flex-start"}}>
              <Box sx={{flex: 1, minWidth: 260}}>
                <Typography variant="subtitle2" sx={{fontWeight: 800, mb: 1}}>
                  Height
                </Typography>
                <Typography variant="caption" sx={{display: "block"}}>
                  Panel max height (px)
                </Typography>
                <Box
                  onMouseEnter={() => setPreviewFocus("height")}
                  onMouseLeave={() => setPreviewFocus(null)}
                  onFocus={() => setPreviewFocus("height")}
                  onBlur={() => setPreviewFocus(null)}
                >
                  <Slider
                    value={fixedMaxHeightPx}
                    min={MIN_FIXED_HEIGHT_PX}
                    max={MAX_FIXED_HEIGHT_PX}
                    step={10}
                    valueLabelDisplay="auto"
                    onChange={(_, v) => {
                      setAutoFitHeight(false);
                      setFixedMaxHeightPx(v as number);
                    }}
                  />
                </Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{mt: 0.5}}>
                  <Button
                    size="small"
                    variant={autoFitHeight ? "contained" : "outlined"}
                    onClick={() => setAutoFitHeight(true)}
                    sx={{textTransform: "none"}}
                  >
                    Fit to page
                  </Button>
                  <Typography variant="caption" sx={{opacity: 0.75}}>
                    Or drag the horizontal handle below the panel.
                  </Typography>
                </Stack>
              </Box>

              <Divider flexItem orientation="vertical" sx={{display: {xs: "none", md: "block"}}}/>

              <Box sx={{flex: 1, minWidth: 260}}>
                <Typography variant="subtitle2" sx={{fontWeight: 800, mb: 1}}>
                  Width
                </Typography>
                <Typography variant="caption" sx={{display: "block"}}>
                  Wrapper width (px) — can exceed 100%
                </Typography>
                <Box
                  onMouseEnter={() => setPreviewFocus("width")}
                  onMouseLeave={() => setPreviewFocus(null)}
                  onFocus={() => setPreviewFocus("width")}
                  onBlur={() => setPreviewFocus(null)}
                >
                  <Slider
                    value={wrapperWidthPx}
                    min={minWrapperWidthPx}
                    max={MAX_WRAPPER_WIDTH_PX}
                    step={20}
                    valueLabelDisplay="auto"
                    onChange={(_, v) => setWrapperWidthPx(v as number)}
                  />
                </Box>
                <Typography variant="caption" sx={{display: "block", opacity: 0.75}}>
                  Tip: Drag the left/right vertical handles to resize symmetrically.
                </Typography>

                <Typography variant="subtitle2" sx={{fontWeight: 800, mt: 2, mb: 1}}>
                  Reference panel
                </Typography>
                <Typography variant="caption" sx={{display: "block"}}>
                  Reference width (px)
                </Typography>
                <Box
                  onMouseEnter={() => setPreviewFocus("refs")}
                  onMouseLeave={() => setPreviewFocus(null)}
                  onFocus={() => setPreviewFocus("refs")}
                  onBlur={() => setPreviewFocus(null)}
                >
                  <Slider
                    value={referenceWidthPx}
                    min={MIN_REFERENCE_WIDTH_PX}
                    max={MAX_REFERENCE_WIDTH_PX}
                    step={10}
                    valueLabelDisplay="auto"
                    onChange={(_, v) => setReferenceWidthPx(v as number)}
                  />
                </Box>
                <Typography variant="caption" sx={{display: "block", opacity: 0.75}}>
                  Tip: Drag the middle handle between chat and references.
                </Typography>
              </Box>
            </Stack>

            {panelSize && (
              <Box>
                <Divider sx={{my: 1.5}}/>
                <Stack direction={{xs: "column", md: "row"}} justifyContent={{md: "space-between"}}>
                  <Typography variant="caption" sx={{opacity: 0.85}}>
                    Current panel size: {Math.round(panelSize.w)} × {Math.round(panelSize.h)} px
                  </Typography>
                  <LayoutPreview
                    wrapperWidthPx={wrapperWidthPx}
                    fixedMaxHeightPx={fixedMaxHeightPx}
                    referenceWidthPx={referenceWidthPx}
                    focus={previewFocus}
                    maxW={240}
                    maxH={150}
                  />
                </Stack>
              </Box>
            )}
          </Stack>
        </DialogContent>

        <DialogActions>
          <Button
            onClick={() => {
              setAutoFitHeight(true);
              setFixedMaxHeightPx(DEFAULT_FIXED_MAX_HEIGHT_PX);
              setWrapperWidthPx(DEFAULT_WRAPPER_WIDTH_PX);
              setReferenceWidthPx(DEFAULT_REFERENCE_WIDTH_PX);
            }}
            sx={{textTransform: "none"}}
          >
            Reset
          </Button>
          <Button variant="contained" onClick={() => setShowLayout(false)} sx={{textTransform: "none"}}>
            Done
          </Button>
        </DialogActions>
      </Dialog>

      {error && <Alert severity="error">{error}</Alert>}

      {/* Centered wrapper: adjustable overall width (can exceed viewport) */}
      <Box
        ref={scrollRef}
        sx={{
          width: "100%",
          overflowX: {xs: "visible", md: "auto"},
          overflowY: "visible",
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
          }}
        >
          {/* Left/right handles to resize the ENTIRE wrapper symmetrically (desktop only) */}
          <Box
            sx={{
              display: {xs: "none", md: "block"},
              position: "absolute",
              top: 0,
              bottom: 0,
              left: -Math.floor(HANDLE_HIT_PX / 2),
              width: HANDLE_HIT_PX,
              cursor: "ew-resize",
              zIndex: 10,
              borderRadius: 2,
              touchAction: "none",
              "&:hover": {bgcolor: "action.hover"},
              "&:hover .grab": {opacity: 0.9},
            }}
            onMouseDown={(e) => onWrapperResizeMouseDown(e, "left")}
            title="Drag to resize width"
          >
            <Box sx={{position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)"}}>
              <GrabBar orientation="vertical"/>
            </Box>
          </Box>

          <Box
            sx={{
              display: {xs: "none", md: "block"},
              position: "absolute",
              top: 0,
              bottom: 0,
              right: -Math.floor(HANDLE_HIT_PX / 2),
              width: HANDLE_HIT_PX,
              cursor: "ew-resize",
              zIndex: 10,
              borderRadius: 2,
              touchAction: "none",
              "&:hover": {bgcolor: "action.hover"},
              "&:hover .grab": {opacity: 0.9},
            }}
            onMouseDown={(e) => onWrapperResizeMouseDown(e, "right")}
            title="Drag to resize width"
          >
            <Box sx={{position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)"}}>
              <GrabBar orientation="vertical"/>
            </Box>
          </Box>

          {/* Panel container: fixed max-height (auto-fits to the rest of the viewport by default) */}
          <Box
            ref={panelRef}
            sx={{
              position: "relative",
              height: {xs: "auto", md: `${panelHeightPx}px`},
              maxHeight: {xs: "none", md: `${panelHeightPx}px`},
              minHeight: {xs: 520, md: MIN_FIXED_HEIGHT_PX},

              display: "grid",
              gap: 0,
              gridTemplateAreas: {
                xs: `"chat" "refs"`,
                md: `"chat handle refs"`,
              },
              gridTemplateColumns: {
                xs: "1fr",
                md: `minmax(${MIN_CHAT_COL_PX}px, 1fr) ${HANDLE_COL_PX}px ${referenceWidthClampedPx}px`,
              },
              gridTemplateRows: {
                xs: "auto auto",
                md: "1fr",
              },

              columnGap: {xs: 2, md: 1.25},
              rowGap: {xs: 2, md: 0},
              alignItems: "stretch",
            }}
          >
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
                  minHeightPx={MIN_FIXED_HEIGHT_PX}
                />
              )}
            </Box>

            {/* Divider / drag handle (desktop only) */}
            <Box
              sx={{
                gridArea: "handle",
                display: {xs: "none", md: "flex"},
                width: `${HANDLE_COL_PX}px`,
                cursor: "col-resize",
                borderRadius: 2,
                alignItems: "center",
                justifyContent: "center",
                touchAction: "none",
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
                  minHeightPx={MIN_FIXED_HEIGHT_PX}
                />
              ) : (
                <Box sx={{height: "100%"}}/>
              )}
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
