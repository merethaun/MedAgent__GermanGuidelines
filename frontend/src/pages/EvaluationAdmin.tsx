import {ChangeEvent, useEffect, useMemo, useState} from "react";
import {Alert, Box, Button, CircularProgress, Stack, Typography} from "@mui/material";

import {useAuth} from "../auth/AuthContext";
import {useChatApi} from "../api/chat";
import {
  type EvaluationRun,
  type EvaluationSample,
  type EvaluatorProfile,
  type LLMSettingsOverride,
  type QuestionEntry,
  type QuestionEntryCreateRequest,
  type QuestionGroup,
  useEvaluationApi,
} from "../api/evaluation";
import {type FindBoundingBoxesArgs, type GuidelineEntry, useReferenceApi} from "../api/references";
import {normalizeObjectId, type WorkflowConfig} from "../api/system";
import {
  BatchRunCard,
  QuestionDatasetCard,
  QuestionEntryDialog,
  QuestionGroupsCard,
  RunsCard,
  SamplesCard,
} from "../components/evaluation";

function downloadTextFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], {type: mimeType});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

const DEFAULT_RUNTIME_LLM_SETTINGS_JSON = `{
  "model": "gpt-4o-mini",
  "api_key": "TODO",
  "base_url": "https://api.openai.com/v1",
  "max_tokens": 256,
  "timeout_s": 60
}`;

export default function EvaluationAdminPage() {
  const auth = useAuth();
  const {listWorkflows} = useChatApi();
  const {listGuidelines, findBoundingBoxes} = useReferenceApi();
  const {
    listQuestionGroups,
    createQuestionGroup,
    createQuestion,
    updateQuestion,
    deleteQuestion,
    listQuestions,
    importQuestionsCsv,
    exportQuestionsCsv,
    listRuns,
    createRun,
    rerunRun,
    listSamples,
    rerunSample,
    listEvaluators,
  } = useEvaluationApi();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [questionEntryDialogOpen, setQuestionEntryDialogOpen] = useState(false);
  const [questionDialogMode, setQuestionDialogMode] = useState<"create" | "edit">("create");
  const [editingQuestion, setEditingQuestion] = useState<QuestionEntry | null>(null);
  const [deletingQuestionId, setDeletingQuestionId] = useState<string | null>(null);
  const [rerunningRunId, setRerunningRunId] = useState<string | null>(null);
  const [rerunningSampleId, setRerunningSampleId] = useState<string | null>(null);

  const [questionGroups, setQuestionGroups] = useState<QuestionGroup[]>([]);
  const [questions, setQuestions] = useState<QuestionEntry[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowConfig[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [samples, setSamples] = useState<EvaluationSample[]>([]);
  const [evaluators, setEvaluators] = useState<EvaluatorProfile[]>([]);
  const [guidelines, setGuidelines] = useState<GuidelineEntry[]>([]);

  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);

  const [runName, setRunName] = useState("");
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [manualReviewMode, setManualReviewMode] = useState<"none" | "open" | "assigned" | "mixed">("open");
  const [selectedEvaluatorSub, setSelectedEvaluatorSub] = useState("");
  const [assignmentJson, setAssignmentJson] = useState("");
  const [runtimeLlmSettingsJson, setRuntimeLlmSettingsJson] = useState(DEFAULT_RUNTIME_LLM_SETTINGS_JSON);

  async function loadBase() {
    setLoading(true);
    setError(null);
    try {
      const [groups, workflowList, runList, evaluatorList, guidelineList] = await Promise.all([
        listQuestionGroups(),
        listWorkflows(),
        listRuns(),
        listEvaluators(),
        listGuidelines(),
      ]);
      setQuestionGroups(groups);
      setWorkflows(workflowList);
      setRuns(runList);
      setEvaluators(evaluatorList);
      setGuidelines(guidelineList);
      if (!selectedGroupId && groups[0]?._id) setSelectedGroupId(normalizeObjectId(groups[0]._id));
      if (!selectedRunId && runList[0]?._id) setSelectedRunId(normalizeObjectId(runList[0]._id));
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!auth.initialized || !auth.authenticated) return;
    void loadBase();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.initialized, auth.authenticated]);

  useEffect(() => {
    if (!selectedGroupId) {
      setQuestions([]);
      return;
    }
    void (async () => {
      try {
        setQuestions(await listQuestions({question_group_id: selectedGroupId}));
      } catch (err: any) {
        setError(err?.message ?? String(err));
      }
    })();
  }, [selectedGroupId, listQuestions]);

  useEffect(() => {
    if (!selectedRunId) {
      setSamples([]);
      return;
    }
    void (async () => {
      try {
        setSamples(await listSamples({run_id: selectedRunId}));
      } catch (err: any) {
        setError(err?.message ?? String(err));
      }
    })();
  }, [selectedRunId, listSamples]);

  useEffect(() => {
    const hasActiveRun = runs.some((run) => ["queued", "running"].includes(run.status));
    if (!hasActiveRun) return;
    const id = window.setInterval(() => {
      void loadBase();
      if (selectedRunId) {
        void listSamples({run_id: selectedRunId}).then(setSamples).catch(() => undefined);
      }
    }, 5000);
    return () => window.clearInterval(id);
  }, [runs, selectedRunId, listSamples]);

  const selectedEvaluator = useMemo(
    () => evaluators.find((entry) => entry.sub === selectedEvaluatorSub),
    [evaluators, selectedEvaluatorSub],
  );
  const selectedRun = useMemo(
    () => runs.find((run) => normalizeObjectId(run._id) === selectedRunId),
    [runs, selectedRunId],
  );

  async function handleCreateGroup() {
    if (!newGroupName.trim()) return;
    try {
      const created = await createQuestionGroup({name: newGroupName.trim(), description: newGroupDescription.trim() || null});
      setNewGroupName("");
      setNewGroupDescription("");
      await loadBase();
      setSelectedGroupId(normalizeObjectId(created._id));
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  async function handleImportQuestions() {
    if (!selectedGroupId || !importFile) return;
    try {
      await importQuestionsCsv(selectedGroupId, importFile);
      setImportFile(null);
      setQuestions(await listQuestions({question_group_id: selectedGroupId}));
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  async function handleExportQuestions() {
    try {
      const content = await exportQuestionsCsv(selectedGroupId || undefined);
      downloadTextFile("evaluation_questions.csv", content, "text/csv");
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  async function refreshQuestions(groupId = selectedGroupId) {
    if (!groupId) {
      setQuestions([]);
      return;
    }
    setQuestions(await listQuestions({question_group_id: groupId}));
  }

  function openCreateQuestionDialog() {
    setQuestionDialogMode("create");
    setEditingQuestion(null);
    setQuestionEntryDialogOpen(true);
  }

  function openEditQuestionDialog(question: QuestionEntry) {
    setQuestionDialogMode("edit");
    setEditingQuestion(question);
    setQuestionEntryDialogOpen(true);
  }

  function closeQuestionDialog() {
    setQuestionEntryDialogOpen(false);
    setEditingQuestion(null);
    setQuestionDialogMode("create");
  }

  async function handleSubmitQuestionEntry(payload: QuestionEntryCreateRequest) {
    try {
      if (questionDialogMode === "edit" && editingQuestion?._id) {
        await updateQuestion(normalizeObjectId(editingQuestion._id), payload);
      } else {
        await createQuestion(payload);
      }
      await refreshQuestions();
    } catch (err: any) {
      setError(err?.message ?? String(err));
      throw err;
    }
  }

  async function handleDeleteQuestion(question: QuestionEntry) {
    const questionId = normalizeObjectId(question._id);
    if (!questionId) return;
    const confirmed = window.confirm(`Delete this question?\n\n${question.question}`);
    if (!confirmed) return;

    setDeletingQuestionId(questionId);
    try {
      await deleteQuestion(questionId);
      await refreshQuestions();
      if (editingQuestion && normalizeObjectId(editingQuestion._id) === questionId) {
        closeQuestionDialog();
      }
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setDeletingQuestionId(null);
    }
  }

  async function handleFindBoundingBoxes(args: FindBoundingBoxesArgs) {
    try {
      return await findBoundingBoxes(args);
    } catch (err: any) {
      setError(err?.message ?? String(err));
      throw err;
    }
  }

  async function handleCreateRun() {
    if (!runName.trim() || !selectedWorkflowId || !selectedGroupId) return;
    try {
      const manualReviewAssignments = assignmentJson.trim().length > 0 ? JSON.parse(assignmentJson) : [];
      const runtimeLlmSettingsPayload = buildRuntimeLlmSettingsPayload();
      await createRun({
        name: runName.trim(),
        workflow_system_id: selectedWorkflowId,
        source_type: "question_group_batch",
        question_group_id: selectedGroupId,
        manual_review_mode: manualReviewMode,
        assigned_evaluator_sub: selectedEvaluator?.sub ?? null,
        assigned_evaluator_username: selectedEvaluator?.username ?? null,
        manual_review_assignments: manualReviewAssignments,
        runtime_llm_settings: runtimeLlmSettingsPayload ?? null,
      });
      setRunName("");
      setAssignmentJson("");
      setRuntimeLlmSettingsJson(DEFAULT_RUNTIME_LLM_SETTINGS_JSON);
      await loadBase();
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  async function handleRerunRun(run: EvaluationRun) {
    const runId = normalizeObjectId(run._id);
    if (!runId) return;
    const confirmed = window.confirm(`Rerun this evaluation run?\n\n${run.name}`);
    if (!confirmed) return;

    setRerunningRunId(runId);
    setError(null);
    try {
      await rerunRun(runId);
      setSelectedRunId(runId);
      const [runSamples] = await Promise.all([
        listSamples({run_id: runId}),
        loadBase(),
      ]);
      setSamples(runSamples);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setRerunningRunId(null);
    }
  }

  async function handleRerunSample(sample: EvaluationSample) {
    const sampleId = normalizeObjectId(sample._id);
    const runId = normalizeObjectId(sample.run_id);
    if (!sampleId || !runId) return;
    const confirmed = window.confirm(`Rerun this sample?\n\n${sample.question_text || "Unnamed sample"}`);
    if (!confirmed) return;

    setRerunningSampleId(sampleId);
    setError(null);
    try {
      await rerunSample(sampleId);
      const [runSamples] = await Promise.all([
        listSamples({run_id: runId}),
        loadBase(),
      ]);
      setSamples(runSamples);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setRerunningSampleId(null);
    }
  }

  function buildRuntimeLlmSettingsPayload(): LLMSettingsOverride | undefined {
    const trimmed = runtimeLlmSettingsJson.trim();
    if (!trimmed) return undefined;

    const parsed = JSON.parse(trimmed);
    if (parsed == null || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("LLM settings JSON must be a JSON object.");
    }

    return parsed as LLMSettingsOverride;
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setImportFile(file);
  }

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Box>
          <Typography variant="h4" sx={{fontWeight: 800}}>
            Evaluation admin
          </Typography>
          <Typography color="text.secondary">
            Manage question datasets, create question entries, batch runs, and sample monitoring.
          </Typography>
        </Box>
        <Button variant="outlined" onClick={() => void loadBase()} disabled={loading} sx={{textTransform: "none"}}>
          Reload
        </Button>
      </Stack>

      {error ? <Alert severity="error">{error}</Alert> : null}

      {loading ? (
        <Box sx={{display: "flex", justifyContent: "center", py: 6}}>
          <CircularProgress />
        </Box>
      ) : null}

      <QuestionGroupsCard
        questionGroups={questionGroups}
        selectedGroupId={selectedGroupId}
        newGroupName={newGroupName}
        newGroupDescription={newGroupDescription}
        onSelectedGroupChange={setSelectedGroupId}
        onNewGroupNameChange={setNewGroupName}
        onNewGroupDescriptionChange={setNewGroupDescription}
        onCreateGroup={() => void handleCreateGroup()}
      />

      <QuestionDatasetCard
        selectedGroupId={selectedGroupId}
        importFile={importFile}
        questions={questions}
        deletingQuestionId={deletingQuestionId}
        onFileChange={onFileChange}
        onImportQuestions={() => void handleImportQuestions()}
        onExportQuestions={() => void handleExportQuestions()}
        onOpenCreateQuestion={openCreateQuestionDialog}
        onOpenEditQuestion={openEditQuestionDialog}
        onDeleteQuestion={(question) => void handleDeleteQuestion(question)}
      />

      <BatchRunCard
        selectedGroupId={selectedGroupId}
        workflows={workflows}
        evaluators={evaluators}
        runName={runName}
        selectedWorkflowId={selectedWorkflowId}
        manualReviewMode={manualReviewMode}
        selectedEvaluatorSub={selectedEvaluatorSub}
        assignmentJson={assignmentJson}
        runtimeLlmSettingsJson={runtimeLlmSettingsJson}
        onRunNameChange={setRunName}
        onSelectedWorkflowIdChange={setSelectedWorkflowId}
        onManualReviewModeChange={setManualReviewMode}
        onSelectedEvaluatorSubChange={setSelectedEvaluatorSub}
        onAssignmentJsonChange={setAssignmentJson}
        onRuntimeLlmSettingsJsonChange={setRuntimeLlmSettingsJson}
        onCreateRun={() => void handleCreateRun()}
      />

      <RunsCard
        runs={runs}
        selectedRunId={selectedRunId}
        onSelectRun={setSelectedRunId}
        onRerunRun={(run) => void handleRerunRun(run)}
        rerunningRunId={rerunningRunId}
      />

      <SamplesCard
        selectedRun={selectedRun}
        samples={samples}
        onRerunSample={(sample) => void handleRerunSample(sample)}
        rerunningSampleId={rerunningSampleId}
      />

      <QuestionEntryDialog
        open={questionEntryDialogOpen}
        mode={questionDialogMode}
        questionGroupId={selectedGroupId}
        guidelines={guidelines}
        initialQuestion={editingQuestion}
        onClose={closeQuestionDialog}
        onSubmit={handleSubmitQuestionEntry}
        onFindBoundingBoxes={handleFindBoundingBoxes}
      />
    </Stack>
  );
}
