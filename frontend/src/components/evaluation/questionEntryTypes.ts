import {QUESTION_SUB_CLASS_OPTIONS, type ExpectedRetrievalSnippet, type QuestionSubClass, type QuestionSuperClass} from "../../api/evaluation";
import {type GuidelineEntry} from "../../api/references";
import {normalizeObjectId} from "../../api/system";

export type ManualSnippetDraft = {
  guidelineId: string;
  guidelineSource: string;
  guidelineTitle: string;
  referenceType: "" | ExpectedRetrievalSnippet["reference_type"];
  retrievalText: string;
  boundingBoxesJson: string;
  startPage: string;
  endPage: string;
};

export function getDefaultSubClass(superClass: QuestionSuperClass): QuestionSubClass {
  return QUESTION_SUB_CLASS_OPTIONS[superClass][0].value;
}

export function createEmptySnippet(): ManualSnippetDraft {
  return {
    guidelineId: "",
    guidelineSource: "",
    guidelineTitle: "",
    referenceType: "text",
    retrievalText: "",
    boundingBoxesJson: "",
    startPage: "",
    endPage: "",
  };
}

export function createDraftFromSnippet(
  snippet: ExpectedRetrievalSnippet,
  guidelines: GuidelineEntry[],
): ManualSnippetDraft {
  const normalizedSource = (snippet.guideline_source || "").trim();
  const normalizedTitle = (snippet.guideline_title || "").trim();
  const matchingGuideline = guidelines.find((guideline) => {
    const guidelineSource = (guideline.download_information?.url || "").trim();
    return (
      (normalizedSource && guidelineSource === normalizedSource) ||
      (normalizedTitle && guideline.title.trim() === normalizedTitle)
    );
  });

  return {
    guidelineId: matchingGuideline ? normalizeObjectId(matchingGuideline._id) : "",
    guidelineSource: snippet.guideline_source || "",
    guidelineTitle: snippet.guideline_title || "",
    referenceType: snippet.reference_type || "text",
    retrievalText: snippet.retrieval_text || "",
    boundingBoxesJson: snippet.bounding_boxes?.length ? JSON.stringify(snippet.bounding_boxes, null, 2) : "",
    startPage: "",
    endPage: "",
  };
}

export function formatGuidelineLabel(guideline: GuidelineEntry) {
  const number = guideline.awmf_register_number_full || guideline.awmf_register_number;
  return `${number} - ${guideline.title}`;
}
