import {Button, Card, CardContent, MenuItem, Stack, TextField, Typography,} from "@mui/material";

import {type GuidelineEntry} from "../../api/references";
import {normalizeObjectId} from "../../api/system";
import {type ExpectedRetrievalSnippet} from "../../api/evaluation";
import {formatGuidelineLabel, type ManualSnippetDraft} from "./questionEntryTypes";

const REFERENCE_TYPE_OPTIONS = [
  {value: "text", label: "Text"},
  {value: "recommendation", label: "Recommendation"},
  {value: "table", label: "Table"},
  {value: "statement", label: "Statement"},
  {value: "image", label: "Image"},
  {value: "metadata", label: "Metadata"},
] as const;

type QuestionSnippetEditorCardProps = {
  index: number;
  draft: ManualSnippetDraft;
  guidelines: GuidelineEntry[];
  canRemove: boolean;
  onChange: (index: number, patch: Partial<ManualSnippetDraft>) => void;
  onRemove: (index: number) => void;
  onFindBoundingBoxes: (index: number) => Promise<void>;
};

export default function QuestionSnippetEditorCard({
                                                    index,
                                                    draft,
                                                    guidelines,
                                                    canRemove,
                                                    onChange,
                                                    onRemove,
                                                    onFindBoundingBoxes,
                                                  }: QuestionSnippetEditorCardProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Typography sx={{fontWeight: 700}}>
              Snippet {index + 1}
            </Typography>
            <Button
              color="error"
              onClick={() => onRemove(index)}
              disabled={!canRemove}
              sx={{textTransform: "none"}}
            >
              Remove
            </Button>
          </Stack>

          <TextField
            select
            fullWidth
            label="Guideline"
            value={draft.guidelineId}
            onChange={(e) => onChange(index, {guidelineId: e.target.value})}
          >
            <MenuItem value="">No guideline selected</MenuItem>
            {guidelines.map((guideline) => (
              <MenuItem key={normalizeObjectId(guideline._id)} value={normalizeObjectId(guideline._id)}>
                {formatGuidelineLabel(guideline)}
              </MenuItem>
            ))}
          </TextField>

          <Stack direction={{xs: "column", md: "row"}} spacing={2}>
            <TextField
              label="Guideline source URL"
              value={draft.guidelineSource}
              onChange={(e) => onChange(index, {guidelineSource: e.target.value})}
              fullWidth
            />
            <TextField
              label="Guideline title"
              value={draft.guidelineTitle}
              onChange={(e) => onChange(index, {guidelineTitle: e.target.value})}
              fullWidth
            />
          </Stack>

          <TextField
            select
            fullWidth
            label="Reference type"
            value={draft.referenceType}
            onChange={(e) => onChange(index, {referenceType: e.target.value as "" | ExpectedRetrievalSnippet["reference_type"]})}
          >
            <MenuItem value="">No reference type</MenuItem>
            {REFERENCE_TYPE_OPTIONS.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Retrieval text"
            value={draft.retrievalText}
            onChange={(e) => onChange(index, {retrievalText: e.target.value})}
            multiline
            minRows={3}
            fullWidth
          />

          <Stack direction={{xs: "column", md: "row"}} spacing={2}>
            <TextField
              label="Start page hint"
              value={draft.startPage}
              onChange={(e) => onChange(index, {startPage: e.target.value})}
              fullWidth
            />
            <TextField
              label="End page hint"
              value={draft.endPage}
              onChange={(e) => onChange(index, {endPage: e.target.value})}
              fullWidth
            />
            <Button
              variant="outlined"
              onClick={() => void onFindBoundingBoxes(index)}
              disabled={!draft.guidelineId || !draft.retrievalText.trim()}
              sx={{textTransform: "none", alignSelf: {md: "center"}}}
              fullWidth
            >
              Find bounding boxes
            </Button>
          </Stack>

          <TextField
            label="Bounding boxes JSON"
            value={draft.boundingBoxesJson}
            onChange={(e) => onChange(index, {boundingBoxesJson: e.target.value})}
            multiline
            minRows={4}
            helperText="Stores the same page + positions structure as the guideline references."
            fullWidth
          />
        </Stack>
      </CardContent>
    </Card>
  );
}
