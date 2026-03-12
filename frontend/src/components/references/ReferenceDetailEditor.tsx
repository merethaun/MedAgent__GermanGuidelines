import {useEffect, useMemo, useState} from "react";
import {Alert, Box, Button, Card, CardContent, Divider, MenuItem, Stack, TextField, Typography} from "@mui/material";
import {
  type BoundingBox,
  type GuidelineHierarchyEntry,
  type GuidelineReference,
  type GuidelineReferenceType,
} from "../../api/references";
import {normalizeObjectId} from "../../api/system";

type Props = {
  reference: GuidelineReference | null;
  saving?: boolean;
  onSave: (patch: Record<string, unknown>) => void | Promise<void>;
  onDelete?: (referenceId: string) => void | Promise<void>;
  mode?: "edit" | "create";
  saveLabel?: string;
  emptyStateText?: string;
  allowTypeChange?: boolean;
  onTypeChange?: (referenceType: GuidelineReferenceType) => void;
};

type HierarchyRowDraft = {
  title: string;
  heading_level: number;
  heading_number: string;
  order: string;
};

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? [], null, 2);
}

function normalizeHierarchyRows(rows: HierarchyRowDraft[]): HierarchyRowDraft[] {
  return rows.map((row, index) => ({
    ...row,
    heading_level: index,
  }));
}

function toHierarchyDraft(entries?: GuidelineHierarchyEntry[]): HierarchyRowDraft[] {
  const rows = (entries ?? []).map((entry) => ({
    title: entry.title ?? "",
    heading_level: entry.heading_level ?? 0,
    heading_number: entry.heading_number ?? "",
    order: String(entry.order ?? 0),
  }));

  return normalizeHierarchyRows(rows);
}

function toHierarchyEntries(rows: HierarchyRowDraft[]): GuidelineHierarchyEntry[] {
  return normalizeHierarchyRows(rows).map((row) => {
    const order = Number(row.order);

    return {
      title: row.title,
      heading_level: row.heading_level,
      heading_number: row.heading_number,
      order: Number.isFinite(order) ? order : 0,
    };
  });
}

function getHierarchyPath(rows: HierarchyRowDraft[]): string | null {
  if (!rows.length) return null;

  return rows
    .map((row) => {
      const value = Number(row.order);
      return Number.isFinite(value) ? String(value) : "0";
    })
    .join(".");
}

function parseBoundingBoxes(value: string): BoundingBox[] | null {
  try {
    const parsed = JSON.parse(value || "[]") as unknown;
    if (!Array.isArray(parsed)) return null;
    return parsed as BoundingBox[];
  } catch {
    return null;
  }
}

export default function ReferenceDetailEditor({
                                                reference,
                                                saving = false,
                                                onSave,
                                                onDelete,
                                                mode = "edit",
                                                saveLabel,
                                                emptyStateText,
                                                allowTypeChange = false,
                                                onTypeChange,
                                              }: Props) {
  const [note, setNote] = useState("");
  const [bboxJson, setBboxJson] = useState("[]");
  const [fieldA, setFieldA] = useState("");
  const [fieldB, setFieldB] = useState("");
  const [fieldC, setFieldC] = useState("");
  const [documentHierarchy, setDocumentHierarchy] = useState<HierarchyRowDraft[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reference) {
      setNote("");
      setBboxJson("[]");
      setFieldA("");
      setFieldB("");
      setFieldC("");
      setDocumentHierarchy([]);
      setError(null);
      return;
    }

    setNote(reference.note ?? "");
    setBboxJson(prettyJson(reference.bboxs ?? []));
    setDocumentHierarchy(toHierarchyDraft(reference.document_hierarchy));

    switch (reference.type) {
      case "text":
        setFieldA(reference.contained_text);
        setFieldB("");
        setFieldC("");
        break;
      case "image":
        setFieldA(reference.caption ?? "");
        setFieldB(reference.describing_text ?? "");
        setFieldC("");
        break;
      case "table":
        setFieldA(reference.caption ?? "");
        setFieldB(reference.plain_text ?? "");
        setFieldC(reference.table_markdown ?? "");
        break;
      case "recommendation":
        setFieldA(reference.recommendation_title ?? "");
        setFieldB(reference.recommendation_content);
        setFieldC(reference.recommendation_grade);
        break;
      case "statement":
        setFieldA(reference.statement_title ?? "");
        setFieldB(reference.statement_content);
        setFieldC(reference.statement_consensus_grade);
        break;
      case "metadata":
        setFieldA(reference.metadata_type);
        setFieldB(reference.metadata_content);
        setFieldC("");
        break;
      default:
        setFieldA("");
        setFieldB("");
        setFieldC("");
    }

    setError(null);
  }, [reference]);

  const referenceId = useMemo(
    () => (reference ? normalizeObjectId(reference._id ?? "") : ""),
    [reference],
  );
  const actionLabel = saveLabel ?? (mode === "create" ? "Create" : "Save");

  const hierarchyPath = useMemo(
    () => getHierarchyPath(documentHierarchy),
    [documentHierarchy],
  );

  function updateHierarchyRow(index: number, key: "title" | "heading_number" | "order", value: string) {
    setDocumentHierarchy((current) =>
      normalizeHierarchyRows(
        current.map((row, rowIndex) => (
          rowIndex === index ? {...row, [key]: value} : row
        )),
      ),
    );
  }

  function addHierarchyRow() {
    setDocumentHierarchy((current) =>
      normalizeHierarchyRows([
        ...current,
        {
          title: "",
          heading_level: current.length,
          heading_number: "",
          order: "0",
        },
      ]),
    );
  }

  function removeHierarchyRow(index: number) {
    setDocumentHierarchy((current) =>
      normalizeHierarchyRows(current.filter((_, rowIndex) => rowIndex !== index)),
    );
  }

  function moveHierarchyRow(index: number, direction: -1 | 1) {
    setDocumentHierarchy((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) return current;

      const next = [...current];
      const [moved] = next.splice(index, 1);
      next.splice(nextIndex, 0, moved);

      return normalizeHierarchyRows(next);
    });
  }

  async function handleSave() {
    if (!reference) return;

    setError(null);

    const parsedBboxs = parseBoundingBoxes(bboxJson);
    if (!parsedBboxs) {
      setError("Bounding boxes must be valid JSON.");
      return;
    }

    const patch: Record<string, unknown> = {
      note: note.trim() ? note : null,
      bboxs: parsedBboxs,
      document_hierarchy: toHierarchyEntries(documentHierarchy),
    };

    switch (reference.type) {
      case "text":
        patch.contained_text = fieldA;
        break;
      case "image":
        patch.caption = fieldA.trim() ? fieldA : undefined;
        patch.describing_text = fieldB.trim() ? fieldB : null;
        break;
      case "table":
        patch.caption = fieldA.trim() ? fieldA : undefined;
        patch.plain_text = fieldB.trim() ? fieldB : undefined;
        patch.table_markdown = fieldC.trim() ? fieldC : undefined;
        break;
      case "recommendation":
        patch.recommendation_title = fieldA.trim() ? fieldA : null;
        patch.recommendation_content = fieldB;
        patch.recommendation_grade = fieldC;
        break;
      case "statement":
        patch.statement_title = fieldA.trim() ? fieldA : null;
        patch.statement_content = fieldB;
        patch.statement_consensus_grade = fieldC;
        break;
      case "metadata":
        patch.metadata_type = fieldA;
        patch.metadata_content = fieldB;
        break;
    }

    await onSave(patch);
  }

  if (!reference) {
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
            height: "100%",
            minHeight: 0,
            overflowY: "auto",
          }}
        >
          <Typography variant="h6" sx={{fontWeight: 800}}>
            Reference details
          </Typography>
          <Typography color="text.secondary">
            {emptyStateText ?? "Select a reference to edit it."}
          </Typography>
        </CardContent>
      </Card>
    );
  }

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
          height: "100%",
          minHeight: 0,
          overflowY: "auto",
        }}
      >
        <Stack spacing={2}>
          <Box>
            <Typography variant="h6" sx={{fontWeight: 800}}>
              Reference details
            </Typography>
            {allowTypeChange ? (
              <TextField
                select
                label="Reference type"
                value={reference.type}
                onChange={(e) => onTypeChange?.(e.target.value as GuidelineReferenceType)}
                fullWidth
                sx={{mt: 1}}
              >
                <MenuItem value="text">Text</MenuItem>
                <MenuItem value="image">Image</MenuItem>
                <MenuItem value="table">Table</MenuItem>
                <MenuItem value="recommendation">Recommendation</MenuItem>
                <MenuItem value="statement">Statement</MenuItem>
                <MenuItem value="metadata">Metadata</MenuItem>
              </TextField>
            ) : (
              <Typography color="text.secondary">
                Type: {reference.type}
              </Typography>
            )}
          </Box>

          {error ? <Alert severity="error">{error}</Alert> : null}

          <TextField
            label="Note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />

          {reference.type === "text" ? (
            <TextField
              label="Contained text"
              value={fieldA}
              onChange={(e) => setFieldA(e.target.value)}
              fullWidth
              multiline
              minRows={4}
            />
          ) : null}

          {reference.type === "image" ? (
            <>
              <TextField
                label="Caption"
                value={fieldA}
                onChange={(e) => setFieldA(e.target.value)}
                fullWidth
              />
              <TextField
                label="Describing text"
                value={fieldB}
                onChange={(e) => setFieldB(e.target.value)}
                fullWidth
                multiline
                minRows={3}
              />
            </>
          ) : null}

          {reference.type === "table" ? (
            <>
              <TextField
                label="Caption"
                value={fieldA}
                onChange={(e) => setFieldA(e.target.value)}
                fullWidth
              />
              <TextField
                label="Plain text"
                value={fieldB}
                onChange={(e) => setFieldB(e.target.value)}
                fullWidth
                multiline
                minRows={3}
              />
              <TextField
                label="Table markdown"
                value={fieldC}
                onChange={(e) => setFieldC(e.target.value)}
                fullWidth
                multiline
                minRows={4}
              />
            </>
          ) : null}

          {reference.type === "recommendation" ? (
            <>
              <TextField
                label="Recommendation title"
                value={fieldA}
                onChange={(e) => setFieldA(e.target.value)}
                fullWidth
              />
              <TextField
                label="Recommendation content"
                value={fieldB}
                onChange={(e) => setFieldB(e.target.value)}
                fullWidth
                multiline
                minRows={4}
              />
              <TextField
                label="Recommendation grade"
                value={fieldC}
                onChange={(e) => setFieldC(e.target.value)}
                fullWidth
              />
            </>
          ) : null}

          {reference.type === "statement" ? (
            <>
              <TextField
                label="Statement title"
                value={fieldA}
                onChange={(e) => setFieldA(e.target.value)}
                fullWidth
              />
              <TextField
                label="Statement content"
                value={fieldB}
                onChange={(e) => setFieldB(e.target.value)}
                fullWidth
                multiline
                minRows={4}
              />
              <TextField
                label="Consensus grade"
                value={fieldC}
                onChange={(e) => setFieldC(e.target.value)}
                fullWidth
              />
            </>
          ) : null}

          {reference.type === "metadata" ? (
            <>
              <TextField
                label="Metadata type"
                value={fieldA}
                onChange={(e) => setFieldA(e.target.value)}
                fullWidth
              />
              <TextField
                label="Metadata content"
                value={fieldB}
                onChange={(e) => setFieldB(e.target.value)}
                fullWidth
                multiline
                minRows={3}
              />
            </>
          ) : null}
          <Divider sx={{my: 0.75}}/>
          <Box>
            <Box sx={{display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1}}>
              <Typography sx={{fontWeight: 700}}>
                Document hierarchy
              </Typography>
              <Button onClick={addHierarchyRow} sx={{textTransform: "none"}}>
                Add entry
              </Button>
            </Box>

            <Stack spacing={1.5}>
              {documentHierarchy.length === 0 ? (
                <Typography color="text.secondary">
                  No hierarchy entries stored for this reference.
                </Typography>
              ) : (
                documentHierarchy.map((row, index) => (
                  <Box
                    key={`${index}-${row.heading_level}-${row.order}-${row.heading_number}`}
                    sx={{
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1,
                      p: 1,
                    }}
                  >
                    <Stack spacing={1}>
                      <Stack direction={{xs: "column", sm: "row"}} spacing={1}>
                        <TextField
                          label="Level"
                          value={row.heading_level}
                          disabled
                          size="small"
                          sx={{
                            width: {sm: 90},
                            "& .MuiInputBase-input.Mui-disabled": {
                              WebkitTextFillColor: (theme) => theme.palette.text.primary,
                            },
                          }}
                        />
                        <TextField
                          label="Order"
                          type="number"
                          value={row.order}
                          onChange={(e) => updateHierarchyRow(index, "order", e.target.value)}
                          size="small"
                          sx={{width: {sm: 90}}}
                        />
                        <TextField
                          label="Heading number"
                          value={row.heading_number}
                          onChange={(e) => updateHierarchyRow(index, "heading_number", e.target.value)}
                          fullWidth
                          size="small"
                        />
                      </Stack>

                      <TextField
                        label="Title"
                        value={row.title}
                        onChange={(e) => updateHierarchyRow(index, "title", e.target.value)}
                        fullWidth
                        size="small"
                      />

                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "flex-end",
                          gap: 0.75,
                          flexWrap: "wrap",
                        }}
                      >
                        <Button
                          onClick={() => moveHierarchyRow(index, -1)}
                          disabled={index === 0}
                          size="small"
                          sx={{textTransform: "none", minWidth: 0, px: 1}}
                        >
                          Up
                        </Button>
                        <Button
                          onClick={() => moveHierarchyRow(index, 1)}
                          disabled={index === documentHierarchy.length - 1}
                          size="small"
                          sx={{textTransform: "none", minWidth: 0, px: 1}}
                        >
                          Down
                        </Button>
                        <Button
                          color="error"
                          onClick={() => removeHierarchyRow(index)}
                          size="small"
                          sx={{textTransform: "none", minWidth: 0, px: 1}}
                        >
                          Remove
                        </Button>
                      </Box>
                    </Stack>
                  </Box>
                ))
              )}
            </Stack>
          </Box>
          <Divider sx={{my: 0.75}}/>

          <TextField
            label="Bounding boxes JSON"
            value={bboxJson}
            onChange={(e) => setBboxJson(e.target.value)}
            fullWidth
            multiline
            minRows={8}
            sx={{
              "& .MuiInputBase-input": {
                color: "gray",
              },
            }}
          />

          <Box sx={{display: "flex", justifyContent: "space-between", gap: 1}}>
            {mode === "edit" ? (
              <Button
                color="error"
                variant="outlined"
                disabled={saving || !referenceId}
                onClick={() => onDelete?.(referenceId)}
                sx={{textTransform: "none"}}
              >
                Delete
              </Button>
            ) : (
              <Box />
            )}

            <Button
              variant="contained"
              disabled={saving}
              onClick={handleSave}
              sx={{textTransform: "none"}}
            >
              {actionLabel}
            </Button>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
