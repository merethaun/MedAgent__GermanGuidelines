import {Box, Button, Card, CardContent, Divider, Stack, Typography} from "@mui/material";

export default function ChatsPage() {
  return (
    <Stack spacing={2.5}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4" sx={{fontWeight: 800}}>
            Chats
          </Typography>
          <Typography color="text.secondary">
            Overview of existing chats (placeholder UI).
          </Typography>
        </Box>

        <Button variant="contained" disabled sx={{textTransform: "none"}}>
          New chat
        </Button>
      </Stack>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1}>
            <Typography variant="h6" sx={{fontWeight: 700}}>
              No data wired yet
            </Typography>
            <Typography color="text.secondary">
              This page currently contains only the layout. Next step is to fetch chat metadata from the backend and
              render it as a list of cards with title, last updated, and a "Continue" action.
            </Typography>
            <Divider sx={{my: 1}}/>
            <Typography variant="body2" color="text.secondary">
              Suggested UI elements: searchable list, pagination, "create chat" button, and a right-side preview panel.
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
