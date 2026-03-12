import {useState} from "react";
import {Alert, Box, Button, Stack, TextField} from "@mui/material";
import {type GuidelineReferenceGroup, useReferenceApi} from "../../api/references";

type Props = {
  onCancel: () => void;
  onCreated: (created: GuidelineReferenceGroup) => void | Promise<void>;
};

export default function ReferenceGroupCreator({onCancel, onCreated}: Props) {
  const {createReferenceGroup} = useReferenceApi();

  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Please enter a group name.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const created = await createReferenceGroup({name: trimmed});
      await onCreated(created);
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack spacing={2}>
      {error && <Alert severity="error">{error}</Alert>}

      <TextField
        label="Reference group name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        fullWidth
        autoFocus
      />

      <Box sx={{display: "flex", justifyContent: "flex-end", gap: 1}}>
        <Button onClick={onCancel} disabled={saving} sx={{textTransform: "none"}}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleCreate}
          disabled={saving || !name.trim()}
          sx={{textTransform: "none"}}
        >
          Create
        </Button>
      </Box>
    </Stack>
  );
}