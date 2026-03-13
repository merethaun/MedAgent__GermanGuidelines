import {Fragment, type ReactNode, useMemo} from "react";
import {
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemText,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import {type GuidelineEntry, type GuidelineHierarchyEntry, type GuidelineReference} from "../../api/references";
import {normalizeObjectId} from "../../api/system";

type Props = {
  reference: GuidelineReference | null;
  guideline?: GuidelineEntry | null;
  emptyStateText?: string;
  pdfSlot?: ReactNode;
};

function pagesFromBBoxes(reference?: GuidelineReference | null): string {
  const pages = (reference?.bboxs ?? [])
    .map((bbox) => bbox.page)
    .filter((page): page is number => typeof page === "number" && Number.isFinite(page));

  if (!pages.length) return "-";

  return Array.from(new Set(pages))
    .sort((a, b) => a - b)
    .join(", ");
}

function getHierarchyLabel(entries?: GuidelineHierarchyEntry[]): string {
  const path = (entries ?? [])
    .slice()
    .sort((a, b) => (a.heading_level ?? 0) - (b.heading_level ?? 0))
    .map((entry) => {
      const prefix = entry.heading_number?.trim();
      const title = entry.title?.trim();
      return [prefix, title].filter(Boolean).join(" ");
    })
    .filter(Boolean);

  return path.length ? path.join(" > ") : "-";
}

function getReferenceHeading(reference: GuidelineReference): string {
  switch (reference.type) {
    case "image":
      return reference.caption?.trim() ? reference.caption : "Reference";
    case "table":
      return reference.caption?.trim() ? reference.caption : "Reference";
    case "recommendation":
      return reference.recommendation_title?.trim() ? reference.recommendation_title : "Reference";
    case "statement":
      return reference.statement_title?.trim() ? reference.statement_title : "Reference";
    case "metadata":
      return reference.metadata_type?.trim() ? reference.metadata_type : "Reference";
    default:
      return "";
  }
}

function getReferenceBody(reference: GuidelineReference): string {
  switch (reference.type) {
    case "text":
      return reference.contained_text ?? "";
    case "image":
      return reference.describing_text ?? "";
    case "table":
      return reference.table_markdown ?? reference.plain_text ?? "";
    case "recommendation":
      return reference.recommendation_content ?? "";
    case "statement":
      return reference.statement_content ?? "";
    case "metadata":
      return reference.metadata_content ?? "";
    default:
      return "";
  }
}

function renderTypeSpecificDetails(reference: GuidelineReference): ReactNode[] {
  switch (reference.type) {
    case "recommendation":
      return reference.recommendation_grade?.trim() ? [
        (
          <Box key="recommendation-grade">
            <Typography variant="body2" sx={{fontWeight: 700, mb: 0.75}}>
              Recommendation Level
            </Typography>
            <Typography sx={{whiteSpace: "pre-wrap"}}>{reference.recommendation_grade}</Typography>
          </Box>
        ),
      ] : [];
    case "statement":
      return reference.statement_consensus_grade?.trim() ? [
        (
          <Box key="statement-grade">
            <Typography variant="body2" sx={{fontWeight: 700, mb: 0.75}}>
              Consensus Level
            </Typography>
            <Typography sx={{whiteSpace: "pre-wrap"}}>{reference.statement_consensus_grade}</Typography>
          </Box>
        ),
      ] : [];
    case "image":
      return reference.caption?.trim() ? [
        (
          <Box key="image-caption">
            <Typography variant="body2" sx={{fontWeight: 700, mb: 0.75}}>
              Caption
            </Typography>
            <Typography sx={{whiteSpace: "pre-wrap"}}>{reference.caption}</Typography>
          </Box>
        ),
      ] : [];
    case "metadata":
      return reference.metadata_type?.trim() ? [
        (
          <Box key="metadata-type">
            <Typography variant="body2" sx={{fontWeight: 700, mb: 0.75}}>
              Metadata Type
            </Typography>
            <Typography sx={{whiteSpace: "pre-wrap"}}>{reference.metadata_type}</Typography>
          </Box>
        ),
      ] : [];
    default:
      return [];
  }
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim();
  const raw = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const withoutTrailing = raw.endsWith("|") ? raw.slice(0, -1) : raw;
  return withoutTrailing.split("|").map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line: string): boolean {
  return /^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/.test(line);
}

function isMarkdownTable(lines: string[], index: number): boolean {
  return index + 1 < lines.length && lines[index].includes("|") && isMarkdownTableSeparator(lines[index + 1]);
}

function renderMarkdown(content: string): ReactNode {
  const normalized = content
    .replace(/\r\n/g, "\n")
    .replace(/\\n/g, "\n")
    .trim();
  if (!normalized) {
    return <Typography color="text.secondary">-</Typography>;
  }

  const lines = normalized.split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  let key = 0;

  while (index < lines.length) {
    const current = lines[index];
    const trimmed = current.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (isMarkdownTable(lines, index)) {
      const header = splitTableRow(lines[index]);
      index += 2;
      const rows: string[][] = [];

      while (index < lines.length && lines[index].trim().includes("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }

      blocks.push(
        <TableContainer key={`table-${key++}`} sx={{border: "1px solid", borderColor: "divider", borderRadius: 1}}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {header.map((cell, cellIndex) => (
                  <TableCell key={`header-${cellIndex}`} sx={{fontWeight: 700}}>
                    {cell || " "}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, rowIndex) => (
                <TableRow key={`row-${rowIndex}`}>
                  {header.map((_, cellIndex) => (
                    <TableCell key={`cell-${rowIndex}-${cellIndex}`}>
                      {row[cellIndex] ?? ""}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>,
      );
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const depth = headingMatch[1].length;
      const variant = depth <= 2 ? "h6" : depth === 3 ? "subtitle1" : "subtitle2";
      blocks.push(
        <Typography key={`heading-${key++}`} variant={variant} sx={{fontWeight: 800}}>
          {headingMatch[2]}
        </Typography>,
      );
      index += 1;
      continue;
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
    const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (bulletMatch || orderedMatch) {
      const ordered = Boolean(orderedMatch);
      const items: string[] = [];

      while (index < lines.length) {
        const line = lines[index].trim();
        const match = ordered ? line.match(/^\d+\.\s+(.*)$/) : line.match(/^[-*]\s+(.*)$/);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }

      blocks.push(
        <List key={`list-${key++}`} dense sx={{py: 0}}>
          {items.map((item, itemIndex) => (
            <ListItem key={`item-${itemIndex}`} disableGutters sx={{display: "list-item", ml: 2, py: 0.25}}>
              <ListItemText
                primary={item}
                sx={{
                  m: 0,
                  "& .MuiListItemText-primary": {
                    typography: "body2",
                    whiteSpace: "pre-wrap",
                  },
                }}
              />
            </ListItem>
          ))}
        </List>,
      );
      continue;
    }

    const quoteMatch = trimmed.match(/^>\s?(.*)$/);
    if (quoteMatch) {
      const quoteLines: string[] = [];
      while (index < lines.length) {
        const line = lines[index].trim();
        const match = line.match(/^>\s?(.*)$/);
        if (!match) break;
        quoteLines.push(match[1]);
        index += 1;
      }

      blocks.push(
        <Box
          key={`quote-${key++}`}
          sx={{
            borderLeft: "3px solid",
            borderColor: "divider",
            pl: 1.5,
            color: "text.secondary",
          }}
        >
          <Typography sx={{whiteSpace: "pre-wrap"}}>{quoteLines.join("\n")}</Typography>
        </Box>,
      );
      continue;
    }

    if (trimmed.startsWith("```")) {
      index += 1;
      const codeLines: string[] = [];
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;

      blocks.push(
        <Box
          key={`code-${key++}`}
          component="pre"
          sx={{
            m: 0,
            p: 1.5,
            borderRadius: 1,
            bgcolor: "grey.100",
            overflowX: "auto",
            fontFamily: "monospace",
            fontSize: 13,
          }}
        >
          {codeLines.join("\n")}
        </Box>,
      );
      continue;
    }

    const paragraphLines: string[] = [current];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isMarkdownTable(lines, index)) {
      const line = lines[index].trim();
      if (
        /^(#{1,6})\s+/.test(line) ||
        /^[-*]\s+/.test(line) ||
        /^\d+\.\s+/.test(line) ||
        /^>\s?/.test(line) ||
        line.startsWith("```")
      ) {
        break;
      }
      paragraphLines.push(lines[index]);
      index += 1;
    }

    blocks.push(
      <Typography key={`p-${key++}`} sx={{whiteSpace: "pre-wrap"}}>
        {paragraphLines.join("\n")}
      </Typography>,
    );
  }

  return (
    <Stack spacing={1.5}>
      {blocks.map((block, blockIndex) => (
        <Fragment key={blockIndex}>{block}</Fragment>
      ))}
    </Stack>
  );
}

export default function ReferenceDetailView(props: Props) {
  const {
    reference,
    guideline = null,
    emptyStateText = "Select a reference to inspect it.",
    pdfSlot,
  } = props;

  const hierarchyLabel = useMemo(() => getHierarchyLabel(reference?.document_hierarchy), [reference]);
  const content = useMemo(() => (reference ? getReferenceBody(reference) : ""), [reference]);
  const extraDetails = useMemo(() => (reference ? renderTypeSpecificDetails(reference) : []), [reference]);

  return (
    <Card variant="outlined" sx={{height: "100%", minHeight: 0}}>
      <CardContent
        sx={{
          height: "100%",
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          p: 0,
        }}
      >
        <Box sx={{p: 2, pb: 1.25}}>
          <Typography variant="subtitle1" sx={{fontWeight: 800}}>
            {getReferenceHeading(reference ?? ({} as GuidelineReference))
              ? `Details: "${getReferenceHeading(reference ?? ({} as GuidelineReference))}"`
              : "Details"}
          </Typography>
        </Box>

        <Divider/>

        <Box sx={{flex: 1, minHeight: 0, overflow: "auto", p: 2}}>
          {!reference ? (
            <Typography color="text.secondary">{emptyStateText}</Typography>
          ) : (
            <Stack spacing={2}>
              <Stack spacing={1}>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip label={`p. ${pagesFromBBoxes(reference)}`} size="small" variant="outlined"/>
                  <Chip
                    label={`Guideline: ${guideline?.title ?? normalizeObjectId(reference.guideline_id)}`}
                    size="small"
                    variant="outlined"
                  />
                </Stack>
              </Stack>

              <Box>
                <Typography variant="body2" sx={{fontWeight: 700, mb: 0.75}}>
                  Document Path
                </Typography>
                <Typography color="text.secondary" sx={{whiteSpace: "pre-wrap"}}>
                  {hierarchyLabel}
                </Typography>
              </Box>

              {reference.note?.trim() ? (
                <Box>
                  <Typography variant="subtitle2" sx={{fontWeight: 800, mb: 0.75}}>
                    Note
                  </Typography>
                  <Typography sx={{whiteSpace: "pre-wrap"}}>{reference.note}</Typography>
                </Box>
              ) : null}

              <Divider/>

              <Box>
                <Typography variant="body2" sx={{fontWeight: 700, mb: 1}}>
                  Content
                </Typography>
                {renderMarkdown(content)}
              </Box>

              {extraDetails.length ? (
                <>
                  <Divider/>
                  <Stack spacing={2}>
                    {extraDetails}
                  </Stack>
                </>
              ) : null}

              {pdfSlot ? (
                <>
                  <Divider/>
                  <Box sx={{minHeight: 320}}>
                    {pdfSlot}
                  </Box>
                </>
              ) : null}
            </Stack>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}
