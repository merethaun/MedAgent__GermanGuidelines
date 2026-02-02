import {useCallback} from "react";
import {useAuthedFetch} from "./http";

export type ReferenceType = "text" | "image" | "table" | "recommendation" | "statement" | "metadata";

export type BoundingBox = {
  page: number;
  positions: [number, number, number, number]; // x0, y0, x1, y1
};

export type GuidelineHierarchyEntry = {
  title: string;
  heading_level: number;
  heading_number: string;
  order?: number;
};

export type GuidelineReferenceBase = {
  _id?: any;
  reference_group_id?: any;
  guideline_id: any;
  type: ReferenceType;
  bboxs: BoundingBox[];
  document_hierarchy: GuidelineHierarchyEntry[];
  note?: string;
  created_automatically?: boolean;
  created_date?: string;
  associated_keywords?: string[];
};

export type GuidelineTextReference = GuidelineReferenceBase & {
  type: "text";
  contained_text?: string;
};

export type GuidelineImageReference = GuidelineReferenceBase & {
  type: "image";
  caption?: string;
  describing_text?: string;
};

export type GuidelineTableReference = GuidelineReferenceBase & {
  type: "table";
  caption?: string;
  plain_text?: string;
  table_markdown?: string;
};

export type GuidelineRecommendationReference = GuidelineReferenceBase & {
  type: "recommendation";
  recommendation_title?: string;
  recommendation_content?: string;
  recommendation_grade?: string;
};

export type GuidelineStatementReference = GuidelineReferenceBase & {
  type: "statement";
  statement_title?: string;
  statement_content?: string;
  statement_consensus_grade?: string;
};

export type GuidelineMetadataReference = GuidelineReferenceBase & {
  type: "metadata";
  metadata_type?: string;
  metadata_content?: string;
};

export type GuidelineReference =
  | GuidelineTextReference
  | GuidelineImageReference
  | GuidelineTableReference
  | GuidelineRecommendationReference
  | GuidelineStatementReference
  | GuidelineMetadataReference;

async function readBodySafe(res: Response) {
  const text = await res.text().catch(() => "");
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export function useReferenceApi() {
  const authedFetch = useAuthedFetch();

  const getReferenceById = useCallback(
    async (referenceId: string) => {
      const res = await authedFetch(`/guideline_references/${encodeURIComponent(referenceId)}`, {method: "GET"});
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

  return {getReferenceById};
}