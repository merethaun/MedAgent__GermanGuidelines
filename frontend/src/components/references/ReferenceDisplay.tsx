import {useEffect, useMemo, useRef, useState} from "react";
import {Alert, Box, Chip, FormControl, MenuItem, Paper, Select, type SelectChangeEvent, Stack, Typography} from "@mui/material";
import {alpha} from "@mui/material/styles";

import {normalizeObjectId, type RetrievalResult} from "../../api/system";
import {type GuidelineEntry, type GuidelineHierarchyEntry, type GuidelineReference, useReferenceApi} from "../../api/references";
import ReferenceDetailView from "./ReferenceDetailView";
import ReferencePdfPanel from "./ReferencePdfPanel";

const HANDLE_HIT_PX = 12;
const HANDLE_GRAB_THICKNESS_PX = 4;
const HANDLE_GRAB_LENGTH_PX = 54;
const REFERENCE_SELECTOR_HEIGHT_PX = 40;
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

function getReferenceTitle(reference: GuidelineReference): string {
  switch (reference.type) {
    case "text":
      return reference.contained_text.slice(0, 80) || "Text reference";
    case "image":
      return reference.caption?.slice(0, 80) || "Image reference";
    case "table":
      return reference.caption?.slice(0, 80) || "Table reference";
    case "recommendation":
      return reference.recommendation_title?.slice(0, 80) || "Recommendation";
    case "statement":
      return reference.statement_title?.slice(0, 80) || "Statement";
    case "metadata":
      return `${reference.metadata_type}: ${reference.metadata_content.slice(0, 60)}`;
    default:
      return "Reference";
  }
}

function getHierarchyOrders(entries?: GuidelineHierarchyEntry[]): number[] {
  return (entries ?? []).map((entry) => {
    const value = entry.order ?? 0;
    return Number.isFinite(value) ? value : 0;
  });
}

function getHierarchyPath(entries?: GuidelineHierarchyEntry[]): string | null {
  const orders = getHierarchyOrders(entries);
  return orders.length ? orders.join(".") : null;
}

function compareNumberArrays(a: number[], b: number[]): number {
  const maxLength = Math.max(a.length, b.length);

  for (let index = 0; index < maxLength; index += 1) {
    const aValue = a[index];
    const bValue = b[index];

    if (aValue == null && bValue == null) return 0;
    if (aValue == null) return -1;
    if (bValue == null) return 1;
    if (aValue !== bValue) return aValue - bValue;
  }

  return 0;
}

function getReferenceMeta(reference: GuidelineReference): string[] {
  const firstPage = reference.bboxs?.[0]?.page;
  const hierarchyPath = getHierarchyPath(reference.document_hierarchy);

  return [
    reference.type,
    hierarchyPath ? `order ${hierarchyPath}` : null,
    firstPage != null ? `p. ${firstPage}` : null,
  ].filter(Boolean);
}

function ReferenceSummaryRow(props: {
  reference: GuidelineReference | null;
  placeholder: string;
}) {
  const {reference, placeholder} = props;
  const title = reference ? getReferenceTitle(reference) : placeholder;
  const meta = reference ? getReferenceMeta(reference) : [];

  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{minWidth: 0, width: "100%", overflow: "hidden"}}>
      <Typography
        variant="body2"
        sx={{
          flex: "1 1 auto",
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {title}
      </Typography>
      {meta.length ? (
        <Stack
          direction="row"
          spacing={0.75}
          alignItems="center"
          sx={{flex: "0 1 auto", minWidth: 0, overflow: "hidden"}}
        >
          {meta.map((item) => (
            <Chip
              key={item}
              label={item}
              size="small"
              variant="outlined"
              sx={{
                flex: "0 0 auto",
                bgcolor: "background.paper",
                borderColor: "divider",
                "& .MuiChip-label": {
                  px: 1,
                },
              }}
            />
          ))}
        </Stack>
      ) : null}
    </Stack>
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
  const [pdfHeightRatio, setPdfHeightRatio] = useState(DEFAULT_PDF_HEIGHT_RATIO);
  const [detailCollapsed, setDetailCollapsed] = useState(false);

  const lowerRef = useRef<HTMLDivElement | null>(null);
  const pdfDragState = useRef<{
    startY: number;
    startRatio: number;
    contentHeight: number;
    nextRatio: number;
  } | null>(null);

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

  const references = useMemo(() => {
    return refIds
      .map((id) => refById[id])
      .filter((reference): reference is GuidelineReference => Boolean(reference))
      .sort((a, b) => {
        const hierarchyCompare = compareNumberArrays(
          getHierarchyOrders(a.document_hierarchy),
          getHierarchyOrders(b.document_hierarchy),
        );
        if (hierarchyCompare !== 0) return hierarchyCompare;

        const aPage = a.bboxs?.[0]?.page ?? Number.MAX_SAFE_INTEGER;
        const bPage = b.bboxs?.[0]?.page ?? Number.MAX_SAFE_INTEGER;
        if (aPage !== bPage) return aPage - bPage;

        return getReferenceTitle(a).localeCompare(getReferenceTitle(b));
      });
  }, [refById, refIds]);
  const selectedRef = selectedRefId ? refById[selectedRefId] ?? null : null;
  const selectedGuidelineId = useMemo(() => normalizeObjectId(selectedRef?.guideline_id ?? ""), [selectedRef]);
  const selectedGuideline = selectedGuidelineId ? guidelineById[selectedGuidelineId] ?? null : null;
  const selectedValue = selectedRefId && references.some((reference) => normalizeObjectId(reference._id ?? "") === selectedRefId)
    ? selectedRefId
    : "";

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
      nextRatio: pdfHeightRatio,
    };

    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;

    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: MouseEvent) => {
      const state = pdfDragState.current;
      if (!state) return;

      const minRatio = Math.max(MIN_PDF_HEIGHT_RATIO, MIN_PDF_HEIGHT_PX / state.contentHeight);
      const maxRatio = Math.min(MAX_PDF_HEIGHT_RATIO, 1 - MIN_DETAIL_HEIGHT_PX / state.contentHeight);
      const deltaRatio = (state.startY - moveEvent.clientY) / state.contentHeight;
      state.nextRatio = clamp(state.startRatio + deltaRatio, minRatio, Math.max(minRatio, maxRatio));
    };

    const onUp = () => {
      const state = pdfDragState.current;
      if (state) setPdfHeightRatio(state.nextRatio);
      pdfDragState.current = null;
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
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
      sx={{
        height,
        minHeight: minHeightPx,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
          flex: "0 0 auto",
          mb: 1.5,
        }}
      >
        <Paper variant="outlined" sx={{p: 2}}>
          <Typography variant="h6" sx={{fontWeight: 800, mb: 1}}>
            References
          </Typography>
          <FormControl fullWidth size="small">
            <Select<string>
              displayEmpty
              value={selectedValue}
              onChange={(event: SelectChangeEvent<string>) => setSelectedRefId(event.target.value || null)}
              inputProps={{"aria-label": "Select reference"}}
              MenuProps={{
                PaperProps: {
                  sx: (theme) => ({
                    mt: 1,
                    borderRadius: 2,
                    "& .MuiMenuItem-root": {
                      py: 1,
                    },
                    "& .MuiMenuItem-root.Mui-selected": {
                      bgcolor: alpha(theme.palette.primary.main, 0.14),
                    },
                    "& .MuiMenuItem-root.Mui-selected:hover": {
                      bgcolor: alpha(theme.palette.primary.main, 0.2),
                    },
                  }),
                },
              }}
              renderValue={(value) => {
                const selectedReference = value ? refById[value] : null;
                const placeholder = references.length === 0 ? "Loading references..." : "Select a reference";

                return (
                  <ReferenceSummaryRow
                    reference={selectedReference}
                    placeholder={placeholder}
                  />
                );
              }}
              sx={(theme) => ({
                height: REFERENCE_SELECTOR_HEIGHT_PX,
                borderRadius: 2,
                bgcolor: alpha(theme.palette.primary.main, 0.08),
                "& .MuiOutlinedInput-notchedOutline": {
                  border: "none",
                },
                "&:hover .MuiOutlinedInput-notchedOutline": {
                  border: "none",
                },
                "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                  border: "none",
                },
                "& .MuiSelect-select": {
                  display: "flex",
                  alignItems: "center",
                  overflow: "hidden",
                  pr: 4,
                },
                "& .MuiSelect-icon": {
                  color: theme.palette.primary.main,
                },
              })}
            >
              {!selectedValue ? (
                <MenuItem value="" disabled>
                  {references.length === 0 ? "Loading references..." : "Select a reference"}
                </MenuItem>
              ) : null}
              {references.map((reference) => {
                const referenceId = normalizeObjectId(reference._id ?? "");
                return (
                  <MenuItem
                    key={referenceId}
                    value={referenceId}
                    sx={{
                      maxWidth: "100%",
                    }}
                  >
                    <ReferenceSummaryRow reference={reference} placeholder="Reference" />
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>
        </Paper>
      </Box>

      {selectedRefId && errById[selectedRefId] ? (
        <Alert severity="error">{errById[selectedRefId]}</Alert>
      ) : (
        <Box ref={lowerRef} sx={{minHeight: MIN_BOTTOM_HEIGHT_PX, flex: "1 1 auto", display: "flex", flexDirection: "column", overflow: "hidden"}}>
          <Box
            sx={detailCollapsed
              ? {
                flex: "0 0 auto",
                pb: 1.5,
                overflow: "hidden",
              }
              : {
                minHeight: MIN_DETAIL_HEIGHT_PX,
                height: `${(1 - pdfHeightRatio) * 100}%`,
                pb: 1.5,
                overflow: "hidden",
              }}
          >
            <ReferenceDetailView
              reference={selectedRef}
              guideline={selectedGuideline}
              emptyStateText={selectedRefId ? "Loading reference..." : "Select a reference."}
              collapsed={detailCollapsed}
              onToggleCollapsed={() => setDetailCollapsed((current) => !current)}
            />
          </Box>

          {!detailCollapsed ? (
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
              <GrabBar/>
            </Box>
          ) : null}

          <Box
            sx={detailCollapsed
              ? {minHeight: MIN_PDF_HEIGHT_PX, flex: "1 1 auto"}
              : {minHeight: MIN_PDF_HEIGHT_PX, height: `${pdfHeightRatio * 100}%`, flex: "0 0 auto"}}
          >
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
