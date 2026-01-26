from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.common.py_object_id import PyObjectId


class NodeConfig(BaseModel):
    component_id: str
    name: str
    type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class EdgeConfig(BaseModel):
    source: str
    target: str


class WorkflowConfig(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    name: str
    nodes: List[NodeConfig]
    edges: List[EdgeConfig]
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_by_name=True,
        populate_by_name=True,
    )
