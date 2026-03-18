from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReferenceHierarchyIndexNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    reference_group_id: str
    guideline_id: str
    heading_level: int = Field(default=0)
    heading_number: str = Field(default="")
    title: str = Field(default="")
    label: str = Field(default="")
    parent_id: Optional[str] = Field(default=None)
    descendant_reference_ids: List[str] = Field(default_factory=list)


class ReferenceHierarchyIndexSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_group_id: str
    nodes: Dict[str, ReferenceHierarchyIndexNode] = Field(default_factory=dict)
    reference_to_node: Dict[str, str] = Field(default_factory=dict)


class ReferenceHierarchyIndexBuildResponse(BaseModel):
    reference_group_id: str
    node_count: int
    mapped_reference_count: int
    persisted_path: str
