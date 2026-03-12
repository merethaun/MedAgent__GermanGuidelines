import {useState} from "react";
import {Alert, Box, Button, Chip, Stack, TextField, Typography} from "@mui/material";
import {
  type BoundingBox,
  type GuidelineImageReference,
  type GuidelineMetadataReference,
  type GuidelineRecommendationReference,
  type GuidelineReference,
  type GuidelineReferenceType,
  type GuidelineStatementReference,
  type GuidelineTableReference,
  type GuidelineTextReference,
  useReferenceApi,
} from "../../api/references";
import ReferenceDetailEditor from "./ReferenceDetailEditor";

type Props = {
  guidelineId: string;
  referenceGroupId: string;
  onCancel: () => void;
  onCreated: () => void | Promise<void>;
};

function extractPrimaryText(reference: GuidelineReference): string {
  switch (reference.type) {
    case "text":
      return reference.contained_text ?? "";
    case "image":
      return reference.describing_text ?? reference.caption ?? "";
    case "table":
      return reference.plain_text ?? reference.caption ?? reference.table_markdown ?? "";
    case "recommendation":
      return reference.recommendation_content ?? reference.recommendation_title ?? "";
    case "statement":
      return reference.statement_content ?? reference.statement_title ?? "";
    case "metadata":
      return reference.metadata_content ?? reference.metadata_type ?? "";
    default:
      return "";
  }
}

function createDraftReference(args: {
  guidelineId: string;
  referenceGroupId: string;
  type: GuidelineReferenceType;
  bboxs?: BoundingBox[];
  note?: string | null;
  documentHierarchy?: GuidelineReference["document_hierarchy"];
  seedText?: string;
}): GuidelineReference {
  const base = {
    guideline_id: args.guidelineId,
    reference_group_id: args.referenceGroupId,
    type: args.type,
    bboxs: args.bboxs ?? [],
    note: args.note ?? null,
    document_hierarchy: args.documentHierarchy ?? [],
    created_automatically: false,
  };
  const seedText = args.seedText ?? "";

  switch (args.type) {
    case "text":
      return {
        ...base,
        type: "text",
        contained_text: seedText,
      } satisfies GuidelineTextReference;
    case "image":
      return {
        ...base,
        type: "image",
        caption: "",
        describing_text: seedText,
      } satisfies GuidelineImageReference;
    case "table":
      return {
        ...base,
        type: "table",
        caption: "",
        plain_text: seedText,
        table_markdown: "",
      } satisfies GuidelineTableReference;
    case "recommendation":
      return {
        ...base,
        type: "recommendation",
        recommendation_title: null,
        recommendation_content: seedText,
        recommendation_grade: "",
      } satisfies GuidelineRecommendationReference;
    case "statement":
      return {
        ...base,
        type: "statement",
        statement_title: null,
        statement_content: seedText,
        statement_consensus_grade: "",
      } satisfies GuidelineStatementReference;
    case "metadata":
      return {
        ...base,
        type: "metadata",
        metadata_type: "",
        metadata_content: seedText,
      } satisfies GuidelineMetadataReference;
  }
}

export default function CreateReferenceFromTextDialog({
                                                        guidelineId,
                                                        referenceGroupId,
                                                        onCancel,
                                                        onCreated,
                                                      }: Props) {
  const {findBoundingBoxes, createReference} = useReferenceApi();

  const [searchText, setSearchText] = useState("");
  const [startPage, setStartPage] = useState("");
  const [endPage, setEndPage] = useState("");
  const [draftReference, setDraftReference] = useState<GuidelineReference>(() =>
    createDraftReference({
      guidelineId,
      referenceGroupId,
      type: "text",
    }),
  );

  const [loadingBoxes, setLoadingBoxes] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFindBoxes() {
    const text = searchText.trim();
    if (!text) {
      setError("Please enter the text to search for.");
      return;
    }

    setLoadingBoxes(true);
    setError(null);

    try {
      const found = await findBoundingBoxes({
        guideline_id: guidelineId,
        text,
        start_page: startPage.trim() ? Number(startPage) : null,
        end_page: endPage.trim() ? Number(endPage) : null,
      });

      setDraftReference((current) =>
        createDraftReference({
          guidelineId,
          referenceGroupId,
          type: current.type,
          bboxs: found ?? [],
          note: current.note ?? null,
          documentHierarchy: current.document_hierarchy,
          seedText: extractPrimaryText(current).trim() || text,
        }),
      );
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
      setDraftReference((current) => ({
        ...current,
        bboxs: [],
      }));
    } finally {
      setLoadingBoxes(false);
    }
  }

  function handleTypeChange(referenceType: GuidelineReferenceType) {
    setDraftReference((current) =>
      createDraftReference({
        guidelineId,
        referenceGroupId,
        type: referenceType,
        bboxs: current.bboxs,
        note: current.note ?? null,
        documentHierarchy: current.document_hierarchy,
        seedText: extractPrimaryText(current).trim() || searchText.trim(),
      }),
    );
  }

  async function handleCreate(patch: Record<string, unknown>) {
    const payload = {
      ...draftReference,
      ...patch,
      guideline_id: guidelineId,
      reference_group_id: referenceGroupId,
      type: draftReference.type,
      created_automatically: false,
    } as GuidelineReference;

    if ((payload.bboxs ?? []).length === 0) {
      setError("Please find at least one bounding box first.");
      return;
    }

    if (payload.type === "text" && !payload.contained_text.trim()) {
      setError("Please enter the contained text.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await createReference(payload);
      await onCreated();
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  }

  const bboxs = draftReference.bboxs ?? [];

  return (
    <Stack spacing={2}>
      {error && <Alert severity="error">{error}</Alert>}

      <TextField
        label="Search text in PDF"
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
        fullWidth
        multiline
        minRows={3}
      />

      <Stack direction="row" spacing={2}>
        <TextField
          label="Start page"
          value={startPage}
          onChange={(e) => setStartPage(e.target.value)}
          sx={{maxWidth: 160}}
        />
        <TextField
          label="End page"
          value={endPage}
          onChange={(e) => setEndPage(e.target.value)}
          sx={{maxWidth: 160}}
        />
        <Box sx={{display: "flex", alignItems: "center"}}>
          <Button
            variant="outlined"
            onClick={handleFindBoxes}
            disabled={loadingBoxes || !searchText.trim()}
            sx={{textTransform: "none"}}
          >
            Find bounding boxes
          </Button>
        </Box>
      </Stack>

      <Box>
        <Typography sx={{fontWeight: 700}}>Found bounding boxes</Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{mt: 1}}>
          <Chip label={`${bboxs.length} match(es)`}/>
          {bboxs.slice(0, 8).map((b, idx) => (
            <Chip key={`${b.page}-${idx}`} label={`p.${b.page}`} variant="outlined"/>
          ))}
        </Stack>
      </Box>

      <ReferenceDetailEditor
        reference={draftReference}
        saving={saving || loadingBoxes}
        onSave={handleCreate}
        mode="create"
        saveLabel="Create"
        allowTypeChange
        onTypeChange={handleTypeChange}
        emptyStateText="Search for text to create a reference."
      />

      <Box sx={{display: "flex", justifyContent: "flex-end", gap: 1}}>
        <Button onClick={onCancel} disabled={saving || loadingBoxes} sx={{textTransform: "none"}}>
          Cancel
        </Button>
      </Box>
    </Stack>
  );
}
