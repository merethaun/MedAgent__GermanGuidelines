import {useEffect, useMemo, useRef} from "react";
import {Box, Card, CardContent, Chip, List, ListItemButton, ListItemText, Stack, Typography} from "@mui/material";
import {type GuidelineHierarchyEntry, type GuidelineReference} from "../../api/references";
import {normalizeObjectId} from "../../api/system";

type Props = {
  references: GuidelineReference[];
  selectedReferenceId: string;
  onSelect: (referenceId: string) => void;
};

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

export default function ReferenceList({references, selectedReferenceId, onSelect}: Props) {
  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const sortedReferences = useMemo(() => {
    return [...references].sort((a, b) => {
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
  }, [references]);

  useEffect(() => {
    if (!selectedReferenceId) return;

    const selectedElement = itemRefs.current[selectedReferenceId];
    if (!selectedElement) return;

    requestAnimationFrame(() => {
      selectedElement.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    });
  }, [selectedReferenceId, sortedReferences]);

  return (
    <Card
      variant="outlined"
      sx={{
        height: "100%",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <CardContent
        sx={{
          p: 0,
          height: "100%",
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box sx={{p: 2, pb: 1, flex: "0 0 auto"}}>
          <Typography variant="h6" sx={{fontWeight: 800}}>
            References
          </Typography>
        </Box>

        {sortedReferences.length === 0 ? (
          <Box sx={{px: 2, pb: 2}}>
            <Typography sx={{fontWeight: 700}}>No references yet</Typography>
            <Typography color="text.secondary">
              Create the first reference from text.
            </Typography>
          </Box>
        ) : (
          <Box
            sx={{
              flex: 1,
              minHeight: 0,
              overflowY: "auto",
              overflowX: "hidden",
              px: 0,
              pb: 1,
            }}
          >
            <List dense sx={{pt: 0}}>
              {sortedReferences.map((reference) => {
                const referenceId = normalizeObjectId(reference._id ?? "");
                const selected = referenceId === selectedReferenceId;
                const firstPage = reference.bboxs?.[0]?.page;
                const hierarchyPath = getHierarchyPath(reference.document_hierarchy);

                return (
                  <ListItemButton
                    key={referenceId}
                    ref={(node) => {
                      itemRefs.current[referenceId] = node;
                    }}
                    selected={selected}
                    onClick={() => onSelect(referenceId)}
                    alignItems="flex-start"
                  >
                    <ListItemText
                      primary={(
                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                          <Chip label={reference.type} size="small"/>
                          {hierarchyPath ? (
                            <Chip label={`order ${hierarchyPath}`} size="small" variant="outlined"/>
                          ) : null}
                          {firstPage != null ? (
                            <Chip label={`p. ${firstPage}`} size="small" variant="outlined"/>
                          ) : null}
                        </Stack>
                      )}
                      secondary={(
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{
                            mt: 0.75,
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {getReferenceTitle(reference)}
                        </Typography>
                      )}
                    />
                  </ListItemButton>
                );
              })}
            </List>
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
