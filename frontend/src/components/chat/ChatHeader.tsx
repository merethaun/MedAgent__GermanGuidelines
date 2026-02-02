import {Box, Button, Chip, Stack, Typography} from "@mui/material";

export default function ChatHeader(props: {
  chatName: string;
  chatId: string;
  username?: string;
  workflowName?: string;
  workflowId?: string;
  onNewChat: () => void;
  rightSlot?: React.ReactNode;
}) {
  const {chatName, chatId, username, workflowName, workflowId, onNewChat, rightSlot} = props;

  return (
    <Stack
      direction={{xs: "column", sm: "row"}}
      alignItems={{xs: "flex-start", sm: "center"}}
      justifyContent="space-between"
      spacing={2}
    >
      <Box>
        <Typography variant="h4" sx={{fontWeight: 900}}>
          Chat: {chatName}
        </Typography>

        <Stack direction="row" spacing={1} alignItems="center" sx={{mt: 0.75, flexWrap: "wrap"}}>
          <Chip label={`ID: ${chatId}`} size="small" variant="outlined"/>
          {username ? <Chip label={`User: ${username}`} size="small" variant="outlined"/> : null}
          {workflowName ? <Chip label={`Workflow: ${workflowName}`} size="small"/> : null}
          {!workflowName && workflowId ? <Chip label={`Workflow: ${workflowId}`} size="small"/> : null}
        </Stack>
      </Box>

      <Stack direction="row" spacing={1} alignItems="center">
        <Button
          variant="contained"
          color="success"
          onClick={onNewChat}
          sx={{textTransform: "none"}}
        >
          New chat
        </Button>

        {rightSlot}
      </Stack>
    </Stack>
  );
}