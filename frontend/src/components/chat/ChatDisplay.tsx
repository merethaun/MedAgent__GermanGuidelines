import {useMemo, useState} from "react";
import {Box, Button, Divider, Paper, Stack, TextField, Typography} from "@mui/material";
import {alpha} from "@mui/material/styles";
import {type Chat, type ChatInteraction} from "../../api/system";

function fmtTime(iso?: string | null): string | undefined {
  if (!iso) return undefined;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function Bubble(props: {
  side: "left" | "right";
  title: string;
  time?: string;
  text: string;
}) {
  const {side, title, time, text} = props;
  const isLeft = side === "left";

  return (
    <Box sx={{display: "flex", justifyContent: isLeft ? "flex-start" : "flex-end"}}>
      <Box
        sx={(theme) => ({
          maxWidth: "85%",
          px: 2,
          py: 1.25,
          borderRadius: 1,
          bgcolor: isLeft ? alpha(theme.palette.text.primary, 0.07) : alpha(theme.palette.primary.main, 0.08),
          color: "text.primary",
        })}
      >
        <Stack direction="row" spacing={1} alignItems="baseline" justifyContent="space-between">
          <Typography variant="caption" sx={{fontWeight: 800}}>
            {title}
          </Typography>
          {time ? (
            <Typography variant="caption" color="text.secondary">
              {time}
            </Typography>
          ) : null}
        </Stack>

        <Typography sx={{whiteSpace: "pre-wrap", mt: 0.5}}>{text}</Typography>
      </Box>
    </Box>
  );
}

function InteractionBlock(props: {
  idx: number;
  interaction: ChatInteraction;
  selected: boolean;
  onSelect: () => void;
}) {
  const {idx, interaction, selected, onSelect} = props;

  const qTime = fmtTime(interaction.time_question_input);
  const aTime = fmtTime(interaction.time_response_output ?? interaction.time_question_input);

  const userText = (interaction.user_input ?? "").trim() || "—";
  const assistantText = (interaction.generator_output ?? "").trim() || "No answer yet.";

  const refCount = interaction.retrieval_output?.length ?? 0;

  return (
    <Box
      onClick={onSelect}
      sx={(theme) => ({
        borderRadius: 0,
        p: 2,
        cursor: "pointer",
        border: "none",
        backgroundColor: selected ? alpha(theme.palette.primary.main, 0.06) : "transparent",
        transition: "background-color 120ms ease, border-color 120ms ease",
        "&:hover": {
          backgroundColor: alpha(theme.palette.text.primary, 0.03),
        },
      })}
    >
      <Stack spacing={1.25}>
        <Bubble side="left" title="User" time={qTime} text={userText}/>
        <Bubble side="right" title="System" time={aTime} text={assistantText}/>
        <Typography variant="caption" color="text.secondary" sx={{pl: 1}}>
          {selected ? (
            <b>Interaction #{idx + 1} • References: {refCount}</b>
          ) : (
            <>Interaction #{idx + 1} • References: {refCount}</>
          )}
        </Typography>
      </Stack>
    </Box>
  );
}

export default function ChatDisplay(props: {
  chat: Chat;
  selectedInteractionIndex: number;
  onSelectInteractionIndex: (idx: number) => void;
  onSend: (text: string) => Promise<void>;
  sending?: boolean;
  height?: string | number;
  minHeightPx?: number;
}) {
  const {chat, selectedInteractionIndex, onSelectInteractionIndex, onSend, sending, height, minHeightPx} = props;

  const interactions = chat.interactions ?? [];
  const [draft, setDraft] = useState("");

  const canSend = draft.trim().length > 0 && !sending;

  const ordered = useMemo(() => {
    // chronological (oldest -> newest)
    return interactions.map((x, idx) => ({x, idx}));
  }, [interactions]);

  return (
    <Paper
      variant="outlined"
      sx={{
        height: height ?? "auto",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        minHeight: minHeightPx,
      }}
    >
      <Box sx={{p: 2}}>
        <Typography variant="h6" sx={{fontWeight: 800}}>
          Messages
        </Typography>
      </Box>

      <Divider/>

      {/* Scrollable message list */}
      <Box sx={{flex: 1, minHeight: 0, overflow: "auto", p: "2 0"}}>
        <Stack spacing={1.25}>
          {ordered.length === 0 ? (
            <Box sx={{p: 1}}>
              <Typography sx={{fontWeight: 700}}>No interactions yet</Typography>
              <Typography color="text.secondary">Send a message below to start.</Typography>
            </Box>
          ) : (
            ordered.map(({x, idx}) => (
              <InteractionBlock
                key={idx}
                idx={idx}
                interaction={x}
                selected={idx === selectedInteractionIndex}
                onSelect={() => onSelectInteractionIndex(idx)}
              />
            ))
          )}
        </Stack>
      </Box>

      <Divider/>

      {/* Composer */}
      <Box sx={{p: 2}}>
        <Stack direction="row" spacing={1} alignItems="flex-end">
          <TextField
            fullWidth
            size="small"
            placeholder="Type a message …"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={!!sending}
            multiline
            maxRows={4}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!canSend) return;
                const text = draft.trim();
                setDraft("");
                void onSend(text);
              }
            }}
          />

          <Button
            variant="contained"
            sx={{textTransform: "none", minWidth: 100}}
            disabled={!canSend}
            onClick={() => {
              if (!canSend) return;
              const text = draft.trim();
              setDraft("");
              void onSend(text);
            }}
          >
            {sending ? "Sending…" : "Send"}
          </Button>
        </Stack>
      </Box>
    </Paper>
  );
}
