from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge.guideline.guideline_reference import GuidelineReference


class GuidelineExpanderKind(str, Enum):
    NEIGHBORHOOD = "neighborhood"
    HIERARCHY = "hierarchy"


class NeighborhoodDirection(str, Enum):
    PRECEDING = "preceding"
    SUCCEEDING = "succeeding"
    BOTH = "both"


class HierarchySelectionMode(str, Enum):
    DIRECT_PARENT = "direct_parent"
    LEVELS_UP = "levels_up"
    HEADING_LEVEL = "heading_level"


class GuidelineExpanderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: GuidelineExpanderKind
    reference_group_id: Optional[str] = Field(default=None)

    context_window_size: int = Field(default=1, ge=1, le=20)
    direction: NeighborhoodDirection = Field(default=NeighborhoodDirection.BOTH)

    mode: HierarchySelectionMode = Field(default=HierarchySelectionMode.DIRECT_PARENT)
    levels_up: int = Field(default=1, ge=1, le=10)
    heading_level: Optional[int] = Field(default=None, ge=0)
    simple_ratio_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Optional coverage ratio required before a resolved hierarchy target section is promoted. "
            "Computed as matched seed references within that target divided by all descendant references in the target section. "
            "If omitted, any resolved target section expands immediately."
        ),
    )

    @model_validator(mode="after")
    def _validate(self) -> "GuidelineExpanderSettings":
        if self.kind == GuidelineExpanderKind.HIERARCHY and self.mode == HierarchySelectionMode.HEADING_LEVEL and self.heading_level is None:
            raise ValueError("heading_level must be set when kind='hierarchy' and mode='heading_level'.")
        return self


class GuidelineExpanderRequest(BaseModel):
    references: List[GuidelineReference]
    settings: GuidelineExpanderSettings


class GuidelineExpanderResponse(BaseModel):
    kind: GuidelineExpanderKind
    references: List[GuidelineReference]
    added_references: List[GuidelineReference]
    latency: float
