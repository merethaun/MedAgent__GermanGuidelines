import {useEffect, useMemo, useState} from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import {useAuth} from "../auth/AuthContext";
import {useEvaluationApi} from "../api/evaluation";
import {normalizeObjectId} from "../api/system";

const EMPTY_FORM = {
  correctness_score: "",
  factuality_score: "",
  count_factual_conflicts: "",
  count_input_conflicts: "",
  count_context_conflicts: "",
  fact_count_overall: "",
  fact_count_backed: "",
  note: "",
};

function toNullableNumber(value: string) {
  if (value.trim() === "") return null;
  return Number(value);
}

export default function EvaluationTasksPage() {
  const auth = useAuth();
  const {listTasks, claimTask, submitTask, getSample, registerEvaluator} = useEvaluationApi();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [selectedTask, setSelectedTask] = useState<any | null>(null);
  const [selectedSample, setSelectedSample] = useState<any | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [mine, setMine] = useState(true);
  const [includeOpen, setIncludeOpen] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);

  const currentUser = auth.username;

  async function loadTasksData() {
    setLoading(true);
    setError(null);
    try {
      if (auth.hasRole(import.meta.env.VITE_KEYCLOAK_EVALUATOR_ROLE ?? "evaluator") || auth.hasRole(import.meta.env.VITE_KEYCLOAK_ADMIN_ROLE ?? "admin")) {
        await registerEvaluator();
      }
      setTasks(await listTasks({mine, include_open: includeOpen}));
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!auth.initialized || !auth.authenticated) return;
    void loadTasksData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.initialized, auth.authenticated, mine, includeOpen]);

  const selectedTaskId = useMemo(() => normalizeObjectId(selectedTask?._id), [selectedTask]);

  async function handleClaim(taskId: string) {
    try {
      await claimTask(taskId);
      await loadTasksData();
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  async function openReview(task: any) {
    try {
      let activeTask = task;
      if (task.status === "open") {
        activeTask = await claimTask(normalizeObjectId(task._id));
        await loadTasksData();
      }
      setSelectedTask(activeTask);
      setSelectedSample(await getSample(activeTask.sample_id));
      setForm(EMPTY_FORM);
      setDialogOpen(true);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  async function handleSubmitReview() {
    if (!selectedTask) return;
    try {
      await submitTask(normalizeObjectId(selectedTask._id), {
        correctness_score: toNullableNumber(form.correctness_score),
        factuality_score: toNullableNumber(form.factuality_score),
        count_factual_conflicts: toNullableNumber(form.count_factual_conflicts),
        count_input_conflicts: toNullableNumber(form.count_input_conflicts),
        count_context_conflicts: toNullableNumber(form.count_context_conflicts),
        fact_count_overall: toNullableNumber(form.fact_count_overall),
        fact_count_backed: toNullableNumber(form.fact_count_backed),
        note: form.note || null,
      });
      setDialogOpen(false);
      setSelectedTask(null);
      setSelectedSample(null);
      await loadTasksData();
    } catch (err: any) {
      setError(err?.message ?? String(err));
    }
  }

  const canReviewTask = (task: any) => task.status === "open" || task.claimed_by_username === currentUser;

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Box>
          <Typography variant="h4" sx={{fontWeight: 800}}>
            Evaluation tasks
          </Typography>
          <Typography color="text.secondary">
            Claim open tasks and complete manual reviews.
          </Typography>
        </Box>
        <Button variant="outlined" onClick={() => void loadTasksData()} sx={{textTransform: "none"}}>
          Reload
        </Button>
      </Stack>

      <Stack direction={{xs: "column", md: "row"}} spacing={2}>
        <FormControlLabel control={<Switch checked={mine} onChange={(e) => setMine(e.target.checked)} />} label="Only mine" />
        <FormControlLabel control={<Switch checked={includeOpen} onChange={(e) => setIncludeOpen(e.target.checked)} />} label="Include open tasks" />
      </Stack>

      {error ? <Alert severity="error">{error}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          {loading ? (
            <Box sx={{display: "flex", justifyContent: "center", py: 6}}>
              <CircularProgress />
            </Box>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{fontWeight: 800}}>Task</TableCell>
                    <TableCell sx={{fontWeight: 800}}>Status</TableCell>
                    <TableCell sx={{fontWeight: 800}}>Assignee</TableCell>
                    <TableCell sx={{fontWeight: 800}}>Claimed by</TableCell>
                    <TableCell sx={{fontWeight: 800}} align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tasks.map((task) => (
                    <TableRow key={normalizeObjectId(task._id)} selected={normalizeObjectId(task._id) === selectedTaskId}>
                      <TableCell>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Chip size="small" label={task.assignment_mode} />
                          <Typography variant="body2">{normalizeObjectId(task.sample_id)}</Typography>
                        </Stack>
                      </TableCell>
                      <TableCell>{task.status}</TableCell>
                      <TableCell>{task.assigned_evaluator_username || task.assigned_evaluator_sub || "-"}</TableCell>
                      <TableCell>{task.claimed_by_username || task.claimed_by_sub || "-"}</TableCell>
                      <TableCell align="right">
                        <Stack direction="row" spacing={1} justifyContent="flex-end">
                          {task.status === "open" ? (
                            <Button
                              variant="outlined"
                              size="small"
                              sx={{textTransform: "none"}}
                              onClick={() => void handleClaim(normalizeObjectId(task._id))}
                            >
                              Claim
                            </Button>
                          ) : null}
                          <Button
                            variant="contained"
                            size="small"
                            sx={{textTransform: "none"}}
                            onClick={() => void openReview(task)}
                            disabled={!canReviewTask(task)}
                          >
                            Review
                          </Button>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                  {tasks.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>No tasks found for the current filters.</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Manual review</DialogTitle>
        <DialogContent dividers>
          {selectedSample ? (
            <Stack spacing={2}>
              <Alert severity="info">
                Review sample <b>{normalizeObjectId(selectedSample._id)}</b>
              </Alert>
              <Typography variant="subtitle2">Question</Typography>
              <Typography sx={{whiteSpace: "pre-wrap"}}>{selectedSample.question_text || "-"}</Typography>
              <Typography variant="subtitle2">Expected answer</Typography>
              <Typography sx={{whiteSpace: "pre-wrap"}}>{selectedSample.expected_answer || "-"}</Typography>
              <Typography variant="subtitle2">Actual answer</Typography>
              <Typography sx={{whiteSpace: "pre-wrap"}}>{selectedSample.answer_text || "-"}</Typography>
              <Typography variant="subtitle2">Expected retrieval snippets</Typography>
              <Typography>{selectedSample.expected_retrieval?.length ?? 0}</Typography>
              <Stack direction={{xs: "column", md: "row"}} spacing={2}>
                <TextField label="Correctness (1-5)" value={form.correctness_score} onChange={(e) => setForm({...form, correctness_score: e.target.value})} fullWidth />
                <TextField label="Factuality (1-5)" value={form.factuality_score} onChange={(e) => setForm({...form, factuality_score: e.target.value})} fullWidth />
              </Stack>
              <Stack direction={{xs: "column", md: "row"}} spacing={2}>
                <TextField label="Factual conflicts" value={form.count_factual_conflicts} onChange={(e) => setForm({...form, count_factual_conflicts: e.target.value})} fullWidth />
                <TextField label="Input conflicts" value={form.count_input_conflicts} onChange={(e) => setForm({...form, count_input_conflicts: e.target.value})} fullWidth />
                <TextField label="Context conflicts" value={form.count_context_conflicts} onChange={(e) => setForm({...form, count_context_conflicts: e.target.value})} fullWidth />
              </Stack>
              <Stack direction={{xs: "column", md: "row"}} spacing={2}>
                <TextField label="Facts overall" value={form.fact_count_overall} onChange={(e) => setForm({...form, fact_count_overall: e.target.value})} fullWidth />
                <TextField label="Facts backed" value={form.fact_count_backed} onChange={(e) => setForm({...form, fact_count_backed: e.target.value})} fullWidth />
              </Stack>
              <TextField
                label="Note"
                value={form.note}
                onChange={(e) => setForm({...form, note: e.target.value})}
                multiline
                minRows={3}
                fullWidth
              />
            </Stack>
          ) : (
            <CircularProgress />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)} sx={{textTransform: "none"}}>Cancel</Button>
          <Button variant="contained" onClick={() => void handleSubmitReview()} sx={{textTransform: "none"}}>
            Submit review
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
