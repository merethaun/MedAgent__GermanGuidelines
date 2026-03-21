import {useCallback} from "react";
import {useAuthedFetchBase} from "./http";

export type QuestionSuperClass = "simple" | "negative" | "complex";
export type QuestionSubClass =
  | "text"
  | "recommendation"
  | "table"
  | "statement"
  | "image"
  | "multiple_guidelines"
  | "multiple_sections_same_guideline"
  | "synonym"
  | "multi_step_reasoning"
  | "outside_medicine"
  | "outside_omfs"
  | "outside_guidelines"
  | "malformed"
  | "patient_specific";

export const QUESTION_SUB_CLASS_OPTIONS: Record<QuestionSuperClass, Array<{value: QuestionSubClass; label: string}>> = {
  simple: [
    {value: "text", label: "Text"},
    {value: "recommendation", label: "Recommendation"},
    {value: "table", label: "Table"},
    {value: "statement", label: "Statement"},
    {value: "image", label: "Image"},
  ],
  complex: [
    {value: "multiple_guidelines", label: "Multiple guidelines"},
    {value: "multiple_sections_same_guideline", label: "Multiple sections (same guideline)"},
    {value: "synonym", label: "Synonym"},
    {value: "multi_step_reasoning", label: "Multi-step reasoning"},
  ],
  negative: [
    {value: "outside_medicine", label: "Outside medicine"},
    {value: "outside_omfs", label: "Outside OMFS"},
    {value: "outside_guidelines", label: "Outside guidelines"},
    {value: "malformed", label: "Malformed"},
    {value: "patient_specific", label: "Patient-specific"},
  ],
};

export type QuestionGroup = {
  _id?: string | null;
  name: string;
  description?: string | null;
  created_at?: string;
};

export type QuestionClassification = {
  super_class: QuestionSuperClass;
  sub_class: QuestionSubClass;
};

export type BoundingBox = {
  page: number;
  positions: [number, number, number, number];
};

export type ExpectedRetrievalSnippet = {
  guideline_source?: string | null;
  guideline_title?: string | null;
  bounding_boxes: BoundingBox[];
  reference_type?: "text" | "image" | "table" | "recommendation" | "statement" | "metadata" | null;
  retrieval_text: string;
};

export type QuestionEntry = {
  _id?: string | null;
  question_group_id: string;
  question: string;
  classification: QuestionClassification;
  correct_answer?: string | null;
  expected_retrieval: ExpectedRetrievalSnippet[];
  note?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type QuestionEntryCreateRequest = Omit<QuestionEntry, "_id" | "created_at" | "updated_at">;
export type QuestionEntryUpdateRequest = QuestionEntryCreateRequest;

export type ManualReviewAssignment = {
  question_id?: string | null;
  evaluator_sub: string;
  evaluator_username?: string | null;
};

export type LLMSettingsOverride = {
  model?: string | null;
  api_key?: string | null;
  base_url?: string | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  timeout_s?: number | null;
  seed?: number | null;
  extra_headers?: Record<string, string>;
  extra_body?: Record<string, any>;
};

export type EvaluationRunCreateRequest = {
  name: string;
  workflow_system_id: string;
  source_type: "question_group_batch" | "chat_snapshot";
  question_group_id?: string;
  source_chat_id?: string;
  source_interaction_index?: number;
  manual_review_mode: "none" | "open" | "assigned" | "mixed";
  assigned_evaluator_sub?: string | null;
  assigned_evaluator_username?: string | null;
  manual_review_assignments?: ManualReviewAssignment[];
  runtime_llm_settings?: LLMSettingsOverride | null;
};

export type RetrievalMetrics = {
  precision?: number | null;
  recall?: number | null;
  f1?: number | null;
  retrieval_latency?: number | null;
};

export type LexicalMetrics = {
  exact_match?: number | null;
  token_f1?: number | null;
  jaccard?: number | null;
  sequence_ratio?: number | null;
};

export type EmbeddingMetrics = {
  provider?: string | null;
  cosine_similarity?: number | null;
  euclidean_distance?: number | null;
  status?: string | null;
  note?: string | null;
};

export type GPTScoreMetrics = {
  similarity?: number | null;
  reasoning?: string | null;
  status?: string | null;
  note?: string | null;
};

export type AutomaticMetrics = {
  response_latency?: number | null;
  retrieval: RetrievalMetrics;
  lexical?: LexicalMetrics | null;
  embeddings?: EmbeddingMetrics | null;
  gpt_score?: GPTScoreMetrics | null;
};

export type EvaluationRun = {
  _id?: string | null;
  name: string;
  workflow_system_id: string;
  workflow_name?: string | null;
  source_type: "question_group_batch" | "chat_snapshot";
  status: "queued" | "running" | "completed" | "failed" | "partial";
  question_group_id?: string | null;
  question_group_name?: string | null;
  source_chat_id?: string | null;
  source_interaction_index?: number | null;
  manual_review_mode: "none" | "open" | "assigned" | "mixed";
  assigned_evaluator_sub?: string | null;
  assigned_evaluator_username?: string | null;
  manual_review_assignments?: ManualReviewAssignment[];
  created_by_sub: string;
  created_by_username?: string | null;
  total_samples: number;
  processed_samples: number;
  failed_samples: number;
  open_tasks: number;
  created_at?: string;
  updated_at?: string;
};

export type EvaluationSample = {
  _id?: string | null;
  run_id: string;
  source_type: "question_group_batch" | "chat_snapshot";
  status: "queued" | "running" | "completed" | "failed";
  source_question_id?: string | null;
  source_question_group_id?: string | null;
  source_chat_id?: string | null;
  source_interaction_index?: number | null;
  workflow_system_id?: string | null;
  workflow_name?: string | null;
  question_text?: string | null;
  question_classification?: QuestionClassification | null;
  expected_answer?: string | null;
  expected_retrieval: ExpectedRetrievalSnippet[];
  backend_chat_id?: string | null;
  backend_interaction_index?: number | null;
  answer_text?: string | null;
  retrieval_output: Record<string, any>[];
  response_latency?: number | null;
  retrieval_latency?: number | null;
  workflow_execution: Record<string, any>[];
  failure_reason?: string | null;
  automatic_metrics: AutomaticMetrics;
  manual_review_task_id?: string | null;
  user_feedback_count: number;
  created_at?: string;
  updated_at?: string;
};

export type ManualReviewSubmission = {
  correctness_score?: number | null;
  factuality_score?: number | null;
  count_factual_conflicts?: number | null;
  count_input_conflicts?: number | null;
  count_context_conflicts?: number | null;
  fact_count_overall?: number | null;
  fact_count_backed?: number | null;
  note?: string | null;
};

export type ManualReviewTask = {
  _id?: string | null;
  run_id: string;
  sample_id: string;
  status: "open" | "claimed" | "completed";
  assignment_mode: "open" | "assigned";
  assigned_evaluator_sub?: string | null;
  assigned_evaluator_username?: string | null;
  claimed_by_sub?: string | null;
  claimed_by_username?: string | null;
  claimed_at?: string | null;
  completed_at?: string | null;
  review?: Record<string, any> | null;
  created_at?: string;
  updated_at?: string;
};

export type EvaluatorProfile = {
  _id?: string | null;
  sub: string;
  username?: string | null;
  last_seen_at?: string;
};

export type AnswerFeedbackCreateRequest = {
  chat_id: string;
  interaction_index: number;
  helpful?: boolean | null;
  rating?: number | null;
  comment?: string | null;
};

async function readBodySafe(res: Response) {
  const text = await res.text().catch(() => "");
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export function useEvaluationApi() {
  const baseUrl = import.meta.env.VITE_EVALUATION_URL ?? "http://localhost:5001";
  const authedFetch = useAuthedFetchBase(baseUrl);

  const listQuestionGroups = useCallback(async () => {
    const res = await authedFetch("/evaluation/question-groups", {method: "GET"});
    return (await res.json()) as QuestionGroup[];
  }, [authedFetch]);

  const createQuestionGroup = useCallback(async (payload: { name: string; description?: string | null }) => {
    const res = await authedFetch("/evaluation/question-groups", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return (await res.json()) as QuestionGroup;
  }, [authedFetch]);

  const listQuestions = useCallback(async (params?: {
    question_group_id?: string;
    question?: string;
    super_class?: string;
    sub_class?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.question_group_id) sp.set("question_group_id", params.question_group_id);
    if (params?.question) sp.set("question", params.question);
    if (params?.super_class) sp.set("super_class", params.super_class);
    if (params?.sub_class) sp.set("sub_class", params.sub_class);
    const res = await authedFetch(`/evaluation/questions${sp.toString() ? `?${sp.toString()}` : ""}`, {method: "GET"});
    return (await res.json()) as QuestionEntry[];
  }, [authedFetch]);

  const createQuestion = useCallback(async (payload: QuestionEntryCreateRequest) => {
    const res = await authedFetch("/evaluation/questions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return (await res.json()) as QuestionEntry;
  }, [authedFetch]);

  const updateQuestion = useCallback(async (questionId: string, payload: QuestionEntryUpdateRequest) => {
    const res = await authedFetch(`/evaluation/questions/${encodeURIComponent(questionId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    return (await res.json()) as QuestionEntry;
  }, [authedFetch]);

  const deleteQuestion = useCallback(async (questionId: string) => {
    const res = await authedFetch(`/evaluation/questions/${encodeURIComponent(questionId)}`, {
      method: "DELETE",
    });
    return await readBodySafe(res);
  }, [authedFetch]);

  const importQuestionsCsv = useCallback(async (questionGroupId: string, file: File) => {
    const form = new FormData();
    form.append("csv_file", file);
    const res = await authedFetch(`/evaluation/questions/import?question_group_id=${encodeURIComponent(questionGroupId)}`, {
      method: "POST",
      body: form,
    });
    return (await res.json()) as QuestionEntry[];
  }, [authedFetch]);

  const exportQuestionsCsv = useCallback(async (questionGroupId?: string) => {
    const sp = new URLSearchParams();
    if (questionGroupId) sp.set("question_group_id", questionGroupId);
    const res = await authedFetch(`/evaluation/questions/export.csv${sp.toString() ? `?${sp.toString()}` : ""}`, {method: "GET"});
    return await res.text();
  }, [authedFetch]);

  const listRuns = useCallback(async () => {
    const res = await authedFetch("/evaluation/runs", {method: "GET"});
    return (await res.json()) as EvaluationRun[];
  }, [authedFetch]);

  const createRun = useCallback(async (payload: EvaluationRunCreateRequest) => {
    const res = await authedFetch("/evaluation/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return (await res.json()) as EvaluationRun;
  }, [authedFetch]);

  const getRun = useCallback(async (runId: string) => {
    const res = await authedFetch(`/evaluation/runs/${encodeURIComponent(runId)}`, {method: "GET"});
    return (await res.json()) as EvaluationRun;
  }, [authedFetch]);

  const rerunRun = useCallback(async (runId: string) => {
    const res = await authedFetch(`/evaluation/runs/${encodeURIComponent(runId)}/rerun`, {method: "POST"});
    return (await res.json()) as EvaluationRun;
  }, [authedFetch]);

  const listSamples = useCallback(async (params?: { run_id?: string; status?: string }) => {
    const sp = new URLSearchParams();
    if (params?.run_id) sp.set("run_id", params.run_id);
    if (params?.status) sp.set("status", params.status);
    const res = await authedFetch(`/evaluation/samples${sp.toString() ? `?${sp.toString()}` : ""}`, {method: "GET"});
    return (await res.json()) as EvaluationSample[];
  }, [authedFetch]);

  const getSample = useCallback(async (sampleId: string) => {
    const res = await authedFetch(`/evaluation/samples/${encodeURIComponent(sampleId)}`, {method: "GET"});
    return (await res.json()) as EvaluationSample;
  }, [authedFetch]);

  const rerunSample = useCallback(async (sampleId: string) => {
    const res = await authedFetch(`/evaluation/samples/${encodeURIComponent(sampleId)}/rerun`, {method: "POST"});
    return (await res.json()) as EvaluationSample;
  }, [authedFetch]);

  const listTasks = useCallback(async (params?: { run_id?: string; status?: string; mine?: boolean; include_open?: boolean }) => {
    const sp = new URLSearchParams();
    if (params?.run_id) sp.set("run_id", params.run_id);
    if (params?.status) sp.set("status", params.status);
    if (params?.mine != null) sp.set("mine", String(params.mine));
    if (params?.include_open != null) sp.set("include_open", String(params.include_open));
    const res = await authedFetch(`/evaluation/tasks${sp.toString() ? `?${sp.toString()}` : ""}`, {method: "GET"});
    return (await res.json()) as ManualReviewTask[];
  }, [authedFetch]);

  const claimTask = useCallback(async (taskId: string) => {
    const res = await authedFetch(`/evaluation/tasks/${encodeURIComponent(taskId)}/claim`, {method: "POST"});
    return (await res.json()) as ManualReviewTask;
  }, [authedFetch]);

  const submitTask = useCallback(async (taskId: string, payload: ManualReviewSubmission) => {
    const res = await authedFetch(`/evaluation/tasks/${encodeURIComponent(taskId)}/submit`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return (await res.json()) as ManualReviewTask;
  }, [authedFetch]);

  const createAnswerFeedback = useCallback(async (payload: AnswerFeedbackCreateRequest) => {
    const res = await authedFetch("/evaluation/feedback/chat-interactions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return await readBodySafe(res);
  }, [authedFetch]);

  const registerEvaluator = useCallback(async () => {
    const res = await authedFetch("/evaluation/evaluators/me/register", {method: "POST"});
    return (await res.json()) as EvaluatorProfile;
  }, [authedFetch]);

  const listEvaluators = useCallback(async () => {
    const res = await authedFetch("/evaluation/evaluators", {method: "GET"});
    return (await res.json()) as EvaluatorProfile[];
  }, [authedFetch]);

  return {
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
    getRun,
    rerunRun,
    listSamples,
    getSample,
    rerunSample,
    listTasks,
    claimTask,
    submitTask,
    createAnswerFeedback,
    registerEvaluator,
    listEvaluators,
  };
}
