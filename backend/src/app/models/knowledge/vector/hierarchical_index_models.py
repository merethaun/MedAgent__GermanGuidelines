from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set


@dataclass
class ParentNode:
    id: str
    label: str
    parent_id: Optional[str]
    depth: int = 0
    # Edges
    child_parent_ids: List[str] = field(default_factory=list)
    child_leaf_ids: List[str] = field(default_factory=list)
    # Derived
    desc_leaf_ids: List[str] = field(default_factory=list)  # ordered list of ALL descendant leaves
    desc_leaf_count: int = 0


@dataclass
class HierConfig:
    text_property: str = "text"
    heading_path_property: str = "heading_path"
    guideline_id_property: str = "guideline_id"
    order_property: str = "chunk_index"
    direct_parent_property: Optional[str] = None


@dataclass
class HierIndex:
    cfg: HierConfig
    # Parents by ID
    parents: Dict[str, ParentNode] = field(default_factory=dict)
    # For fast lookups
    roots: Set[str] = field(default_factory=set)
    leaf_to_parent: Dict[str, str] = field(default_factory=dict)
    parent_of_parent: Dict[str, Optional[str]] = field(default_factory=dict)
    ancestors_cache: Dict[str, List[str]] = field(default_factory=dict)
    # Leaf facts
    leaf_text: Dict[str, str] = field(default_factory=dict)
    leaf_order: Dict[str, int] = field(default_factory=dict)
    leaf_guideline: Dict[str, str] = field(default_factory=dict)
    
    def get_ancestors(self, parent_id: str) -> List[str]:
        if parent_id in self.ancestors_cache:
            return self.ancestors_cache[parent_id]
        chain = []
        cur = parent_id
        while True:
            cur = self.parent_of_parent.get(cur)
            if not cur:
                break
            chain.append(cur)
        self.ancestors_cache[parent_id] = chain
        return chain
