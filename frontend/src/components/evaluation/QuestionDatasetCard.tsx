import {ChangeEvent} from "react";
import {
  Button,
  Card,
  CardContent,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import {type QuestionEntry} from "../../api/evaluation";
import {normalizeObjectId} from "../../api/system";

type QuestionDatasetCardProps = {
  selectedGroupId: string;
  importFile: File | null;
  questions: QuestionEntry[];
  deletingQuestionId?: string | null;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onImportQuestions: () => void;
  onExportQuestions: () => void;
  onOpenCreateQuestion: () => void;
  onOpenEditQuestion: (question: QuestionEntry) => void;
  onDeleteQuestion: (question: QuestionEntry) => void;
};

export default function QuestionDatasetCard({
  selectedGroupId,
  importFile,
  questions,
  deletingQuestionId,
  onFileChange,
  onImportQuestions,
  onExportQuestions,
  onOpenCreateQuestion,
  onOpenEditQuestion,
  onDeleteQuestion,
}: QuestionDatasetCardProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{mb: 2}}>
          <Typography variant="h6" sx={{fontWeight: 800}}>
            Dataset questions
          </Typography>
          <Button
            variant="contained"
            onClick={onOpenCreateQuestion}
            disabled={!selectedGroupId}
            sx={{textTransform: "none"}}
          >
            Add question entry
          </Button>
        </Stack>
        <Stack direction={{xs: "column", md: "row"}} spacing={2} alignItems={{md: "center"}}>
          <Button component="label" variant="outlined" sx={{textTransform: "none"}}>
            Choose CSV
            <input hidden type="file" accept=".csv" onChange={onFileChange} />
          </Button>
          <Typography color="text.secondary">
            {importFile ? importFile.name : "No file selected"}
          </Typography>
          <Button
            variant="contained"
            onClick={onImportQuestions}
            disabled={!selectedGroupId || !importFile}
            sx={{textTransform: "none"}}
          >
            Import questions
          </Button>
          <Button variant="outlined" onClick={onExportQuestions} sx={{textTransform: "none"}}>
            Export CSV
          </Button>
        </Stack>
        <TableContainer sx={{mt: 2}}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{fontWeight: 800}}>Question</TableCell>
                <TableCell sx={{fontWeight: 800}}>Class</TableCell>
                <TableCell sx={{fontWeight: 800}}>Expected retrieval</TableCell>
                <TableCell sx={{fontWeight: 800}}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {questions.map((question) => {
                const questionId = normalizeObjectId(question._id);
                return (
                  <TableRow key={questionId}>
                    <TableCell>{question.question}</TableCell>
                    <TableCell>{question.classification.super_class} / {question.classification.sub_class}</TableCell>
                    <TableCell>{question.expected_retrieval?.length ?? 0}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => onOpenEditQuestion(question)}
                          sx={{textTransform: "none"}}
                        >
                          Edit
                        </Button>
                        <Button
                          color="error"
                          variant="outlined"
                          size="small"
                          onClick={() => onDeleteQuestion(question)}
                          disabled={deletingQuestionId === questionId}
                          sx={{textTransform: "none"}}
                        >
                          Delete
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
              {questions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}>No questions in the selected group yet.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}
