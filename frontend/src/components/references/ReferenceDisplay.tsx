import {useEffect, useMemo, useRef, useState} from "react";
import {Alert, Box, Paper, Stack, Typography} from "@mui/material";

import {type RetrievalResult, normalizeObjectId} from "../../api/system";
import {type GuidelineEntry, type GuidelineReference, useReferenceApi} from "../../api/references";
import ReferenceDetailView from "./ReferenceDetailView";
import ReferenceList from "./ReferenceList";
import ReferencePdfPanel from "./ReferencePdfPanel";

const HANDLE_HIT_PX = 12;
const HANDLE_GRAB_THICKNESS_PX = 4;
const HANDLE_GRAB_LENGTH_PX = 54;
const DEFAULT_LIST_HEIGHT_RATIO = 0.26;
const MIN_LIST_HEIGHT_RATIO = 0;
const MAX_LIST_HEIGHT_RATIO = 0.55;
const MIN_LIST_HEIGHT_PX = 0;
const MIN_BOTTOM_HEIGHT_PX = 220;
const DEFAULT_PDF_HEIGHT_RATIO = 0.48;
const MIN_PDF_HEIGHT_RATIO = 0.28;
const MAX_PDF_HEIGHT_RATIO = 0.72;
const MIN_PDF_HEIGHT_PX = 240;
const MIN_DETAIL_HEIGHT_PX = 0;

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function GrabBar() {
  return (
    <Box
      className="grab"
      sx={{
        width: HANDLE_GRAB_LENGTH_PX,
        height: HANDLE_GRAB_THICKNESS_PX,
        borderRadius: 999,
        bgcolor: "text.disabled",
        opacity: 0.35,
      }}
    />
  );
}

export default function ReferenceDisplay(props: {
  retrievalResults: RetrievalResult[];
  height?: string | number;
  stickyHeader?: boolean;
  minHeightPx?: number;
}) {
  const {retrievalResults, height = "auto", minHeightPx} = props;
  const {getGuidelineById, getReferenceById} = useReferenceApi();

  const refIds = useMemo(() => {
    const ids = (retrievalResults ?? [])
      .map((result) => normalizeObjectId(result?.reference_id))
      .filter(Boolean);
    return Array.from(new Set(ids));
  }, [retrievalResults]);

  const [selectedRefId, setSelectedRefId] = useState<string | null>(null);
  const [refById, setRefById] = useState<Record<string, GuidelineReference>>({});
  const [errById, setErrById] = useState<Record<string, string>>({});
  const [guidelineById, setGuidelineById] = useState<Record<string, GuidelineEntry>>({});
  const [listHeightRatio, setListHeightRatio] = useState(DEFAULT_LIST_HEIGHT_RATIO);
  const [pdfHeightRatio, setPdfHeightRatio] = useState(DEFAULT_PDF_HEIGHT_RATIO);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const lowerRef = useRef<HTMLDivElement | null>(null);
  const listDragState = useRef<{startY: number; startRatio: number; contentHeight: number} | null>(null);
  const pdfDragState = useRef<{startY: number; startRatio: number; contentHeight: number} | null>(null);

  useEffect(() => {
    setSelectedRefId((current) => (current && refIds.includes(current) ? current : (refIds[0] ?? null)));
  }, [refIds]);

  useEffect(() => {
    let cancelled = false;

    async function fetchMissing() {
      const missing = refIds.filter((id) => !refById[id] && !errById[id]);
      if (!missing.length) return;

      await Promise.all(
        missing.map(async (id) => {
          try {
            const ref = await getReferenceById(id);
            if (cancelled) return;
            setRefById((prev) => ({...prev, [id]: ref}));
          } catch (error: any) {
            if (cancelled) return;
            setErrById((prev) => ({...prev, [id]: error?.message ?? String(error)}));
          }
        }),
      );
    }

    void fetchMissing();
    return () => {
      cancelled = true;
    };
  }, [errById, getReferenceById, refById, refIds]);

  const references = useMemo(
    () => refIds.map((id) => refById[id]).filter((reference): reference is GuidelineReference => Boolean(reference)),
    [refById, refIds],
  );
  const selectedRef = selectedRefId ? refById[selectedRefId] ?? null : null;
  const selectedGuidelineId = useMemo(() => normalizeObjectId(selectedRef?.guideline_id ?? ""), [selectedRef]);
  const selectedGuideline = selectedGuidelineId ? guidelineById[selectedGuidelineId] ?? null : null;

  useEffect(() => {
    if (!selectedGuidelineId || guidelineById[selectedGuidelineId]) return;

    let cancelled = false;

    async function loadGuideline() {
      try {
        const guideline = await getGuidelineById(selectedGuidelineId);
        if (cancelled) return;
        setGuidelineById((prev) => ({...prev, [selectedGuidelineId]: guideline}));
      } catch {
        if (cancelled) return;
      }
    }

    void loadGuideline();
    return () => {
      cancelled = true;
    };
  }, [getGuidelineById, guidelineById, selectedGuidelineId]);

  function onListResizeMouseDown(event: React.MouseEvent) {
    if (event.button !== 0) return;
    event.preventDefault();

    const container = rootRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const contentHeight = rect.height - HANDLE_HIT_PX;
    if (contentHeight <= 0) return;

    listDragState.current = {
      startY: event.clientY,
      startRatio: listHeightRatio,
      contentHeight,
    };

    const onMove = (moveEvent: MouseEvent) => {
      const state = listDragState.current;
      if (!state) return;

      const minRatio = Math.max(MIN_LIST_HEIGHT_RATIO, MIN_LIST_HEIGHT_PX / state.contentHeight);
      const maxRatio = Math.min(MAX_LIST_HEIGHT_RATIO, 1 - MIN_BOTTOM_HEIGHT_PX / state.contentHeight);
      const deltaRatio = (moveEvent.clientY - state.startY) / state.contentHeight;
      setListHeightRatio(clamp(state.startRatio + deltaRatio, minRatio, Math.max(minRatio, maxRatio)));
    };

    const onUp = () => {
      listDragState.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function onPdfResizeMouseDown(event: React.MouseEvent) {
    if (event.button !== 0) return;
    event.preventDefault();

    const container = lowerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const contentHeight = rect.height - HANDLE_HIT_PX;
    if (contentHeight <= 0) return;

    pdfDragState.current = {
      startY: event.clientY,
      startRatio: pdfHeightRatio,
      contentHeight,
    };

    const onMove = (moveEvent: MouseEvent) => {
      const state = pdfDragState.current;
      if (!state) return;

      const minRatio = Math.max(MIN_PDF_HEIGHT_RATIO, MIN_PDF_HEIGHT_PX / state.contentHeight);
      const maxRatio = Math.min(MAX_PDF_HEIGHT_RATIO, 1 - MIN_DETAIL_HEIGHT_PX / state.contentHeight);
      const deltaRatio = (state.startY - moveEvent.clientY) / state.contentHeight;
      setPdfHeightRatio(clamp(state.startRatio + deltaRatio, minRatio, Math.max(minRatio, maxRatio)));
    };

    const onUp = () => {
      pdfDragState.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  if (refIds.length === 0) {
    return (
      <Box sx={{height, minHeight: minHeightPx, p: 0}}>
        <Alert severity="info">No references for this interaction.</Alert>
      </Box>
    );
  }

  return (
    <Box
      ref={rootRef}
      sx={{
        height,
        minHeight: minHeightPx,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <Box sx={{minHeight: MIN_LIST_HEIGHT_PX, height: `${listHeightRatio * 100}%`, pb: 1.5}}>
        <ReferenceList
          references={references}
          selectedReferenceId={selectedRefId ?? ""}
          onSelect={setSelectedRefId}
        />
      </Box>

      <Box
        sx={{
          height: HANDLE_HIT_PX,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "ns-resize",
          borderRadius: 2,
          mb: 1.5,
          "&:hover": {bgcolor: "action.hover"},
          "&:hover .grab": {opacity: 0.9},
        }}
        onMouseDown={onListResizeMouseDown}
        title="Drag to resize reference list"
      >
        <GrabBar />
      </Box>

      {selectedRefId && errById[selectedRefId] ? (
        <Alert severity="error">{errById[selectedRefId]}</Alert>
      ) : (
        <Box ref={lowerRef} sx={{minHeight: MIN_BOTTOM_HEIGHT_PX, flex: "1 1 auto", display: "flex", flexDirection: "column", overflow: "hidden"}}>
          <Box sx={{minHeight: MIN_DETAIL_HEIGHT_PX, height: `${(1 - pdfHeightRatio) * 100}%`, pb: 1.5, overflow: "hidden"}}>
            <ReferenceDetailView
              reference={selectedRef}
              guideline={selectedGuideline}
              emptyStateText={selectedRefId ? "Loading reference..." : "Select a reference."}
            />
          </Box>

          <Box
            sx={{
              height: HANDLE_HIT_PX,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "ns-resize",
              borderRadius: 2,
              mb: 1.5,
              "&:hover": {bgcolor: "action.hover"},
              "&:hover .grab": {opacity: 0.9},
            }}
            onMouseDown={onPdfResizeMouseDown}
            title="Drag to resize PDF area"
          >
            <GrabBar />
          </Box>

          <Box sx={{minHeight: MIN_PDF_HEIGHT_PX, height: `${pdfHeightRatio * 100}%`, flex: "0 0 auto"}}>
            {selectedGuidelineId && selectedRef ? (
              <ReferencePdfPanel
                guidelineId={selectedGuidelineId}
                guideline={selectedGuideline}
                references={[selectedRef]}
                selectedReferenceId={selectedRefId}
                onSelect={setSelectedRefId}
                showHeader={false}
                showReferenceToggle={false}
                framed
              />
            ) : (
              <Paper
                variant="outlined"
                sx={{height: "100%", display: "flex", alignItems: "center", justifyContent: "center", p: 2}}
              >
                <Typography color="text.secondary">Select a reference to load its PDF.</Typography>
              </Paper>
            )}
          </Box>
        </Box>
      )}
    </Box>
  );
}
