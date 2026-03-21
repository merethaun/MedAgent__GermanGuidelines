import {Button, Card, CardContent, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography} from "@mui/material";

import {type EvaluationRun, type EvaluationSample} from "../../api/evaluation";
import {normalizeObjectId} from "../../api/system";

function fmtScore(value?: number | null) {
  return value == null ? "-" : value.toFixed(2);
}

type SamplesCardProps = {
  selectedRun?: EvaluationRun;
  samples: EvaluationSample[];
  onRerunSample: (sample: EvaluationSample) => void;
  rerunningSampleId?: string | null;
};

export default function SamplesCard({selectedRun, samples, onRerunSample, rerunningSampleId}: SamplesCardProps) {
  const runIsActive = selectedRun?.status === "queued" || selectedRun?.status === "running";

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{fontWeight: 800, mb: 2}}>
          {selectedRun ? `Samples for ${selectedRun.name}` : "Samples"}
        </Typography>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{fontWeight: 800}}>Question</TableCell>
                <TableCell sx={{fontWeight: 800}}>Status</TableCell>
                <TableCell sx={{fontWeight: 800}}>Latency</TableCell>
                <TableCell sx={{fontWeight: 800}}>Retrieval F1</TableCell>
                <TableCell sx={{fontWeight: 800}}>GPTScore</TableCell>
                <TableCell sx={{fontWeight: 800}} align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {samples.map((sample) => {
                const sampleId = normalizeObjectId(sample._id);
                const isRerunning = rerunningSampleId === sampleId;

                return (
                  <TableRow key={sampleId}>
                    <TableCell>{sample.question_text || "-"}</TableCell>
                    <TableCell>{sample.status}</TableCell>
                    <TableCell>{fmtScore(sample.automatic_metrics?.response_latency)}</TableCell>
                    <TableCell>{fmtScore(sample.automatic_metrics?.retrieval?.f1)}</TableCell>
                    <TableCell>{fmtScore(sample.automatic_metrics?.gpt_score?.similarity)}</TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={runIsActive || sample.status === "running" || isRerunning}
                        onClick={() => onRerunSample(sample)}
                        sx={{textTransform: "none"}}
                      >
                        {isRerunning ? "Queueing..." : "Rerun"}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
              {samples.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6}>Select a run to inspect its samples.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}
