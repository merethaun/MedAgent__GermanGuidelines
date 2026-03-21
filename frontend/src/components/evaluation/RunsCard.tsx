import {Button, Card, CardContent, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography} from "@mui/material";

import {type EvaluationRun} from "../../api/evaluation";
import {normalizeObjectId} from "../../api/system";

type RunsCardProps = {
  runs: EvaluationRun[];
  selectedRunId: string;
  onSelectRun: (runId: string) => void;
  onRerunRun: (run: EvaluationRun) => void;
  rerunningRunId?: string | null;
};

export default function RunsCard({runs, selectedRunId, onSelectRun, onRerunRun, rerunningRunId}: RunsCardProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{fontWeight: 800, mb: 2}}>
          Runs
        </Typography>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{fontWeight: 800}}>Run</TableCell>
                <TableCell sx={{fontWeight: 800}}>Workflow</TableCell>
                <TableCell sx={{fontWeight: 800}}>Status</TableCell>
                <TableCell sx={{fontWeight: 800}}>Samples</TableCell>
                <TableCell sx={{fontWeight: 800}}>Open tasks</TableCell>
                <TableCell sx={{fontWeight: 800}} align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.map((run) => {
                const runId = normalizeObjectId(run._id);
                const isActive = run.status === "queued" || run.status === "running";
                const isRerunning = rerunningRunId === runId;

                return (
                  <TableRow
                    key={runId}
                    hover
                    selected={runId === selectedRunId}
                    onClick={() => onSelectRun(runId)}
                    sx={{cursor: "pointer"}}
                  >
                    <TableCell>{run.name}</TableCell>
                    <TableCell>{run.workflow_name || run.workflow_system_id}</TableCell>
                    <TableCell>{run.status}</TableCell>
                    <TableCell>{run.processed_samples}/{run.total_samples}</TableCell>
                    <TableCell>{run.open_tasks}</TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={isActive || isRerunning}
                        onClick={(event) => {
                          event.stopPropagation();
                          onRerunRun(run);
                        }}
                        sx={{textTransform: "none"}}
                      >
                        {isRerunning ? "Queueing..." : "Rerun"}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
              {runs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6}>No evaluation runs yet.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}
