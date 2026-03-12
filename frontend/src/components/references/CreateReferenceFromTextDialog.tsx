import {useState} from "react";
import {Alert, Box, Button, Chip, Stack, TextField, Typography,} from "@mui/material";
import {type BoundingBox, type GuidelineTextReference, useReferenceApi,} from "../../api/references";

type Props = {
  guidelineId: string;
  referenceGroupId: string;
  onCancel: () => void;
  onCreated: () => void | Promise<void>;
};

export default function CreateReferenceFromTextDialog({
                                                        guidelineId,
                                                        referenceGroupId,
                                                        onCancel,
                                                        onCreated,
                                                      }: Props) {
  const {findBoundingBoxes, createReference} = useReferenceApi();

  const [searchText, setSearchText] = useState("");
  const [containedText, setContainedText] = useState("");
  const [note, setNote] = useState("");
  const [startPage, setStartPage] = useState("");
  const [endPage, setEndPage] = useState("");

  const [bboxs, setBboxs] = useState<BoundingBox[]>([]);
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
      setBboxs(found ?? []);
      if (!containedText.trim()) {
        setContainedText(text);
      }
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
      setBboxs([]);
    } finally {
      setLoadingBoxes(false);
    }
  }

  async function handleCreate() {
    if (!containedText.trim()) {
      setError("Please enter the contained text.");
      return;
    }
    if (bboxs.length === 0) {
      setError("Please find at least one bounding box first.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const payload: GuidelineTextReference = {
        guideline_id: guidelineId,
        reference_group_id: referenceGroupId,
        type: "text",
        contained_text: containedText.trim(),
        bboxs,
        note: note.trim() || null,
        created_automatically: false,
      };

      await createReference(payload);
      await onCreated();
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  }

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

      <TextField
        label="Contained text"
        value={containedText}
        onChange={(e) => setContainedText(e.target.value)}
        fullWidth
        multiline
        minRows={3}
      />

      <TextField
        label="Note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        fullWidth
        multiline
        minRows={2}
      />

      <Box sx={{display: "flex", justifyContent: "flex-end", gap: 1}}>
        <Button onClick={onCancel} disabled={saving || loadingBoxes} sx={{textTransform: "none"}}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleCreate}
          disabled={saving || bboxs.length === 0 || !containedText.trim()}
          sx={{textTransform: "none"}}
        >
          Create
        </Button>
      </Box>
    </Stack>
  );
}