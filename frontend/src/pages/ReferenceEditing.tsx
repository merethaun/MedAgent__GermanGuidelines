import {useEffect, useMemo, useRef, useState} from "react";
import {useNavigate, useParams} from "react-router-dom";

import CloseIcon from "@mui/icons-material/Close";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Container,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";

import {useAuth} from "../auth/AuthContext";
import {normalizeObjectId} from "../api/system";
import {type GuidelineEntry, type GuidelineReference, type GuidelineReferenceGroup, useReferenceApi,} from "../api/references";

import ReferencePdfPanel from "../components/references/ReferencePdfPanel";
import ReferenceList from "../components/references/ReferenceList";
import ReferenceDetailEditor from "../components/references/ReferenceDetailEditor";
import CreateReferenceFromTextDialog from "../components/references/CreateReferenceFromTextDialog";

// -------------------- Layout helpers --------------------

const DEFAULT_FIXED_MAX_HEIGHT = "75vh";
const DEFAULT_WRAPPER_WIDTH = "1600px";
const DEFAULT_RIGHT_WIDTH = "36%";

const MIN_FIXED_HEIGHT = "25vh";
const MAX_FIXED_HEIGHT = "100vh";

const MIN_WRAPPER_WIDTH = "960px";
const MAX_WRAPPER_WIDTH = "2400px";

const MIN_RIGHT_WIDTH = "22%";
const MAX_RIGHT_WIDTH = "62%";

const HANDLE_HIT_PX = 12;
const HANDLE_GRAB_THICKNESS_PX = 4;
const HANDLE_GRAB_LENGTH_PX = 54;

const MIN_PDF_COL_PX = 520;
const MIN_RIGHT_COL_PX = 360;

const DEFAULT_LIST_HEIGHT_RATIO = 0.36;
const MIN_LIST_HEIGHT_RATIO = 0.18;
const MAX_LIST_HEIGHT_RATIO = 0.72;
const MIN_LIST_HEIGHT_PX = 180;
const MIN_EDITOR_HEIGHT_PX = 240;

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

  const v = parseFloat(s);
  if (!Number.isFinite(v)) return 0;

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

export default function ReferenceEditorPage() {
  const auth = useAuth() as any;
  const theme = useTheme();
  const navigate = useNavigate();
  const {groupId: rawGroupId, guidelineId: rawGuidelineId} = useParams();

  const referenceGroupId = rawGroupId ?? "";
  const guidelineId = rawGuidelineId ?? "";

  const {
    getReferenceGroupById,
    getGuidelineById,
    listReferences,
    patchReference,
    deleteReference,
  } = useReferenceApi();

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [referenceGroup, setReferenceGroup] = useState<GuidelineReferenceGroup | null>(null);
  const [guideline, setGuideline] = useState<GuidelineEntry | null>(null);
  const [references, setReferences] = useState<GuidelineReference[]>([]);
  const [selectedReferenceId, setSelectedReferenceId] = useState<string>("");

  const [showCreateFromText, setShowCreateFromText] = useState(false);

  const didAutoLoadRef = useRef(false);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const rightPaneRef = useRef<HTMLDivElement | null>(null);

  const [viewport, setViewport] = useState(() => ({
    w: typeof window !== "undefined" ? window.innerWidth : 0,
    h: typeof window !== "undefined" ? window.innerHeight : 0,
  }));

  useEffect(() => {
    const onResize = () => setViewport({w: window.innerWidth, h: window.innerHeight});
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const bp = theme.breakpoints.values as Record<BreakpointKey, number>;

  const [autoFitHeight, setAutoFitHeight] = useState(true);

  const minFixedHeightPx = Math.max(0, resolveCssPx(MIN_FIXED_HEIGHT, "y", viewport, bp));
  const maxFixedHeightPx = Math.max(minFixedHeightPx, resolveCssPx(MAX_FIXED_HEIGHT, "y", viewport, bp));

  const [fixedMaxHeightPx, setFixedMaxHeightPx] = useState<number>(() =>
    Math.max(minFixedHeightPx, resolveCssPx(DEFAULT_FIXED_MAX_HEIGHT, "y", viewport, bp)),
  );

  const minWrapperFromSpecPx = Math.max(0, resolveCssPx(MIN_WRAPPER_WIDTH, "x", viewport, bp));
  const maxWrapperWidthPx = Math.max(0, resolveCssPx(MAX_WRAPPER_WIDTH, "x", viewport, bp));

  const [wrapperWidthPx, setWrapperWidthPx] = useState<number>(() =>
    Math.max(0, resolveCssPx(DEFAULT_WRAPPER_WIDTH, "x", viewport, bp)),
  );

  const [rightWidthRatio, setRightWidthRatio] = useState<number>(() =>
    parsePercentToRatio(DEFAULT_RIGHT_WIDTH),
  );

  const [listHeightRatio, setListHeightRatio] = useState<number>(DEFAULT_LIST_HEIGHT_RATIO);

  const [scrollPadPx, setScrollPadPx] = useState(0);

  const HANDLE_COL_PX = HANDLE_HIT_PX;
  const HANDLE_TOTAL_PX = HANDLE_COL_PX * 3;

  const minWrapperWidthPx = Math.max(
    minWrapperFromSpecPx,
    HANDLE_TOTAL_PX + MIN_PDF_COL_PX + MIN_RIGHT_COL_PX,
  );

  useEffect(() => {
    setWrapperWidthPx((w) => clamp(w, minWrapperWidthPx, maxWrapperWidthPx));
  }, [minWrapperWidthPx, maxWrapperWidthPx]);

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
  }, [autoFitHeight, minFixedHeightPx, maxFixedHeightPx, viewport.h]);

  const panelHeightPx = clamp(fixedMaxHeightPx, minFixedHeightPx, maxFixedHeightPx);
  const wrapperWidthClampedPx = clamp(wrapperWidthPx, minWrapperWidthPx, maxWrapperWidthPx);
  const contentWidthPx = Math.max(1, wrapperWidthClampedPx - HANDLE_TOTAL_PX);

  const minRightRatioBase = clamp(parsePercentToRatio(MIN_RIGHT_WIDTH), 0, 0.99);
  const maxRightRatioBase = clamp(parsePercentToRatio(MAX_RIGHT_WIDTH), 0.01, 1);

  const minRightRatioDynamic = Math.max(minRightRatioBase, MIN_RIGHT_COL_PX / contentWidthPx);
  const maxRightRatioDynamic = Math.min(maxRightRatioBase, 1 - MIN_PDF_COL_PX / contentWidthPx);

  const rightRatioClamped = clamp(
    rightWidthRatio,
    minRightRatioDynamic,
    Math.max(minRightRatioDynamic, maxRightRatioDynamic),
  );

  useEffect(() => {
    setRightWidthRatio((r) =>
      clamp(r, minRightRatioDynamic, Math.max(minRightRatioDynamic, maxRightRatioDynamic)),
    );
  }, [minRightRatioDynamic, maxRightRatioDynamic]);

  const rightWidthClampedPx = rightRatioClamped * contentWidthPx;

  const rightContentHeightPx = Math.max(1, panelHeightPx - HANDLE_HIT_PX);

  const minListRatioDynamic = Math.max(MIN_LIST_HEIGHT_RATIO, MIN_LIST_HEIGHT_PX / rightContentHeightPx);
  const maxListRatioDynamic = Math.min(MAX_LIST_HEIGHT_RATIO, 1 - MIN_EDITOR_HEIGHT_PX / rightContentHeightPx);

  const listRatioClamped = clamp(
    listHeightRatio,
    minListRatioDynamic,
    Math.max(minListRatioDynamic, maxListRatioDynamic),
  );

  useEffect(() => {
    setListHeightRatio((r) =>
      clamp(r, minListRatioDynamic, Math.max(minListRatioDynamic, maxListRatioDynamic)),
    );
  }, [minListRatioDynamic, maxListRatioDynamic]);

  const listHeightPx = listRatioClamped * rightContentHeightPx;

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const compute = () => {
      const availableW = el.clientWidth || viewport.w || window.innerWidth;
      const pad = wrapperWidthClampedPx > availableW ? Math.round((wrapperWidthClampedPx - availableW) / 2) : 0;
      setScrollPadPx(pad);
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
    nextW: number;
  } | null>(null);

  const dragRightState = useRef<{
    startX: number;
    startRightPx: number;
    contentW: number;
    nextRatio: number;
  } | null>(null);

  const dragHeightState = useRef<{
    startY: number;
    startH: number;
    minH: number;
    maxH: number;
    nextH: number;
  } | null>(null);

  const dragListState = useRef<{
    startY: number;
    startListPx: number;
    contentH: number;
    nextRatio: number;
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
      nextW: startW,
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
      const nextW = clamp(st.startW + signed * 2, st.minW, st.maxW);
      st.nextW = nextW;
    };

    const onUp = () => {
      const st = dragWrapperState.current;
      if (st) setWrapperWidthPx(st.nextW);
      dragWrapperState.current = null;
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function onRightResizeMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();

    const el = wrapperRef.current;
    const wrapperW = el?.getBoundingClientRect().width ?? wrapperWidthClampedPx;
    const contentW = Math.max(1, wrapperW - HANDLE_TOTAL_PX);
    const startRightPx = rightRatioClamped * contentW;

    dragRightState.current = {
      startX: e.clientX,
      startRightPx,
      contentW,
      nextRatio: rightRatioClamped,
    };

    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;

    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    const onMove = (ev: MouseEvent) => {
      const st = dragRightState.current;
      if (!st) return;

      const dx = ev.clientX - st.startX;
      const nextRightPx = st.startRightPx - dx;

      const minRightPx = Math.max(MIN_RIGHT_COL_PX, minRightRatioBase * st.contentW);
      const maxRightPx = Math.min(st.contentW - MIN_PDF_COL_PX, maxRightRatioBase * st.contentW);

      const clampedPx = clamp(nextRightPx, minRightPx, Math.max(minRightPx, maxRightPx));
      st.nextRatio = clampedPx / st.contentW;
    };

    const onUp = () => {
      const st = dragRightState.current;
      if (st) setRightWidthRatio(st.nextRatio);
      dragRightState.current = null;
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function onHeightResizeMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();

    setAutoFitHeight(false);

    dragHeightState.current = {
      startY: e.clientY,
      startH: panelHeightPx,
      minH: minFixedHeightPx,
      maxH: maxFixedHeightPx,
      nextH: panelHeightPx,
    };

    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;

    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";

    const onMove = (ev: MouseEvent) => {
      const st = dragHeightState.current;
      if (!st) return;

      const dy = ev.clientY - st.startY;
      const nextH = clamp(st.startH + dy, st.minH, st.maxH);
      st.nextH = nextH;
    };

    const onUp = () => {
      const st = dragHeightState.current;
      if (st) setFixedMaxHeightPx(st.nextH);
      dragHeightState.current = null;
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function onListResizeMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();

    const rightPaneHeight = rightPaneRef.current?.getBoundingClientRect().height ?? panelHeightPx;
    const contentH = Math.max(1, rightPaneHeight - HANDLE_HIT_PX);
    const startListPx = listRatioClamped * contentH;

    dragListState.current = {
      startY: e.clientY,
      startListPx,
      contentH,
      nextRatio: listRatioClamped,
    };

    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;

    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";

    const onMove = (ev: MouseEvent) => {
      const st = dragListState.current;
      if (!st) return;

      const dy = ev.clientY - st.startY;
      const nextListPx = st.startListPx + dy;

      const minListPx = Math.max(MIN_LIST_HEIGHT_PX, MIN_LIST_HEIGHT_RATIO * st.contentH);
      const maxListPx = Math.min(
        st.contentH - MIN_EDITOR_HEIGHT_PX,
        MAX_LIST_HEIGHT_RATIO * st.contentH,
      );

      const clampedPx = clamp(nextListPx, minListPx, Math.max(minListPx, maxListPx));
      st.nextRatio = clampedPx / st.contentH;
    };

    const onUp = () => {
      const st = dragListState.current;
      if (st) setListHeightRatio(st.nextRatio);
      dragListState.current = null;
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  async function loadOnce() {
    if (!referenceGroupId || !guidelineId) return;

    setLoading(true);
    setError(null);

    try {
      const [group, g, refs] = await Promise.all([
        getReferenceGroupById(referenceGroupId),
        getGuidelineById(guidelineId),
        listReferences({
          referenceGroupId,
          guidelineId,
        }),
      ]);

      setReferenceGroup(group);
      setGuideline(g);
      setReferences(refs ?? []);

      const firstId = normalizeObjectId((refs?.[0] as any)?._id) ?? "";
      setSelectedReferenceId((prev) => {
        if (prev && refs.some((r) => normalizeObjectId((r as any)._id) === prev)) {
          return prev;
        }
        return firstId;
      });
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
      setReferenceGroup(null);
      setGuideline(null);
      setReferences([]);
      setSelectedReferenceId("");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!auth.initialized || !auth.authenticated) return;
    if (!referenceGroupId || !guidelineId) return;
    if (didAutoLoadRef.current) return;

    didAutoLoadRef.current = true;
    loadOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.initialized, auth.authenticated, referenceGroupId, guidelineId]);

  const selectedReference = useMemo(() => {
    return (
      references.find((r) => normalizeObjectId((r as any)._id) === selectedReferenceId) ?? null
    );
  }, [references, selectedReferenceId]);

  async function handleSaveReference(patch: Record<string, any>) {
    if (!selectedReferenceId) return;

    setSaving(true);
    setError(null);

    try {
      await patchReference(selectedReferenceId, {
        ...patch,
        created_automatically: false,
      });
      await loadOnce();
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteReference(referenceId: string) {
    const ok = window.confirm("Delete this reference?");
    if (!ok) return;

    setSaving(true);
    setError(null);

    try {
      await deleteReference(referenceId);
      await loadOnce();
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  }

  if (!referenceGroupId || !guidelineId) {
    return <Alert severity="error">Missing route parameters.</Alert>;
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
      <Container maxWidth="lg">
        <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h4" sx={{fontWeight: 800}}>
              Reference editing
            </Typography>
            <Typography color="text.secondary">
              {referenceGroup?.name ?? referenceGroupId}
              {" · "}
              {guideline?.title ?? guidelineId}
            </Typography>
          </Box>

          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              onClick={() => navigate("/admin/references")}
              sx={{textTransform: "none"}}
            >
              Back
            </Button>
            <Button
              variant="outlined"
              onClick={() => loadOnce()}
              disabled={loading}
              sx={{textTransform: "none"}}
            >
              Reload
            </Button>
            <Button
              variant="contained"
              onClick={() => setShowCreateFromText(true)}
              sx={{textTransform: "none"}}
            >
              New from text
            </Button>
          </Stack>
        </Stack>
      </Container>

      {error && (
        <Container maxWidth="lg">
          <Alert severity="error">{error}</Alert>
        </Container>
      )}

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
                xs: `"pdf" "right"`,
                md: `"handleL pdf handleM right handleR"`,
              },
              gridTemplateColumns: {
                xs: "1fr",
                md: `${HANDLE_COL_PX}px minmax(${MIN_PDF_COL_PX}px, 1fr) ${HANDLE_COL_PX}px ${rightWidthClampedPx}px ${HANDLE_COL_PX}px`,
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
                px: 0.5,
                "&:hover": {bgcolor: "action.hover"},
                "&:hover .grab": {opacity: 0.9},
              }}
              onMouseDown={(e) => onWrapperResizeMouseDown(e, "left")}
              title="Drag to resize overall editor width"
            >
              <GrabBar orientation="vertical"/>
            </Box>

            <Box
              sx={{
                gridArea: "pdf",
                minWidth: 0,
                minHeight: 0,
                overflow: "hidden",
              }}
            >
              <ReferencePdfPanel
                guidelineId={guidelineId}
                guideline={guideline}
                references={references}
                selectedReferenceId={selectedReferenceId}
                onSelect={(referenceId) => setSelectedReferenceId(referenceId)}
              />
            </Box>

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
              onMouseDown={onRightResizeMouseDown}
              title="Drag to resize the right panel"
            >
              <GrabBar orientation="vertical"/>
            </Box>

            <Box
              ref={rightPaneRef}
              sx={{
                gridArea: "right",
                minWidth: 0,
                minHeight: 0,
                overflow: "hidden",
              }}
            >
              <Box
                sx={{
                  height: "100%",
                  minHeight: 0,
                  display: "grid",
                  gridTemplateRows: {
                    xs: "minmax(220px, auto) minmax(320px, auto)",
                    md: `${listHeightPx}px ${HANDLE_HIT_PX}px minmax(0, 1fr)`,
                  },
                  rowGap: {xs: 2, md: 0},
                  overflow: "hidden",
                }}
              >
                <Box
                  sx={{
                    minWidth: 0,
                    minHeight: {xs: 220, md: 0},
                    overflow: "hidden",
                  }}
                >
                  <ReferenceList
                    references={references}
                    selectedReferenceId={selectedReferenceId}
                    onSelect={(referenceId) => setSelectedReferenceId(referenceId)}
                  />
                </Box>

                <Box
                  sx={{
                    display: {xs: "none", md: "flex"},
                    height: `${HANDLE_HIT_PX}px`,
                    cursor: "ns-resize",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: 2,
                    touchAction: "none",
                    "&:hover": {bgcolor: "action.hover"},
                    "&:hover .grab": {opacity: 0.9},
                  }}
                  onMouseDown={onListResizeMouseDown}
                  title="Drag to resize reference list and detail editor"
                >
                  <GrabBar orientation="horizontal"/>
                </Box>

                <Box
                  sx={{
                    minWidth: 0,
                    minHeight: {xs: 320, md: 0},
                    overflow: "hidden",
                  }}
                >
                  <ReferenceDetailEditor
                    reference={selectedReference}
                    saving={saving}
                    onSave={handleSaveReference}
                    onDelete={(referenceId) => handleDeleteReference(referenceId)}
                  />
                </Box>
              </Box>
            </Box>

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
              title="Drag to resize overall editor width"
            >
              <GrabBar orientation="vertical"/>
            </Box>
          </Box>

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

      {loading && (
        <Box
          sx={{
            position: "fixed",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <CircularProgress/>
        </Box>
      )}

      <Dialog
        open={showCreateFromText}
        onClose={() => setShowCreateFromText(false)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle sx={{fontWeight: 800}}>
          <Typography variant="h5" sx={{fontWeight: 800}}>
            Create reference from search text
          </Typography>
          <IconButton
            aria-label="close"
            onClick={() => setShowCreateFromText(false)}
            sx={{position: "absolute", right: 8, top: 8}}
            size="small"
          >
            <CloseIcon/>
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <CreateReferenceFromTextDialog
            guidelineId={guidelineId}
            referenceGroupId={referenceGroupId}
            onCancel={() => setShowCreateFromText(false)}
            onCreated={async () => {
              setShowCreateFromText(false);
              await loadOnce();
            }}
          />
        </DialogContent>
      </Dialog>
    </Stack>
  );
}
