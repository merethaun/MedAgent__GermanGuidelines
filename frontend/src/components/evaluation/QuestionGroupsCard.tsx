import {Button, Card, CardContent, MenuItem, Stack, TextField, Typography} from "@mui/material";

import {type QuestionGroup} from "../../api/evaluation";
import {normalizeObjectId} from "../../api/system";

type QuestionGroupsCardProps = {
  questionGroups: QuestionGroup[];
  selectedGroupId: string;
  newGroupName: string;
  newGroupDescription: string;
  onSelectedGroupChange: (value: string) => void;
  onNewGroupNameChange: (value: string) => void;
  onNewGroupDescriptionChange: (value: string) => void;
  onCreateGroup: () => void;
};

export default function QuestionGroupsCard({
  questionGroups,
  selectedGroupId,
  newGroupName,
  newGroupDescription,
  onSelectedGroupChange,
  onNewGroupNameChange,
  onNewGroupDescriptionChange,
  onCreateGroup,
}: QuestionGroupsCardProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{fontWeight: 800, mb: 2}}>
          Question groups
        </Typography>
        <Stack direction={{xs: "column", md: "row"}} spacing={2}>
          <TextField label="New group name" value={newGroupName} onChange={(e) => onNewGroupNameChange(e.target.value)} fullWidth />
          <TextField label="Description" value={newGroupDescription} onChange={(e) => onNewGroupDescriptionChange(e.target.value)} fullWidth />
          <Button variant="contained" onClick={onCreateGroup} sx={{textTransform: "none"}}>
            Create
          </Button>
        </Stack>
        <TextField
          select
          fullWidth
          sx={{mt: 2}}
          label="Selected group"
          value={selectedGroupId}
          onChange={(e) => onSelectedGroupChange(e.target.value)}
        >
          {questionGroups.map((group) => (
            <MenuItem key={normalizeObjectId(group._id)} value={normalizeObjectId(group._id)}>
              {group.name}
            </MenuItem>
          ))}
        </TextField>
      </CardContent>
    </Card>
  );
}
