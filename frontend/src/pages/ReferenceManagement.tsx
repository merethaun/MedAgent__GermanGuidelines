import {useEffect, useMemo, useRef, useState} from "react";
import {useNavigate} from "react-router-dom";
import {useAuth} from "../auth/AuthContext";

import CloseIcon from "@mui/icons-material/Close";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import IconButton from "@mui/material/IconButton";

import {normalizeObjectId} from "../api/system";
import {type GuidelineEntry, type GuidelineReferenceGroup, useReferenceApi,} from "../api/references";

import ReferenceGroupCreator from "../components/references/ReferenceGroupCreator";
import ReferenceGuidelinePicker from "../components/references/ReferenceGuidelinePicker";

const DEBUG = true;

export default function ReferenceManagementPage() {
  const auth = useAuth() as any;
  const navigate = useNavigate();

  const {
    listReferenceGroups,
    listGuidelines,
    listGuidelinesForGroup,
  } = useReferenceApi();

  const [showCreateGroup, setShowCreateGroup] = useState(false);
  const [showGuidelinePicker, setShowGuidelinePicker] = useState(false);

  const [loading, setLoading] = useState(false);
  const [groupGuidelinesLoading, setGroupGuidelinesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [referenceGroups, setReferenceGroups] = useState<GuidelineReferenceGroup[]>([]);
  const [allGuidelines, setAllGuidelines] = useState<GuidelineEntry[]>([]);
  const [groupGuidelines, setGroupGuidelines] = useState<GuidelineEntry[]>([]);

  const [selectedGroupId, setSelectedGroupId] = useState<string>("");

  const didAutoLoadRef = useRef(false);

  async function loadOnce() {
    setLoading(true);
    setError(null);

    try {
      const [groups, guidelines] = await Promise.all([
        listReferenceGroups(),
        listGuidelines(),
      ]);

      if (DEBUG) console.log("[ReferenceManagement] groups:", groups);
      if (DEBUG) console.log("[ReferenceManagement] guidelines:", guidelines);

      setReferenceGroups(groups ?? []);
      setAllGuidelines(guidelines ?? []);

      const firstGroupId =
        selectedGroupId ||
        normalizeObjectId((groups?.[0] as any)?._id) ||
        "";

      setSelectedGroupId(firstGroupId);

      if (firstGroupId) {
        setGroupGuidelinesLoading(true);
        try {
          const result = await listGuidelinesForGroup(firstGroupId);
          setGroupGuidelines(result ?? []);
        } finally {
          setGroupGuidelinesLoading(false);
        }
      } else {
        setGroupGuidelines([]);
      }
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
      setReferenceGroups([]);
      setAllGuidelines([]);
      setGroupGuidelines([]);
    } finally {
      setLoading(false);
    }
  }

  async function loadGuidelinesForSelectedGroup(referenceGroupId: string) {
    setSelectedGroupId(referenceGroupId);
    setGroupGuidelinesLoading(true);
    setError(null);

    try {
      const result = await listGuidelinesForGroup(referenceGroupId);
      if (DEBUG) console.log("[ReferenceManagement] group guidelines:", result);
      setGroupGuidelines(result ?? []);
    } catch (e: any) {
      console.error(e);
      setError(e?.message ?? String(e));
      setGroupGuidelines([]);
    } finally {
      setGroupGuidelinesLoading(false);
    }
  }

  useEffect(() => {
    if (!auth.initialized || !auth.authenticated) return;
    if (didAutoLoadRef.current) return;

    didAutoLoadRef.current = true;
    loadOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.initialized, auth.authenticated]);

  const selectedGroup = useMemo(() => {
    return referenceGroups.find(
      (g) => normalizeObjectId((g as any)._id) === selectedGroupId,
    ) ?? null;
  }, [referenceGroups, selectedGroupId]);

  const availableGuidelinesForPicker = useMemo(() => {
    const alreadyInGroup = new Set(
      groupGuidelines.map((g) => normalizeObjectId((g as any)._id)).filter(Boolean),
    );

    return allGuidelines.filter(
      (g) => !alreadyInGroup.has(normalizeObjectId((g as any)._id)),
    );
  }, [allGuidelines, groupGuidelines]);

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4" sx={{fontWeight: 800}}>
            Reference management
          </Typography>
          <Typography color="text.secondary">
            Manage reference groups and open guideline-specific editors.
          </Typography>
        </Box>

        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            onClick={() => loadOnce()}
            disabled={loading || !(auth.initialized && auth.authenticated)}
            sx={{textTransform: "none"}}
          >
            Reload
          </Button>

          <Button
            variant="contained"
            color="success"
            onClick={() => setShowCreateGroup(true)}
            disabled={!(auth.initialized && auth.authenticated)}
            sx={{textTransform: "none"}}
          >
            New reference group
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Stack direction={{xs: "column", lg: "row"}} spacing={2.5} alignItems="stretch">
        <Card variant="outlined" sx={{flex: 1, minWidth: 320}}>
          <CardContent sx={{p: 0}}>
            <Box sx={{p: 2}}>
              <Typography variant="h6" sx={{fontWeight: 800}}>
                Reference groups
              </Typography>
              <Typography color="text.secondary">
                Select a group to see which guidelines already contain references.
              </Typography>
            </Box>

            <Divider/>

            {loading ? (
              <Box sx={{display: "flex", justifyContent: "center", py: 6}}>
                <CircularProgress/>
              </Box>
            ) : referenceGroups.length === 0 ? (
              <Box sx={{p: 3}}>
                <Typography sx={{fontWeight: 700}}>No reference groups found</Typography>
                <Typography color="text.secondary">
                  Create the first reference group to get started.
                </Typography>
              </Box>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{fontWeight: 800}}>Name</TableCell>
                      <TableCell sx={{fontWeight: 800}} align="right">
                        Action
                      </TableCell>
                    </TableRow>
                  </TableHead>

                  <TableBody>
                    {referenceGroups.map((g) => {
                      const groupId = normalizeObjectId((g as any)._id);
                      const selected = groupId === selectedGroupId;

                      return (
                        <TableRow
                          key={groupId}
                          hover
                          selected={selected}
                          onClick={() => loadGuidelinesForSelectedGroup(groupId)}
                          sx={{cursor: "pointer"}}
                        >
                          <TableCell>{g.name}</TableCell>
                          <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                            <Button
                              variant="outlined"
                              size="small"
                              sx={{textTransform: "none"}}
                              onClick={() => loadGuidelinesForSelectedGroup(groupId)}
                            >
                              Select
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </Card>

        <Card variant="outlined" sx={{flex: 2, minWidth: 420}}>
          <CardContent sx={{p: 0}}>
            <Box sx={{p: 2}}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2}>
                <Box>
                  <Typography variant="h6" sx={{fontWeight: 800}}>
                    {selectedGroup ? `Guidelines in "${selectedGroup.name}"` : "Guidelines"}
                  </Typography>
                  <Typography color="text.secondary">
                    Open an editor for one guideline inside the selected reference group.
                  </Typography>
                </Box>

                <Button
                  variant="contained"
                  onClick={() => setShowGuidelinePicker(true)}
                  disabled={!selectedGroupId}
                  sx={{textTransform: "none"}}
                >
                  Add / open guideline
                </Button>
              </Stack>
            </Box>

            <Divider/>

            {!selectedGroupId ? (
              <Box sx={{p: 3}}>
                <Typography sx={{fontWeight: 700}}>No group selected</Typography>
                <Typography color="text.secondary">
                  Select a reference group first.
                </Typography>
              </Box>
            ) : groupGuidelinesLoading ? (
              <Box sx={{display: "flex", justifyContent: "center", py: 6}}>
                <CircularProgress/>
              </Box>
            ) : groupGuidelines.length === 0 ? (
              <Box sx={{p: 3}}>
                <Typography sx={{fontWeight: 700}}>No guidelines with references yet</Typography>
                <Typography color="text.secondary">
                  Open a guideline for this group. It will effectively appear here once the first
                  reference is created.
                </Typography>
              </Box>
            ) : (
              <TableContainer>
                <Table size="small">
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
                    {groupGuidelines.map((g) => {
                      const guidelineId = normalizeObjectId((g as any)._id);

                      return (
                        <TableRow
                          key={guidelineId}
                          hover
                          onClick={() =>
                            navigate(`/admin/references/${selectedGroupId}/${guidelineId}`)
                          }
                          sx={{cursor: "pointer"}}
                        >
                          <TableCell>{g.title}</TableCell>
                          <TableCell>{g.awmf_register_number_full}</TableCell>
                          <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                            <Button
                              variant="outlined"
                              size="small"
                              sx={{textTransform: "none"}}
                              onClick={() =>
                                navigate(`/admin/references/${selectedGroupId}/${guidelineId}`)
                              }
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
          </CardContent>
        </Card>
      </Stack>

      <Dialog
        open={showCreateGroup}
        onClose={() => setShowCreateGroup(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle sx={{fontWeight: 800}}>
          <Typography variant="h5" sx={{fontWeight: 800}}>
            New reference group
          </Typography>
          <IconButton
            aria-label="close"
            onClick={() => setShowCreateGroup(false)}
            sx={{position: "absolute", right: 8, top: 8}}
            size="small"
          >
            <CloseIcon/>
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <ReferenceGroupCreator
            onCancel={() => setShowCreateGroup(false)}
            onCreated={async (created) => {
              setShowCreateGroup(false);
              await loadOnce();

              const groupId = normalizeObjectId((created as any)._id);
              if (groupId) {
                await loadGuidelinesForSelectedGroup(groupId);
              }
            }}
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={showGuidelinePicker}
        onClose={() => setShowGuidelinePicker(false)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle sx={{fontWeight: 800}}>
          <Typography variant="h5" sx={{fontWeight: 800}}>
            Open guideline in group
          </Typography>
          <IconButton
            aria-label="close"
            onClick={() => setShowGuidelinePicker(false)}
            sx={{position: "absolute", right: 8, top: 8}}
            size="small"
          >
            <CloseIcon/>
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <ReferenceGuidelinePicker
            guidelines={availableGuidelinesForPicker}
            onCancel={() => setShowGuidelinePicker(false)}
            onSelect={(guideline) => {
              setShowGuidelinePicker(false);
              const guidelineId = normalizeObjectId((guideline as any)._id);
              if (selectedGroupId && guidelineId) {
                navigate(`/admin/references/${selectedGroupId}/${guidelineId}`);
              }
            }}
          />
        </DialogContent>
      </Dialog>
    </Stack>
  );
}