import {useParams} from "react-router-dom";
import {Box, Button, Chip, Divider, Paper, Stack, TextField, Typography} from "@mui/material";

export default function ChatInteractionPage() {
  const {chatId} = useParams();

  const placeholderMessages = [
    {role: "user" as const, ts: "—", text: "Platzhalter: User question goes here."},
    {role: "assistant" as const, ts: "—", text: "Platzhalter: assistant answer with references will go here."},
  ];

  return (
    <Stack spacing={2.5}>
      <Stack
        direction={{xs: "column", sm: "row"}}
        alignItems={{xs: "flex-start", sm: "center"}}
        justifyContent="space-between"
        spacing={2}
      >
        <Box>
          <Typography variant="h4" sx={{fontWeight: 800}}>
            Chat
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{mt: 0.75}}>
            <Chip label={`ID: ${chatId ?? "-"}`} size="small" variant="outlined"/>
            <Chip label="UI placeholder" size="small"/>
          </Stack>
        </Box>

        <Button variant="outlined" disabled sx={{textTransform: "none"}}>
          Export
        </Button>
      </Stack>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {xs: "1fr", md: "2fr 1fr"},
          gap: 2,
        }}
      >
        <Paper variant="outlined" sx={{p: 2, display: "flex", flexDirection: "column", minHeight: 480}}>
          <Typography variant="h6" sx={{fontWeight: 700}}>
            Messages
          </Typography>
          <Divider sx={{my: 1.5}}/>

          <Stack spacing={1.25} sx={{flex: 1, overflow: "auto", pr: 1}}>
            {placeholderMessages.map((m, idx) => (
              <Paper key={idx} variant="outlined" sx={{p: 1.5}}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2}>
                  <Typography variant="subtitle2" sx={{fontWeight: 700, textTransform: "capitalize"}}>
                    {m.role}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {m.ts}
                  </Typography>
                </Stack>
                <Typography sx={{whiteSpace: "pre-wrap", mt: 0.5}}>
                  {m.text}
                </Typography>
              </Paper>
            ))}

            <Typography variant="body2" color="text.secondary">
              Next step: wire in the real message stream + retrieval references; then replace these placeholders.
            </Typography>
          </Stack>

          <Divider sx={{my: 1.5}}/>
          <Stack direction="row" spacing={1}>
            <TextField fullWidth size="small" placeholder="Type a message…" disabled/>
            <Button variant="contained" disabled sx={{textTransform: "none"}}>
              Send
            </Button>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{p: 2, minHeight: 480}}>
          <Typography variant="h6" sx={{fontWeight: 700}}>
            References
          </Typography>
          <Divider sx={{my: 1.5}}/>
          <Stack spacing={1}>
            <Typography color="text.secondary">
              Placeholder: later render guideline references per answer (guideline title, section heading, page, and a
              clickable PDF deep link / highlight).
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Suggested UI: list items grouped by guideline, each with a short quote + page number.
            </Typography>
          </Stack>
        </Paper>
      </Box>
    </Stack>
  );
}
