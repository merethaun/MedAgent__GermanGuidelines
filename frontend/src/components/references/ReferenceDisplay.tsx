import {useEffect, useMemo, useState} from "react";
import {Alert, Box, Chip, Divider, List, ListItemButton, ListItemText, Paper, Stack, Typography,} from "@mui/material";

import {normalizeObjectId, type RetrievalResult} from "../../api/system";
import {type GuidelineReference, useReferenceApi} from "../../api/reference";

function pagesFromBBoxes(ref?: GuidelineReference): string {
  const pages = (ref?.bboxs ?? []).map((b) => b.page).filter((p) => typeof p === "number");
  if (pages.length === 0) return "—";
  const uniq = Array.from(new Set(pages)).sort((a, b) => a - b);
  return uniq.join(", ");
}

function hierarchyPath(ref?: GuidelineReference): string {
  const h = ref?.document_hierarchy ?? [];
  if (!h.length) return "—";
  return h
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    .map((x) => (x.heading_number ? `${x.heading_number} ` : "") + x.title)
    .join(" > ");
}

function renderMainContent(ref: GuidelineReference): { title: string; body?: string } {
  switch (ref.type) {
    case "text":
      return {title: "Text", body: ref.contained_text ?? ""};
    case "table":
      return {
        title: ref.caption ? `Table — ${ref.caption}` : "Table",
        body: ref.table_markdown ?? ref.plain_text ?? "",
      };
    case "image":
      return {title: ref.caption ? `Image — ${ref.caption}` : "Image", body: ref.describing_text ?? ""};
    case "recommendation":
      return {
        title: ref.recommendation_title ? `Recommendation — ${ref.recommendation_title}` : "Recommendation",
        body: ref.recommendation_content ?? "",
      };
    case "statement":
      return {
        title: ref.statement_title ? `Statement — ${ref.statement_title}` : "Statement",
        body: ref.statement_content ?? "",
      };
    case "metadata":
      return {
        title: ref.metadata_type ? `Metadata — ${ref.metadata_type}` : "Metadata",
        body: ref.metadata_content ?? "",
      };
    default:
      return {title: "Reference", body: ""};
  }
}

export default function ReferenceDisplay(props: {
  retrievalResults: RetrievalResult[];
  height?: string | number;
  stickyHeader?: boolean;
  minHeightPx?: number;
}) {
  const {retrievalResults, height = "auto", stickyHeader = false, minHeightPx} = props;
  const {getReferenceById} = useReferenceApi();

  const refIds = useMemo(() => {
    const ids = (retrievalResults ?? [])
      .map((r: any) => normalizeObjectId(r?.reference_id))
      .filter(Boolean);
    return Array.from(new Set(ids));
  }, [retrievalResults]);

  const [selectedRefId, setSelectedRefId] = useState<string | null>(null);
  const [refById, setRefById] = useState<Record<string, GuidelineReference>>({});
  const [errById, setErrById] = useState<Record<string, string>>({});

  useEffect(() => {
    setSelectedRefId(refIds[0] ?? null);
  }, [refIds]);

  useEffect(() => {
    let cancelled = false;

    async function fetchMissing() {
      const missing = refIds.filter((id) => !refById[id] && !errById[id]);
      if (missing.length === 0) return;

      await Promise.all(
        missing.map(async (id) => {
          try {
            const ref = await getReferenceById(id);
            if (cancelled) return;
            setRefById((prev) => ({...prev, [id]: ref}));
          } catch (e: any) {
            if (cancelled) return;
            setErrById((prev) => ({...prev, [id]: e?.message ?? String(e)}));
          }
        }),
      );
    }

    void fetchMissing();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refIds.join("|")]);

  const selectedRef = selectedRefId ? refById[selectedRefId] : null;

  return (
    <Paper
      variant="outlined"
      sx={{
        height,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        minHeight: minHeightPx,
      }}
    >
      {/* Sticky header area */}
      <Box
        sx={{
          p: 2,
          ...(stickyHeader
            ? {position: "sticky", top: 0, zIndex: 2, bgcolor: "background.paper"}
            : null),
        }}
      >
        <Typography variant="h6" sx={{fontWeight: 800}}>
          References
        </Typography>
        <Divider sx={{mt: 1.5}}/>
      </Box>

      {refIds.length === 0 ? (
        <Box sx={{p: 2}}>
          <Typography sx={{fontWeight: 700}}>No references for this interaction</Typography>
          <Typography color="text.secondary">
            Select another interaction on the left to see its retrieval output.
          </Typography>
        </Box>
      ) : (
        <Stack spacing={2} sx={{flex: 1, overflow: "hidden", p: 2}}>
          {/* List (scrollable) */}
          <Paper variant="outlined" sx={{p: 0, overflow: "auto", maxHeight: "clamp(140px, 32%, 240px)", minHeight: 120}}>
            <List dense disablePadding>
              {refIds.map((id) => {
                const ref = refById[id];
                const err = errById[id];
                const label = ref ? `${ref.type} — p. ${pagesFromBBoxes(ref)}` : err ? "Failed to load" : "Loading…";

                return (
                  <ListItemButton key={id} selected={id === selectedRefId} onClick={() => setSelectedRefId(id)}>
                    <ListItemText
                      primary={label}
                      secondary={id}
                      primaryTypographyProps={{noWrap: true}}
                      secondaryTypographyProps={{noWrap: true}}
                    />
                  </ListItemButton>
                );
              })}
            </List>
          </Paper>

          {/* Detail (scrollable) */}
          <Paper variant="outlined" sx={{p: 1.5, flex: 1, overflow: "auto"}}>
            {!selectedRefId ? (
              <Typography color="text.secondary">Select a reference.</Typography>
            ) : errById[selectedRefId] ? (
              <Alert severity="error">{errById[selectedRefId]}</Alert>
            ) : !selectedRef ? (
              <Typography color="text.secondary">Loading reference…</Typography>
            ) : (
              <Stack spacing={1}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{flexWrap: "wrap"}}>
                  <Chip label={selectedRef.type} size="small"/>
                  <Chip
                    label={`Guideline: ${normalizeObjectId((selectedRef as any).guideline_id)}`}
                    size="small"
                    variant="outlined"
                  />
                  <Chip label={`Pages: ${pagesFromBBoxes(selectedRef)}`} size="small" variant="outlined"/>
                </Stack>

                <Typography variant="subtitle2" sx={{fontWeight: 800}}>
                  Document path
                </Typography>
                <Typography color="text.secondary" sx={{whiteSpace: "pre-wrap"}}>
                  {hierarchyPath(selectedRef)}
                </Typography>

                {selectedRef.note ? (
                  <>
                    <Typography variant="subtitle2" sx={{fontWeight: 800}}>
                      Note
                    </Typography>
                    <Typography sx={{whiteSpace: "pre-wrap"}}>{selectedRef.note}</Typography>
                  </>
                ) : null}

                <Divider/>

                {(() => {
                  const {title, body} = renderMainContent(selectedRef);
                  return (
                    <>
                      <Typography variant="subtitle2" sx={{fontWeight: 800}}>
                        {title}
                      </Typography>
                      <Typography sx={{whiteSpace: "pre-wrap"}} color={body?.trim() ? "text.primary" : "text.secondary"}>
                        {body?.trim() ? body : "—"}
                      </Typography>
                    </>
                  );
                })()}
              </Stack>
            )}
          </Paper>
        </Stack>
      )}
    </Paper>
  );
}
