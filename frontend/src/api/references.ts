import {useCallback} from "react";
import {useAuthedFetch} from "./http";
import {normalizeObjectId} from "./system";

async function readBodySafe(res: Response) {
  const text = await res.text().catch(() => "");
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export type GuidelineReferenceType =
  | "text"
  | "image"
  | "table"
  | "recommendation"
  | "statement"
  | "metadata";

export type GuidelineReferenceGroup = {
  _id?: string | null;
  name: string;
};

export type GuidelineEntry = {
  _id?: string | null;
  awmf_register_number: string;
  awmf_register_number_full: string;
  awmf_class?: string | null;
  title: string;
  keywords?: string[];
  download_information?: {
    url?: string | null;
    download_date?: string | null;
    file_path?: string | null;
    page_count?: number | null;
  } | null;
};

export type BoundingBox = {
  page: number;
  positions: [number, number, number, number];
};

export type GuidelineHierarchyEntry = {
  title: string;
  heading_level: number;
  heading_number: string;
  order?: number;
};

export type BaseReference = {
  _id?: string | null;
  reference_group_id?: string | null;
  guideline_id: string;
  type: GuidelineReferenceType;
  bboxs?: BoundingBox[];
  document_hierarchy?: GuidelineHierarchyEntry[];
  note?: string | null;
  created_automatically?: boolean;
  created_date?: string;
  associated_keywords?: string[] | null;
};

export type GuidelineTextReference = BaseReference & {
  type: "text";
  contained_text: string;
};

export type GuidelineImageReference = BaseReference & {
  type: "image";
  caption?: string;
  describing_text?: string | null;
};

export type GuidelineTableReference = BaseReference & {
  type: "table";
  caption?: string;
  plain_text?: string;
  table_markdown?: string;
};

export type GuidelineRecommendationReference = BaseReference & {
  type: "recommendation";
  recommendation_title?: string | null;
  recommendation_content: string;
  recommendation_grade: string;
};

export type GuidelineStatementReference = BaseReference & {
  type: "statement";
  statement_title?: string | null;
  statement_content: string;
  statement_consensus_grade: string;
};

export type GuidelineMetadataReference = BaseReference & {
  type: "metadata";
  metadata_type: string;
  metadata_content: string;
};

export type GuidelineReference =
  | GuidelineTextReference
  | GuidelineImageReference
  | GuidelineTableReference
  | GuidelineRecommendationReference
  | GuidelineStatementReference
  | GuidelineMetadataReference;

export type CreateReferenceGroupArgs = {
  name: string;
};

export type ListReferencesArgs = {
  referenceGroupId?: string;
  guidelineId?: string;
  referenceType?: GuidelineReferenceType;
};

export type FindBoundingBoxesArgs = {
  guideline_id: string;
  text: string;
  start_page?: number | null;
  end_page?: number | null;
};

export function useReferenceApi() {
  const authedFetch = useAuthedFetch();

  const listReferenceGroups = useCallback(async () => {
    const res = await authedFetch(`/guideline_references/groups`, {method: "GET"});
    if (!res.ok) {
      const body = await readBodySafe(res);
      throw new Error(
        `GET /guideline_references/groups failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
      );
    }
    return (await res.json()) as GuidelineReferenceGroup[];
  }, [authedFetch]);

  const createReferenceGroup = useCallback(
    async (args: CreateReferenceGroupArgs) => {
      const payload: GuidelineReferenceGroup = {name: args.name};

      const res = await authedFetch(`/guideline_references/groups`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `POST /guideline_references/groups failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }

      const createdId = (await res.json()) as string;
      return {_id: createdId, name: args.name} as GuidelineReferenceGroup;
    },
    [authedFetch],
  );

  const getReferenceGroupById = useCallback(
    async (referenceGroupId: string) => {
      const res = await authedFetch(
        `/guideline_references/groups/${encodeURIComponent(referenceGroupId)}`,
        {method: "GET"},
      );
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `GET /guideline_references/groups/${referenceGroupId} failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return (await res.json()) as GuidelineReferenceGroup;
    },
    [authedFetch],
  );

  const listGuidelines = useCallback(async () => {
    const res = await authedFetch(`/guidelines/`, {method: "GET"});
    if (!res.ok) {
      const body = await readBodySafe(res);
      throw new Error(
        `GET /guidelines/ failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
      );
    }
    return (await res.json()) as GuidelineEntry[];
  }, [authedFetch]);

  const getGuidelineById = useCallback(
    async (guidelineId: string) => {
      const res = await authedFetch(`/guidelines/${encodeURIComponent(guidelineId)}`, {
        method: "GET",
      });
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `GET /guidelines/${guidelineId} failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return (await res.json()) as GuidelineEntry;
    },
    [authedFetch],
  );

  const fetchGuidelinePdfBlob = useCallback(
    async (guidelineId: string) => {
      const res = await authedFetch(`/guidelines/${encodeURIComponent(guidelineId)}/pdf`, {
        method: "GET",
      });
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `GET /guidelines/${guidelineId}/pdf failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return await res.blob();
    },
    [authedFetch],
  );

  const listReferences = useCallback(
    async (args: ListReferencesArgs = {}) => {
      const sp = new URLSearchParams();
      if (args.referenceGroupId) sp.set("reference_group_id", args.referenceGroupId);
      if (args.guidelineId) sp.set("guideline_id", args.guidelineId);
      if (args.referenceType) sp.set("reference_type", args.referenceType);

      const qs = sp.toString();
      const res = await authedFetch(`/guideline_references/${qs ? `?${qs}` : ""}`, {
        method: "GET",
      });

      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `GET /guideline_references/ failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }

      return (await res.json()) as GuidelineReference[];
    },
    [authedFetch],
  );

  const getReferenceById = useCallback(
    async (referenceId: string) => {
      const res = await authedFetch(`/guideline_references/${encodeURIComponent(referenceId)}`, {
        method: "GET",
      });
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `GET /guideline_references/${referenceId} failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return (await res.json()) as GuidelineReference;
    },
    [authedFetch],
  );

  const createReference = useCallback(
    async (reference: GuidelineReference) => {
      const res = await authedFetch(`/guideline_references/`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(reference),
      });
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `POST /guideline_references/ failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return (await res.json()) as string;
    },
    [authedFetch],
  );

  const patchReference = useCallback(
    async (referenceId: string, patch: Record<string, any>) => {
      const res = await authedFetch(`/guideline_references/${encodeURIComponent(referenceId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `PATCH /guideline_references/${referenceId} failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return await readBodySafe(res);
    },
    [authedFetch],
  );

  const deleteReference = useCallback(
    async (referenceId: string) => {
      const res = await authedFetch(`/guideline_references/${encodeURIComponent(referenceId)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `DELETE /guideline_references/${referenceId} failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }
      return await readBodySafe(res);
    },
    [authedFetch],
  );

  const findBoundingBoxes = useCallback(
    async (args: FindBoundingBoxesArgs) => {
      const res = await authedFetch(`/guideline_references/finder`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(args),
      });

      if (!res.ok) {
        const body = await readBodySafe(res);
        throw new Error(
          `POST /guideline_references/finder failed: ${res.status} ${res.statusText} — ${JSON.stringify(body)}`,
        );
      }

      return (await res.json()) as BoundingBox[];
    },
    [authedFetch],
  );

  const listGuidelinesForGroup = useCallback(
    async (referenceGroupId: string) => {
      const [allGuidelines, refs] = await Promise.all([
        listGuidelines(),
        listReferences({referenceGroupId}),
      ]);

      const guidelineIdsInGroup = new Set(
        refs
          .map((r) => normalizeObjectId((r as any).guideline_id))
          .filter(Boolean),
      );

      return allGuidelines.filter((g) =>
        guidelineIdsInGroup.has(normalizeObjectId((g as any)._id)),
      );
    },
    [listGuidelines, listReferences],
  );

  return {
    listReferenceGroups,
    createReferenceGroup,
    getReferenceGroupById,
    listGuidelines,
    getGuidelineById,
    fetchGuidelinePdfBlob,
    listReferences,
    getReferenceById,
    createReference,
    patchReference,
    deleteReference,
    listGuidelinesForGroup,
    findBoundingBoxes,
  };
}
