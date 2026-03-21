import {useEffect, useMemo, useState} from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import {
  QUESTION_SUB_CLASS_OPTIONS,
  type BoundingBox,
  type QuestionEntry,
  type QuestionEntryCreateRequest,
  type QuestionSubClass,
  type QuestionSuperClass,
} from "../../api/evaluation";
import {type FindBoundingBoxesArgs, type GuidelineEntry} from "../../api/references";
import {normalizeObjectId} from "../../api/system";
import QuestionSnippetEditorCard from "./QuestionSnippetEditorCard";
import {createDraftFromSnippet, createEmptySnippet, getDefaultSubClass, type ManualSnippetDraft} from "./questionEntryTypes";

type QuestionEntryDialogProps = {
  open: boolean;
  mode: "create" | "edit";
  questionGroupId: string;
  guidelines: GuidelineEntry[];
  initialQuestion?: QuestionEntry | null;
  onClose: () => void;
  onSubmit: (payload: QuestionEntryCreateRequest) => Promise<void>;
  onFindBoundingBoxes: (args: FindBoundingBoxesArgs) => Promise<BoundingBox[]>;
};

function buildInitialState(guidelines: GuidelineEntry[], initialQuestion?: QuestionEntry | null) {
  if (initialQuestion) {
    return {
      question: initialQuestion.question,
      correctAnswer: initialQuestion.correct_answer || "",
      note: initialQuestion.note || "",
      superClass: initialQuestion.classification.super_class as QuestionSuperClass,
      subClass: initialQuestion.classification.sub_class as QuestionSubClass,
      snippets: initialQuestion.expected_retrieval?.length
        ? initialQuestion.expected_retrieval.map((snippet) => createDraftFromSnippet(snippet, guidelines))
        : [createEmptySnippet()] as ManualSnippetDraft[],
    };
  }
  return {
    question: "",
    correctAnswer: "",
    note: "",
    superClass: "simple" as QuestionSuperClass,
    subClass: getDefaultSubClass("simple"),
    snippets: [createEmptySnippet()] as ManualSnippetDraft[],
  };
}

export default function QuestionEntryDialog({
  open,
  mode,
  questionGroupId,
  guidelines,
  initialQuestion,
  onClose,
  onSubmit,
  onFindBoundingBoxes,
}: QuestionEntryDialogProps) {
  const [question, setQuestion] = useState("");
  const [correctAnswer, setCorrectAnswer] = useState("");
  const [note, setNote] = useState("");
  const [superClass, setSuperClass] = useState<QuestionSuperClass>("simple");
  const [subClass, setSubClass] = useState<QuestionSubClass>(getDefaultSubClass("simple"));
  const [snippetDrafts, setSnippetDrafts] = useState<ManualSnippetDraft[]>([createEmptySnippet()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentSubClassOptions = useMemo(() => QUESTION_SUB_CLASS_OPTIONS[superClass], [superClass]);

  useEffect(() => {
    if (!open) return;
    const initial = buildInitialState(guidelines, initialQuestion);
    setQuestion(initial.question);
    setCorrectAnswer(initial.correctAnswer);
    setNote(initial.note);
    setSuperClass(initial.superClass);
    setSubClass(initial.subClass);
    setSnippetDrafts(initial.snippets);
    setError(null);
    setSaving(false);
  }, [open, guidelines, initialQuestion]);

  function updateSnippetDraft(index: number, patch: Partial<ManualSnippetDraft>) {
    setSnippetDrafts((drafts) =>
      drafts.map((draft, draftIndex) => {
        if (draftIndex !== index) return draft;
        const next = {...draft, ...patch};
        if (patch.guidelineId !== undefined) {
          const guideline = guidelines.find((entry) => normalizeObjectId(entry._id) === patch.guidelineId);
          if (guideline) {
            next.guidelineSource = guideline.download_information?.url || "";
            next.guidelineTitle = guideline.title;
          } else if (!patch.guidelineId) {
            next.guidelineSource = "";
            next.guidelineTitle = "";
          }
        }
        return next;
      }),
    );
  }

  function addSnippetDraft() {
    setSnippetDrafts((drafts) => [...drafts, createEmptySnippet()]);
  }

  function removeSnippetDraft(index: number) {
    setSnippetDrafts((drafts) => drafts.filter((_, draftIndex) => draftIndex !== index));
  }

  async function handleFindBoxes(index: number) {
    const draft = snippetDrafts[index];
    if (!draft.guidelineId || !draft.retrievalText.trim()) return;
    try {
      setError(null);
      const boxes = await onFindBoundingBoxes({
        guideline_id: draft.guidelineId,
        text: draft.retrievalText.trim(),
        start_page: draft.startPage ? Number(draft.startPage) : null,
        end_page: draft.endPage ? Number(draft.endPage) : null,
      });
      updateSnippetDraft(index, {boundingBoxesJson: JSON.stringify(boxes, null, 2)});
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  function parseSnippets() {
    return snippetDrafts
      .filter((draft) =>
        Boolean(
          draft.guidelineSource.trim() ||
          draft.guidelineTitle.trim() ||
          draft.referenceType ||
          draft.retrievalText.trim() ||
          draft.boundingBoxesJson.trim(),
        ),
      )
      .map((draft) => {
        const boundingBoxes = draft.boundingBoxesJson.trim()
          ? JSON.parse(draft.boundingBoxesJson) as BoundingBox[]
          : [];
        return {
          guideline_source: draft.guidelineSource.trim() || null,
          guideline_title: draft.guidelineTitle.trim() || null,
          reference_type: draft.referenceType || null,
          retrieval_text: draft.retrievalText.trim(),
          bounding_boxes: boundingBoxes,
        };
      });
  }

  async function handleSubmit() {
    if (!questionGroupId || !question.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        question_group_id: questionGroupId,
        question: question.trim(),
        classification: {
          super_class: superClass,
          sub_class: subClass,
        },
        correct_answer: correctAnswer.trim() || null,
        note: note.trim() || null,
        expected_retrieval: parseSnippets(),
      });
      onClose();
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setSaving(false);
    }
  }

  const dialogTitle = mode === "edit" ? "Edit question entry" : "Create question entry";
  const dialogDescription = mode === "edit"
    ? "Update question text, classification, answer, and retrieval expectations for this dataset entry."
    : "Build evaluation questions directly in the UI with guided question-type selection and existing guideline choices.";
  const submitLabel = mode === "edit" ? "Save changes" : "Create question entry";

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{dialogTitle}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <Alert severity="info">
            {dialogDescription}
          </Alert>
          <TextField
            label="Question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            multiline
            minRows={2}
            fullWidth
          />
          <Stack direction={{xs: "column", md: "row"}} spacing={2}>
            <TextField
              select
              fullWidth
              label="Super class"
              value={superClass}
              onChange={(e) => {
                const nextSuper = e.target.value as QuestionSuperClass;
                setSuperClass(nextSuper);
                setSubClass(getDefaultSubClass(nextSuper));
              }}
            >
              <MenuItem value="simple">Simple</MenuItem>
              <MenuItem value="complex">Complex</MenuItem>
              <MenuItem value="negative">Negative</MenuItem>
            </TextField>
            <TextField
              select
              fullWidth
              label="Sub class"
              value={subClass}
              onChange={(e) => setSubClass(e.target.value as QuestionSubClass)}
            >
              {currentSubClassOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <TextField
            label="Correct answer"
            value={correctAnswer}
            onChange={(e) => setCorrectAnswer(e.target.value)}
            multiline
            minRows={3}
            fullWidth
          />
          <TextField
            label="Comment / note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            multiline
            minRows={2}
            fullWidth
          />

          <Divider />

          <Stack spacing={2}>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="subtitle1" sx={{fontWeight: 700}}>
                Expected retrieval snippets
              </Typography>
              <Button variant="outlined" onClick={addSnippetDraft} sx={{textTransform: "none"}}>
                Add snippet
              </Button>
            </Stack>

            {snippetDrafts.map((draft, index) => (
              <QuestionSnippetEditorCard
                key={index}
                index={index}
                draft={draft}
                guidelines={guidelines}
                canRemove={snippetDrafts.length > 1}
                onChange={updateSnippetDraft}
                onRemove={removeSnippetDraft}
                onFindBoundingBoxes={handleFindBoxes}
              />
            ))}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={{textTransform: "none"}}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={() => void handleSubmit()}
          disabled={!questionGroupId || !question.trim() || saving}
          sx={{textTransform: "none"}}
        >
          {submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
