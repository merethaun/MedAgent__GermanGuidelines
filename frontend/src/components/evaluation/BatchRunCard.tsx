import {Button, Card, CardContent, MenuItem, Stack, TextField, Typography} from "@mui/material";

import {type EvaluatorProfile} from "../../api/evaluation";
import {normalizeObjectId, type WorkflowConfig} from "../../api/system";

type BatchRunCardProps = {
  selectedGroupId: string;
  workflows: WorkflowConfig[];
  evaluators: EvaluatorProfile[];
  runName: string;
  selectedWorkflowId: string;
  manualReviewMode: "none" | "open" | "assigned" | "mixed";
  selectedEvaluatorSub: string;
  assignmentJson: string;
  runtimeLlmSettingsJson: string;
  onRunNameChange: (value: string) => void;
  onSelectedWorkflowIdChange: (value: string) => void;
  onManualReviewModeChange: (value: "none" | "open" | "assigned" | "mixed") => void;
  onSelectedEvaluatorSubChange: (value: string) => void;
  onAssignmentJsonChange: (value: string) => void;
  onRuntimeLlmSettingsJsonChange: (value: string) => void;
  onCreateRun: () => void;
};

export default function BatchRunCard({
  selectedGroupId,
  workflows,
  evaluators,
  runName,
  selectedWorkflowId,
  manualReviewMode,
  selectedEvaluatorSub,
  assignmentJson,
  runtimeLlmSettingsJson,
  onRunNameChange,
  onSelectedWorkflowIdChange,
  onManualReviewModeChange,
  onSelectedEvaluatorSubChange,
  onAssignmentJsonChange,
  onRuntimeLlmSettingsJsonChange,
  onCreateRun,
}: BatchRunCardProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{fontWeight: 800, mb: 2}}>
          Create batch run
        </Typography>
        <Stack spacing={2}>
          <TextField label="Run name" value={runName} onChange={(e) => onRunNameChange(e.target.value)} fullWidth />
          <TextField
            select
            fullWidth
            label="Workflow"
            value={selectedWorkflowId}
            onChange={(e) => onSelectedWorkflowIdChange(e.target.value)}
          >
            {workflows.map((workflow) => (
              <MenuItem key={normalizeObjectId(workflow._id)} value={normalizeObjectId(workflow._id)}>
                {workflow.name}
              </MenuItem>
            ))}
          </TextField>
          <Stack direction={{xs: "column", md: "row"}} spacing={2}>
            <TextField
              select
              fullWidth
              label="Manual review mode"
              value={manualReviewMode}
              onChange={(e) => onManualReviewModeChange(e.target.value as "none" | "open" | "assigned" | "mixed")}
            >
              <MenuItem value="none">none</MenuItem>
              <MenuItem value="open">open</MenuItem>
              <MenuItem value="assigned">assigned</MenuItem>
              <MenuItem value="mixed">mixed</MenuItem>
            </TextField>
            <TextField
              select
              fullWidth
              label="Assigned evaluator"
              value={selectedEvaluatorSub}
              onChange={(e) => onSelectedEvaluatorSubChange(e.target.value)}
              disabled={manualReviewMode === "open" || manualReviewMode === "none"}
            >
              <MenuItem value="">None</MenuItem>
              {evaluators.map((evaluator) => (
                <MenuItem key={evaluator.sub} value={evaluator.sub}>
                  {evaluator.username || evaluator.sub}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <TextField
            label="Mixed assignment JSON"
            value={assignmentJson}
            onChange={(e) => onAssignmentJsonChange(e.target.value)}
            disabled={manualReviewMode !== "mixed"}
            multiline
            minRows={3}
            helperText='Optional. Example: [{"question_id":"...","evaluator_sub":"...","evaluator_username":"alice"}]'
            fullWidth
          />
          <TextField
            label="LLM settings JSON"
            value={runtimeLlmSettingsJson}
            onChange={(e) => onRuntimeLlmSettingsJsonChange(e.target.value)}
            multiline
            minRows={8}
            helperText="Optional. Applied to workflow execution and GPT-score metrics for this run only. Clear the field to disable the override."
            fullWidth
          />
          <Button
            variant="contained"
            onClick={onCreateRun}
            disabled={!runName.trim() || !selectedWorkflowId || !selectedGroupId}
            sx={{textTransform: "none", alignSelf: "flex-start"}}
          >
            Create run
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
