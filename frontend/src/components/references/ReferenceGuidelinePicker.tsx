import {useMemo, useState} from "react";
import {Box, Button, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,} from "@mui/material";
import {type GuidelineEntry} from "../../api/references";
import {normalizeObjectId} from "../../api/system";

type Props = {
  guidelines: GuidelineEntry[];
  onCancel: () => void;
  onSelect: (guideline: GuidelineEntry) => void;
};

export default function ReferenceGuidelinePicker({guidelines, onCancel, onSelect}: Props) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return guidelines;

    return guidelines.filter((g) => {
      const haystack = [
        g.title,
        g.awmf_register_number,
        g.awmf_register_number_full,
        g.awmf_class ?? "",
      ]
        .join(" ")
        .toLowerCase();

      return haystack.includes(q);
    });
  }, [guidelines, query]);

  return (
    <Stack spacing={2}>
      <TextField
        label="Search guideline"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        fullWidth
        autoFocus
      />

      {filtered.length === 0 ? (
        <Box sx={{py: 2}}>
          <Typography sx={{fontWeight: 700}}>No matching guidelines</Typography>
          <Typography color="text.secondary">
            Adjust the search query.
          </Typography>
        </Box>
      ) : (
        <TableContainer sx={{maxHeight: 480}}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell sx={{fontWeight: 800}}>Guideline</TableCell>
                <TableCell sx={{fontWeight: 800}}>AWMF</TableCell>
                <TableCell sx={{fontWeight: 800}} align="right">
                  Action
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map((g) => {
                const guidelineId = normalizeObjectId((g as any)._id);

                return (
                  <TableRow key={guidelineId} hover>
                    <TableCell>{g.title}</TableCell>
                    <TableCell>{g.awmf_register_number_full}</TableCell>
                    <TableCell align="right">
                      <Button
                        variant="outlined"
                        size="small"
                        sx={{textTransform: "none"}}
                        onClick={() => onSelect(g)}
                      >
                        Open
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Box sx={{display: "flex", justifyContent: "flex-end"}}>
        <Button onClick={onCancel} sx={{textTransform: "none"}}>
          Close
        </Button>
      </Box>
    </Stack>
  );
}